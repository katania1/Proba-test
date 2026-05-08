import os
import re
import json
import base64
from PyQt6.QtCore import QObject, pyqtSignal, QSettings
from PyQt6.QtWidgets import QMessageBox, QApplication, QDialog

from core.ai_orchestrator import AIOrchestrator
from core.bridge import VibeBridge
from core.api_worker import APIWorker
from core.providers import OpenAIProvider, AnthropicProvider, GeminiAPIProvider
from core.vector_db import VectorDatabase
from core.embeddings import EmbeddingFactory
from core.mcp_manager import MCPManager

class AIController(QObject):
    ai_response_signal = pyqtSignal(str)
    limit_reached_signal = pyqtSignal()

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window 
        
        self.orchestrator = AIOrchestrator()
        self.bridge = VibeBridge()
        
        self.bridge.on_result_received = lambda text: self.ai_response_signal.emit(text)
        self.bridge.on_limit_reached = lambda: self.limit_reached_signal.emit()
        
        self.ai_response_signal.connect(self.process_ai_response)
        self.limit_reached_signal.connect(self.process_limit_reached)
        
        self.retry_count = 0
        self.is_waiting_for_commit_msg = False
        self.is_waiting_for_relay_msg = False
        
        self.browser_mcp_step = 0
        self.max_browser_mcp_steps = 5
        self.mcp_manager = MCPManager(self.mw.project_path)
        
        self.agent_trace = []

    def _extract_first_json(self, text):
        start = text.find('{')
        if start == -1: return None
        
        braces = 0
        for i in range(start, len(text)):
            if text[i] == '{': braces += 1
            elif text[i] == '}':
                braces -= 1
                if braces == 0:
                    try:
                        import json
                        return json.loads(text[start:i+1])
                    except:
                        return None
        return None

    def start(self):
        self.bridge.start_server()

    def estimate_tokens(self, text):
        return int(len(text) / 2.5)

    def _encode_image_base64(self, filepath):
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def _get_rag_context_string(self, user_text):
        if not user_text or len(user_text.strip()) < 10:
            return ""

        db_path = os.path.join(self.mw.project_path, ".vibecoder", "vector_db")
        if not os.path.exists(db_path):
            return ""

        try:
            db = VectorDatabase(self.mw.project_path)
            if db.collection.count() == 0:
                return ""
                
            embed_provider, _ = EmbeddingFactory.get_provider("Gemini")
            self.mw.log_system("🔍 [RAG] Векторизация вопроса и поиск по кодовой базе...")
            
            query_vector = embed_provider.get_embedding(user_text)
            results = db.search(query_vector, n_results=3)
            
            if not results:
                return ""

            rag_context = "=== СИСТЕМНЫЙ КОНТЕКСТ ПРОЕКТА (RAG) ===\n"
            rag_context += "Ниже представлены фрагменты кода из текущего проекта, которые семантически связаны с запросом пользователя.\n"
            rag_context += "Используй их для понимания архитектуры, но не меняй, если пользователь явно не просил.\n\n"
            
            marker = '`' * 3
            for i, res in enumerate(results):
                file_path = res['metadata'].get('file_path', 'Неизвестный файл')
                rag_context += f"--- Файл: {file_path} (Совпадение #{i+1}) ---\n"
                rag_context += f"{marker}python\n{res['text']}\n{marker}\n\n"

            self.mw.log_system(f"🧠 [RAG] Найдено {len(results)} релевантных фрагментов.")
            return rag_context

        except Exception as e:
            self.mw.log_system(f"⚠️ Ошибка RAG-поиска: {str(e)}", color="#ffaa00")
            return ""

    def send_task(self, is_coding_mode=True):
        import mimetypes
        user_text = self.mw.prompt_input.toPlainText().strip()
        if not user_text: return
        
        self.agent_trace = []
        
        engine_data = self.mw.get_selected_engine_data()
        provider_id = engine_data.get("provider_id", "Browser")
        selected_model = engine_data.get("model", "")
        target_id = self.mw.get_current_target_id()
        is_browser = (provider_id == "Browser")
        
        try:
            selected_tab = self.mw.status_bar.combo_tabs.currentText()
        except AttributeError:
            selected_tab = "Browser"
        
        if is_browser and "🔴" in selected_tab:
            self.mw.show_popup("Ошибка связи", "Нет активных вкладок браузера!", is_error=True)
            return

        # 1. Подготовка изображений (физических)
        image_paths = list(self.mw.attachment_panel.get_attachments())
        image_payload = []
        if image_paths:
            for path in image_paths:
                base64_img = self._encode_image_base64(path)
                mime_type, _ = mimetypes.guess_type(path)
                if not mime_type: mime_type = "image/jpeg"
                image_payload.append({"mime": mime_type, "data": base64_img, "name": os.path.basename(path)})

        # 2. Получение RAG контекста (ТОЛЬКО ДЛЯ РЕЖИМА КОДИНГА)
        rag_context_str = ""
        if is_coding_mode:
            rag_context_str = self._get_rag_context_string(user_text)
        else:
            self.mw.log_system("💬 Режим чата: умный RAG-поиск отключен.")

        # 3. Получение содержимого файлов из тегов (Работает всегда, если файл указан явно)
        attached_blocks_text = []
        tags_in_text = re.findall(r'@\[.*?\]|@[\w\.\-\/\\]+', user_text)
        for tag in tags_in_text:
            fname = tag[1:].strip("[]")
            if fname in self.mw.attached_files:
                content = self.mw.get_file_content_safe(fname)
                if content:
                    if is_browser:
                        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                        image_payload.append({"mime": "text/plain", "data": b64_content, "name": os.path.basename(fname)})
                    else:
                        marker = '`' * 3
                        attached_blocks_text.append("### ФАЙЛ: " + fname + " ###\n" + marker + "\n" + content + "\n" + marker)

        # Логирование в UI
        self.mw.chat_logger.log("USER", user_text)
        tab_display_name = selected_tab.split(" [")[0].replace("🟢 ", "") if is_browser else selected_model
        media_notice = f" <i>(+ {len(image_paths)} картинки)</i>" if image_paths else ""
        mode_notice = "⚡ Кодинг" if is_coding_mode else "💬 Чат"
        self.mw.chat_history.append(f"<br><span style='color: #569cd6;'><b>ВЫ</b> [{mode_notice}] (в <i>{tab_display_name}</i>){media_notice}<b>:</b> {user_text}</span>")

        if is_browser:
            self.browser_mcp_step = 0
            
            # Собираем MCP инструменты (доступны в обоих режимах)
            tools_instruction = ""
            tools_schema = self.mcp_manager.get_tools_schema()
            if tools_schema:
                tools_instruction = (
                    "--- ДОСТУПНЫЕ ИНСТРУМЕНТЫ (MCP) ---\n"
                    "У тебя есть доступ к внешним инструменты (Context7, Поиск, БД).\n"
                    "АБСОЛЮТНЫЙ ПРИОРИТЕТ: Если тебе нужно вызвать инструмент, ВЕРНИ ТОЛЬКО ОДИН JSON в формате:\n"
                    '{"tool": "имя_инструмента", "args": {"ключ": "значение"}}\n'
                    "Ты можешь вызывать инструменты ПО ОЧЕРЕДИ несколько раз.\n"
                    "Список инструментов:\n" + json.dumps(tools_schema, ensure_ascii=False, indent=2) + "\n\n"
                )

            if is_coding_mode:
                # ФОРМИРУЕМ ТЯЖЕЛЫЙ КОНТЕКСТ
                system_rules = tools_instruction + self.orchestrator.system_prompt
                b64_rules = base64.b64encode(system_rules.encode('utf-8')).decode('utf-8')
                image_payload.append({"mime": "text/plain", "data": b64_rules, "name": "vibe_instructions.txt"})

                if rag_context_str:
                    b64_rag = base64.b64encode(rag_context_str.encode('utf-8')).decode('utf-8')
                    image_payload.append({"mime": "text/plain", "data": b64_rag, "name": "rag_context.txt"})

                state_text = self.orchestrator.format_request("", project_path=self.mw.project_path, current_file_path=self.mw.current_file_path, file_content="")
                b64_state = base64.b64encode(state_text.encode('utf-8')).decode('utf-8')
                image_payload.append({"mime": "text/plain", "data": b64_state, "name": "project_state.txt"})

                final_prompt_text = user_text + "\n\n[СИСТЕМНОЕ НАПОМИНАНИЕ: Правила проекта, структура папок, код файлов и RAG-контекст прикреплены к этому сообщению в виде текстовых файлов. Обязательно прочитай vibe_instructions.txt перед ответом и отвечай СТРОГО в формате JSON Оркестратора. Не используй Markdown-заглушки.]"
            else:
                # ФОРМИРУЕМ ЛЕГКИЙ КОНТЕКСТ ДЛЯ БОЛТАЛКИ
                chat_rules = tools_instruction + "Ты — умный AI-помощник разработчика. Отвечай на вопросы пользователя в свободном формате (Markdown). Пиши понятно, приводи примеры кода, если нужно. НИКАКИХ JSON-структур."
                b64_rules = base64.b64encode(chat_rules.encode('utf-8')).decode('utf-8')
                image_payload.append({"mime": "text/plain", "data": b64_rules, "name": "vibe_chat_rules.txt"})
                
                final_prompt_text = user_text + "\n\n[СИСТЕМНОЕ НАПОМИНАНИЕ: Мы находимся в режиме 'Чат'. Отвечай обычным текстом (Markdown), JSON-структура НЕ нужна. Прикрепленные файлы (если есть) нужны только для контекста вопроса.]"

            self.mw.last_full_prompt = final_prompt_text
            
            self.agent_trace.append({"title": f"Исходный запрос ({mode_notice})", "content": final_prompt_text})
            self.mw.tokens_sent += self.estimate_tokens(final_prompt_text)
            self.mw.update_status_bar()
            self.retry_count = 0 
            self.mw.prompt_input.clear()
            self.mw.attachment_panel.clear() 

            self.bridge.add_task(self.mw.last_full_prompt, is_relay=False, target_id=target_id, images=image_payload)
            self.mw.log_system(f"Задача отправлена во вкладку '{tab_display_name}'. Режим: {mode_notice}.")
            
        else:
            # Логика для API
            enriched_text = user_text
            if tools_schema := self.mcp_manager.get_tools_schema():
                tools_instruction = (
                    "\n\n--- ДОСТУПНЫЕ ИНСТРУМЕНТЫ (MCP) ---\n"
                    "У тебя есть доступ к внешним инструментам (Context7, Поиск, БД).\n"
                    "АБСОЛЮТНЫЙ ПРИОРИТЕТ: Если тебе нужно вызвать инструмент, ВЕРНИ ТОЛЬКО ОДИН JSON в формате:\n"
                    '{"tool": "имя_инструмента", "args": {"ключ": "значение"}}\n'
                    "Список инструментов:\n" + json.dumps(tools_schema, ensure_ascii=False, indent=2)
                )
                enriched_text = tools_instruction + "\n\n" + enriched_text
            
            if rag_context_str:
                enriched_text += "\n\n" + rag_context_str

            final_prompt_text = enriched_text + ("\n\n[СИСТЕМНЫЙ БЛОК: ПРИКРЕПЛЕННЫЙ КОД]\n" + "\n\n".join(attached_blocks_text) + "\n[КОНЕЦ СИСТЕМНОГО БЛОКА]" if attached_blocks_text else "")
            
            if is_coding_mode:
                self.mw.last_full_prompt = self.orchestrator.format_request(user_prompt=final_prompt_text, project_path=self.mw.project_path, current_file_path=self.mw.current_file_path, file_content="")
                active_sys_prompt = self.orchestrator.system_prompt
            else:
                self.mw.last_full_prompt = final_prompt_text
                active_sys_prompt = "Ты — умный AI-помощник разработчика. Отвечай на вопросы пользователя в свободном формате (Markdown). Пиши понятно, приводи примеры кода, если нужно."
            
            self.agent_trace.append({"title": f"Исходный запрос API ({mode_notice})", "content": self.mw.last_full_prompt})
            self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
            self.mw.update_status_bar()
            self.retry_count = 0 
            self.mw.prompt_input.clear()
            self.mw.attachment_panel.clear() 

            self.execute_api_task(provider_id, selected_model, image_paths, active_sys_prompt)

    def execute_api_task(self, provider_id, selected_model, image_paths=None, sys_prompt=""):
        if not sys_prompt:
            sys_prompt = self.orchestrator.system_prompt
            
        settings = QSettings("VibeCoder", "API_Config")
        provider = None
        try:
            if provider_id == "OpenAI":
                key, url = settings.value("openai_api_key", ""), settings.value("openai_base_url", "https://api.openai.com/v1")
                if not key: raise Exception("API ключ OpenAI не задан! Откройте ⚙️ API.")
                provider = OpenAIProvider(key, url)
            elif provider_id == "Anthropic":
                key, url = settings.value("anthropic_api_key", ""), settings.value("anthropic_base_url", "https://api.anthropic.com")
                if not key: raise Exception("API ключ Anthropic не задан! Откройте ⚙️ API.")
                provider = AnthropicProvider(key, url)
            elif provider_id == "Gemini":
                key = settings.value("gemini_api_key", "")
                if not key: raise Exception("API ключ Gemini не задан! Откройте ⚙️ API.")
                provider = GeminiAPIProvider(key)
            else:
                custom_providers = json.loads(settings.value("custom_providers", "[]"))
                found = next((p for p in custom_providers if p['id'] == provider_id), None)
                if not found: raise Exception(f"Неизвестный провайдер: {provider_id}")
                if not found['key']: self.mw.log_system(f"Внимание: Ключ для {found['name']} пуст.", color="#ffaa00")
                provider = OpenAIProvider(found['key'], found['url'])

            if provider:
                media_log = f" и {len(image_paths)} картинками" if image_paths else ""
                self.mw.log_system(f"Отправка запроса{media_log} через API (Модель: {selected_model})...")
                original_generate = provider.generate
                provider.generate = lambda p, sp: original_generate(p, sp, model=selected_model, image_paths=image_paths)
                
                self.worker = APIWorker(provider, self.mw.last_full_prompt, sys_prompt, mcp_manager=self.mcp_manager)
                self.worker.finished_signal.connect(self.process_ai_response)
                self.worker.error_signal.connect(lambda err: self.mw.log_system(f"ОШИБКА API: {err}", color="#ff4444", is_bold=True))
                self.worker.log_signal.connect(lambda msg: self.mw.log_system(msg))
                self.worker.start()
        except Exception as e:
            self.mw.show_popup("Ошибка конфигурации API", str(e), is_error=True)
            self.mw.log_system(f"Сбой запуска API: {str(e)}", color="#ff4444", is_bold=True)

    def request_ai_commit_message(self, diff_text):
        self.is_waiting_for_commit_msg = True 
        if len(diff_text) > 10000:
            diff_text = diff_text[:10000] + "\n...[DIFF СЛИШКОМ БОЛЬШОЙ, ОБРЕЗАН]..."

        engine_data = self.mw.get_selected_engine_data()
        is_browser = engine_data.get("provider_id", "Browser") == "Browser"

        marker = '`' * 3
        
        # Исправление: код diff теперь передается прямо внутри текстового промпта.
        prompt = (
            "Сгенерируй короткое, профессиональное сообщение для Git коммита на основе предоставленного Diff кода.\n"
            "Выдай ТОЛЬКО текст коммита обычным текстом (Markdown). НЕ ИСПОЛЬЗУЙ JSON! Пиши на русском языке, используй общепринятые префиксы (feat:, fix:, refactor:).\n\n"
            f"=== DIFF КОД ===\n{marker}diff\n{diff_text}\n{marker}\n"
        )

        self.mw.log_system("Запрос ИИ-коммита...")
        self.mw.chat_history.append(f"<br><span style='color: #673ab7;'><b>[СИСТЕМА] Отправка diff для генерации ИИ-коммита...</b></span>")
        self.mw.scroll_chat()

        if is_browser:
            self.mw.last_full_prompt = prompt
            
            self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
            self.mw.update_status_bar()
            self.retry_count = 0
            
            # Отправляем ПРОСТО текст, без виртуальных файлов (images=None)
            self.bridge.add_task(self.mw.last_full_prompt, target_id=self.mw.get_current_target_id())
        else:
            self.mw.last_full_prompt = self.orchestrator.format_request(
                user_prompt=prompt, 
                project_path=self.mw.project_path, current_file_path=None, file_content=""
            )
            self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
            self.mw.update_status_bar()
            self.retry_count = 0
            sys_prompt = "Ты — профессиональный программист, генерирующий идеальные коммиты."
            self.execute_api_task(engine_data.get("provider_id"), engine_data.get("model"), sys_prompt=sys_prompt)

    def force_relay(self):
        self.is_waiting_for_relay_msg = True
        prompt = (
            "[СИСТЕМНАЯ КОМАНДА: ФОРМИРОВАНИЕ ТРАНЗИТНОГО ПАКЕТА]\n"
            "Наша сессия подходит к концу из-за исчерпания контекста/лимитов. Твоя задача — передать дела своему 'сменщику'.\n"
            "Проанализируй всю нашу текущую переписку и составь максимально подробный бриф для продолжения работы.\n\n"
            "ОТВЕЧАЙ ОБЫЧНЫМ ТЕКСТОМ (Markdown), НЕ ИСПОЛЬЗУЙ JSON. Строго следуй этой структуре:\n"
            "1. Глобальная цель: Кратко, что за проект мы пишем.\n"
            "2. Архитектурные правила: Какие технологии используем.\n"
            "3. Текущий прогресс: Что уже успешно реализовано и работает.\n"
            "4. Точка прерывания: На чем конкретно мы остановились прямо сейчас?\n"
            "5. План действий (Next Steps): Четкие инструкции для следующего ИИ.\n"
        )
        
        self.mw.log_system("Запрос транзитного пакета у ИИ...")
        self.mw.chat_history.append("<br><span style='color: #005f73;'><b>[СИСТЕМА] Сбор Транзитного Пакета (эстафеты)...</b></span>")
        self.mw.scroll_chat()

        self.mw.last_full_prompt = self.orchestrator.format_request(
            user_prompt=prompt, project_path=self.mw.project_path, current_file_path=self.mw.current_file_path, file_content=""
        )
        
        self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
        self.mw.update_status_bar()
        self.retry_count = 0
        
        engine_data = self.mw.get_selected_engine_data()
        if engine_data.get("provider_id") == "Browser":
            self.bridge.add_task(self.mw.last_full_prompt, target_id=self.mw.get_current_target_id())
        else:
            self.execute_api_task(engine_data.get("provider_id"), engine_data.get("model"), sys_prompt="Ты — координатор проекта. Формируй брифы четко.")

    def send_requested_files(self, file_paths):
        engine_data = self.mw.get_selected_engine_data()
        is_browser = engine_data.get("provider_id", "Browser") == "Browser"

        self.mw.chat_logger.log("SYSTEM", f"Авто-отправка файлов: {', '.join(file_paths)}")
        self.mw.chat_history.append(f"<br><div style='color: #858585; font-size: 13px; margin-left: 10px;'>[СИСТЕМА] Автоматически отправлены: {', '.join(file_paths)}</div>")
        self.mw.scroll_chat()

        if is_browser:
            image_payload = []
            for path in file_paths:
                content = self.mw.get_file_content_safe(path)
                if content:
                    b64_data = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                    image_payload.append({"mime": "text/plain", "data": b64_data, "name": os.path.basename(path)})

            system_text = "[СИСТЕМНОЕ СООБЩЕНИЕ]\nПользователь предоставил запрошенные файлы. Они прикреплены к этому сообщению.\nПроанализируй их и выполни предыдущую задачу. Не забывай отвечать в формате JSON Оркестратора."
            self.mw.last_full_prompt = system_text

            self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
            self.mw.update_status_bar()
            self.retry_count = 0

            self.bridge.add_task(self.mw.last_full_prompt, target_id=self.mw.get_current_target_id(), images=image_payload)
            self.mw.log_system("Файлы отправлены как вложения. Ожидание ответа...")
        else:
            marker = '`' * 3
            attached_blocks = []
            for path in file_paths:
                content = self.mw.get_file_content_safe(path)
                if content: 
                    attached_blocks.append("### ФАЙЛ: " + path + " ###\n" + marker + "\n" + content + "\n" + marker)
                else:
                    attached_blocks.append("### ФАЙЛ: " + path + " ###\n[ФАЙЛ НЕ НАЙДЕН ИЛИ ПУСТ]")
            
            system_text = "[СИСТЕМНОЕ СООБЩЕНИЕ: ПОЛЬЗОВАТЕЛЬ ПРЕДОСТАВИЛ ЗАПРОШЕННЫЕ ФАЙЛЫ]\n\n" + "\n\n".join(attached_blocks) + "\n\nПроанализируй их и выполни предыдущую задачу."
            
            self.mw.last_full_prompt = self.orchestrator.format_request(
                user_prompt=system_text, project_path=self.mw.project_path, current_file_path=self.mw.current_file_path, file_content=""
            )
            self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
            self.mw.update_status_bar()
            self.retry_count = 0 
            self.execute_api_task(engine_data.get("provider_id"), engine_data.get("model"))

    def process_limit_reached(self):
        if not self.mw.btn_pause.isChecked():
            self.mw.btn_pause.setChecked(True)
            self.mw.toggle_pause()
            
        self.mw.log_system("🚨 Внимание: Получен сигнал об изменении лимитов Gemini!", color="#ffaa00", is_bold=True)
        
        msg = QMessageBox(self.mw)
        msg.setWindowTitle("⚠️ Лимиты Gemini Pro")
        msg.setText(
            "Похоже, лимиты продвинутой версии (Pro) исчерпаны, и чат перешел на быструю версию (Flash).\n\n"
            "Flash-версия хуже справляется со сложным кодом и может нарушать формат JSON.\n"
            "Что делаем дальше?"
        )
        
        btn_relay = msg.addButton("🔄 Собрать Эстафету", QMessageBox.ButtonRole.AcceptRole)
        btn_continue = msg.addButton("⚡ Продолжить на Flash", QMessageBox.ButtonRole.RejectRole)
        
        msg.setStyleSheet("QMessageBox { background-color: #252526; color: #d4d4d4; } QLabel { color: #d4d4d4; font-size: 13px; } QPushButton { background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #1177bb; }")
        msg.exec()
        
        if msg.clickedButton() == btn_relay:
            self.mw.log_system("Запускаю авто-сборку Транзитного Пакета...", color="#ff4444", is_bold=True)
            self.force_relay()
        else:
            self.mw.log_system("Продолжаем работу на версии Flash. Будьте внимательны к качеству кода.", color="#31a24c", is_bold=True)
            if self.mw.btn_pause.isChecked():
                self.mw.btn_pause.setChecked(False)
                self.mw.toggle_pause()

    def _extract_thoughts_robustly(self, raw_text):
        result = self.orchestrator.parse_and_validate_response(raw_text)
        if result["status"] == "success":
            return result["data"].get("thoughts", "")

        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}') + 1
        if start_idx != -1 and end_idx != -1:
            json_str = raw_text[start_idx:end_idx]
            try:
                data = json.loads(json_str)
                return data.get("thoughts", "")
            except Exception:
                match = re.search(r'"thoughts"\s*:\s*"(.*?)"\s*,\s*"(?:request_files|create_files|updates)"', json_str, re.DOTALL)
                if match:
                    return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        
        marker = '`' * 3
        return raw_text.replace(f'{marker}json', '').replace(marker, '').strip()

    def _markdown_to_html(self, text):
        import html
        import re

        text = html.escape(text)
        text = f"<div style='color: #d4d4d4; line-height: 1.5;'>{text}</div>"

        def code_replacer(match):
            lang = match.group(1).strip()
            lang = lang.split('\n')[0].strip()
            code = match.group(2).strip('\n') 
            header = f"<div style='background-color: #2d2d2d; color: #858585; padding: 4px 10px; font-size: 11px; font-weight: bold; border-top-left-radius: 5px; border-top-right-radius: 5px;'>{lang.upper() if lang else 'CODE'}</div>"
            body = f"<pre style='margin: 0; padding: 10px; color: #d4d4d4; font-family: Consolas, monospace; font-size: 13px; white-space: pre-wrap;'>{code}</pre>"
            return f"</div><div style='background-color: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 5px; margin: 10px 0;'>{header}{body}</div><div style='color: #d4d4d4; line-height: 1.5;'>"

        text = re.sub(r'`{3}(.*?)\n(.*?)`{3}', code_replacer, text, flags=re.DOTALL)
        text = re.sub(r'`(.*?)`', r"<code style='background-color: #3c3c3c; color: #ce9178; padding: 2px 5px; border-radius: 4px; font-family: Consolas, monospace;'>\1</code>", text)
        text = re.sub(r'\*\*(.*?)\*\*', r"<b style='color: #ffffff;'>\1</b>", text)

        parts = re.split(r'(<pre.*?</pre>)', text, flags=re.DOTALL)
        for i in range(len(parts)):
            if not parts[i].startswith('<pre'):
                parts[i] = parts[i].replace('\n', '<br>')

        return "".join(parts)

    def process_ai_response(self, raw_text):
        if "You've reached your Pro model limit" in raw_text or "Limit resets" in raw_text:
            self.process_limit_reached()
            return
        
        if self.is_waiting_for_relay_msg:
            self.is_waiting_for_relay_msg = False
            self.retry_count = 0
            self.mw.tokens_received += self.estimate_tokens(raw_text)
            self.mw.update_status_bar()
            
            ai_summary = self._extract_thoughts_robustly(raw_text)
            if not ai_summary:
                self.mw.show_popup("Ошибка Эстафеты", "ИИ не смог собрать пакет.\nПридется переносить историю вручную.", is_error=True)
                return
                
            mega_prompt = (
                "Привет! Это транзитный пакет (эстафета) из предыдущего чата. Мы продолжаем работу над нашим проектом.\n\n"
                "=== БРИФ ОТ ПРЕДЫДУЩЕГО ИИ (СТАТУС И ПЛАН) ===\n"
                f"{ai_summary}\n\n"
                "Пожалуйста, внимательно прочитай бриф и вникай в архитектуру.\n"
                "Ответь обычным текстом: 'Контекст принял, план ясен, готов к работе.' НЕ используй JSON."
            )
            
            clipboard = QApplication.clipboard()
            clipboard.setText(mega_prompt)
            
            self.mw.chat_history.append("<span style='color: #31a24c;'><b>[СИСТЕМА] Транзитный пакет успешно скопирован в буфер обмена!</b></span>")
            self.mw.scroll_chat()
            self.mw.show_popup("Эстафета готова!", "Мега-промпт успешно скопирован в буфер обмена!\n\nВставьте его в новый чат Gemini.")
            return
            
        if self.is_waiting_for_commit_msg:
            self.is_waiting_for_commit_msg = False
            self.retry_count = 0
            self.mw.tokens_received += self.estimate_tokens(raw_text)
            self.mw.update_status_bar()
            
            commit_msg = self._extract_thoughts_robustly(raw_text)
            if not commit_msg:
                 commit_msg = "Автоматический коммит (не удалось распарсить ответ ИИ)"
                 
            safe_msg = commit_msg.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
            self.mw.chat_history.append(f"<br><span style='color: #4CAF50;'><b>[ИИ-Коммит]:</b><br>{safe_msg}</span>")
            self.mw.chat_logger.log("AI", f"Сгенерирован коммит:\n{commit_msg}")
            self.mw.scroll_chat()
            
            if hasattr(self.mw, 'current_git_dialog') and self.mw.current_git_dialog and self.mw.current_git_dialog.isVisible():
                self.mw.current_git_dialog.text_input.setPlainText(commit_msg)
                self.mw.current_git_dialog.btn_ai.setText("✨ Сгенерировать ИИ-описание")
                self.mw.current_git_dialog.btn_ai.setEnabled(True)
            else:
                self.mw.open_git_dialog(prefill_msg=commit_msg)
            return

        self.mw.tokens_received += self.estimate_tokens(raw_text)
        self.mw.update_status_bar()

        step_suffix = f" (Шаг {self.browser_mcp_step + 1})" if self.browser_mcp_step > 0 else ""
        self.agent_trace.append({"title": f"Ответ от ИИ{step_suffix}", "content": raw_text})

        marker = '`' * 3
        clean_result = raw_text.replace(f'{marker}json', '').replace(marker, '').strip()
        command = self._extract_first_json(clean_result)
        
        engine_data = self.mw.get_selected_engine_data()
        is_browser = engine_data.get("provider_id", "Browser") == "Browser"
        
        # Обработка MCP-вызовов (оставлена для обоих режимов на случай, если в чате потребуется поиск)
        if is_browser and command and isinstance(command, dict) and "tool" in command and "updates" not in command:
            tool_name = command.get("tool")
            args = command.get("args", {})
            self.browser_mcp_step += 1
            
            status_color = "#bb86fc" 
            self.mw.chat_history.append(f"<div style='color: {status_color}; font-style: italic; margin-left: 20px;'>⚙️ Агент (шаг {self.browser_mcp_step}): использую {tool_name}...</div>")
            self.mw.scroll_chat()

            if self.browser_mcp_step > self.max_browser_mcp_steps:
                self.mw.log_system("⚠️ Лимит шагов превышен. Запрашиваю финал.", color="#ffaa00", is_bold=True)
                self.bridge.add_task("Лимит превышен. Дай финальный ответ.", target_id=self.mw.get_current_target_id())
                return
                
            tool_result = self.mcp_manager.execute_tool(tool_name, args)
            next_prompt = (f"Результат выполнения '{tool_name}':\n---\n{tool_result}\n---\n\n"
                           f"Если информации достаточно, дай финальный ответ.")
            
            self.agent_trace.append({"title": f"Результат '{tool_name}'", "content": next_prompt})
            
            self.mw.chat_history.append(f"<div style='color: #858585; font-size: 12px; margin-left: 20px;'>📥 Данные получены, жду решения ИИ...</div>")
            self.mw.scroll_chat()
            
            self.bridge.add_task(next_prompt, target_id=self.mw.get_current_target_id())
            return

        # Парсинг ответа
        result = self.orchestrator.parse_and_validate_response(raw_text)
        
        if result["status"] == "error":
            # Если сломался JSON, но мы находимся в режиме болталки, то просто выводим текст
            if "\"updates\": [" not in raw_text and "\"create_files\": [" not in raw_text:
                formatted_thoughts = self._markdown_to_html(raw_text.strip())
                self.mw.chat_history.append(f"<div style='margin-top: 10px; margin-bottom: 10px;'><b style='color: #31a24c;'>[ОТВЕТ ИИ]:</b><br>{formatted_thoughts}</div>")
                self.mw.scroll_chat()
                return

            self.retry_count += 1
            if self.retry_count > 2:
                self.mw.log_system("ИИ не смог выдать правильный JSON. Включена АВТО-ПАУЗА.", color="#ff4444", is_bold=True)
                if not self.mw.btn_pause.isChecked():
                    self.mw.btn_pause.setChecked(True)
                    self.mw.toggle_pause()
                return

            self.mw.log_system(f"ОШИБКА ИИ: {result['error_message']}", color="#ff4444", is_bold=True)
            self.mw.log_system(f"Авто-исправление (Попытка {self.retry_count} из 2)...", color="#ffaa00")
            
            fix_prompt = (
                f"Твой предыдущий ответ вызвал ошибку парсера: {result['error_message']}\n"
                "🚨 ГЛАВНАЯ ПРИЧИНА: Ты используешь неэкранированные двойные кавычки внутри JSON-строки.\n"
                "Например, ты генерируешь: \"replace\": \" \"use server\"; \"\n"
                "Для парсера это выглядит как конец строки после слова replace, а дальше идет мусор, что ломает весь JSON.\n\n"
                "ПРАВИЛО: Внутри полей 'code', 'search' и 'replace' используй ТОЛЬКО одинарные кавычки (') для строк, импортов и HTML-атрибутов. Либо тщательно экранируй двойные (\\\").\n\n"
                "Исправь свой код (замени \" на ') и пришли валидный чистый JSON."
            )
            
            self.agent_trace.append({
                "title": f"Авто-исправление ошибки (Попытка {self.retry_count})", 
                "content": fix_prompt
            })
            
            if engine_data.get("provider_id") == "Browser":
                self.bridge.add_task(fix_prompt, target_id=self.mw.get_current_target_id())
            else:
                old_prompt = self.mw.last_full_prompt
                self.mw.last_full_prompt = fix_prompt
                self.execute_api_task(engine_data.get("provider_id"), engine_data.get("model"))
                self.mw.last_full_prompt = old_prompt
        else:
            self.retry_count = 0 
            data = result["data"]
            thoughts = data.get('thoughts', '')
            self.mw.chat_logger.log("AI", thoughts)
            
            if thoughts: 
                formatted_thoughts = self._markdown_to_html(thoughts)
                self.mw.chat_history.append(f"<div style='margin-top: 10px; margin-bottom: 10px;'><b style='color: #31a24c;'>[МЫСЛИ ИИ]:</b><br>{formatted_thoughts}</div>")
            
            requested_files = data.get("request_files", [])
            if requested_files:
                self.mw.chat_history.append(f"<span style='color: #e6a822;'><b>[ИИ ЗАПРАШИВАЕТ ФАЙЛЫ]:</b> {', '.join(requested_files)}</span>")
                self.mw.scroll_chat()
                
                msg = QMessageBox(self.mw)
                msg.setWindowTitle("🤖 Запрос контекста")
                msg.setText(f"ИИ просит предоставить код следующих файлов для работы:\n\n" + "\n".join(requested_files) + "\n\nОтправить их сейчас автоматически?")
                msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg.setStyleSheet("QMessageBox { background-color: #252526; color: #d4d4d4; } QLabel { color: #d4d4d4; font-size: 13px; } QPushButton { background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #1177bb; }")
                
                if msg.exec() == QMessageBox.StandardButton.Yes:
                    self.send_requested_files(requested_files)
                    return

            create_files = data.get("create_files", [])
            if create_files:
                from core.creation_dialog import FileCreationDialog
                dlg = FileCreationDialog(self.mw, create_files)
                if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_files:
                    for path in dlg.selected_files:
                        if not self.mw.is_path_safe(path):
                            self.mw.log_system(f"⚠️ Блокировка: ИИ попытался создать файл вне проекта ({path})", color="#ffaa00", is_bold=True)
                            continue
                            
                        abs_path = os.path.abspath(os.path.join(self.mw.project_path, path))
                        dir_name = os.path.dirname(abs_path)
                        
                        if path.endswith('/') or path.endswith('\\'):
                            os.makedirs(abs_path, exist_ok=True)
                            self.mw.log_system(f"📁 Создана папка: {path}", color="#31a24c")
                        else:
                            if dir_name: os.makedirs(dir_name, exist_ok=True)
                            if not os.path.exists(abs_path):
                                open(abs_path, 'w', encoding='utf-8').close()
                                self.mw.log_system(f"📄 Создан файл: {path}", color="#31a24c")
                    
                    self.mw.update_git_status()
            
            self.mw.proposed_updates = data.get("updates", [])
            if self.mw.proposed_updates:
                valid_updates = []
                for update in self.mw.proposed_updates:
                    rel_path = update.get("file_path", "")
                    action = update.get("action", "modify")
                    
                    if not self.mw.is_path_safe(rel_path): continue
                    abs_path = os.path.abspath(os.path.join(self.mw.project_path, rel_path))
                    
                    if action == "modify":
                        if not os.path.exists(abs_path):
                            open(abs_path, 'w', encoding='utf-8').close()
                        
                        with open(abs_path, 'r', encoding='utf-8') as f:
                            patched_code = f.read()
                            
                        changes = update.get("changes", [])
                        patch_failed = False
                        failed_search_block = ""
                        
                        for change in changes:
                            search_block = change.get("search", "").replace('\r\n', '\n')
                            replace_block = change.get("replace", "").replace('\r\n', '\n')
                            
                            if search_block == "":
                                patched_code = replace_block
                            elif search_block in patched_code:
                                patched_code = patched_code.replace(search_block, replace_block)
                            else:
                                patch_failed = True
                                failed_search_block = search_block
                                break 
                                
                        if patch_failed:
                            self.mw.log_system(f"ИИ ОШИБСЯ С КОНТЕКСТОМ! Блок не найден в {rel_path}. Запрос переделки...", color="#ffaa00", is_bold=True)
                            self.retry_count += 1
                            
                            marker = '`' * 3
                            error_prompt = (
                                "Твой ответ отклонен системой (Smart Diff Error).\n"
                                f"Я не нашел следующий блок 'search' в файле {rel_path}:\n"
                                f"{marker}python\n"
                                f"{failed_search_block}\n"
                                f"{marker}\n"
                                "Пожалуйста, скопируй ТОЧНЫЕ строки из моего исходного файла в поле 'search'. Или оставь 'search' пустым, если пишешь файл с нуля. Повтори JSON."
                            )
                            
                            self.agent_trace.append({
                                "title": f"Запрос переделки Smart Diff (Попытка {self.retry_count})", 
                                "content": error_prompt
                            })
                            
                            engine_data = self.mw.get_selected_engine_data()
                            if engine_data.get("provider_id") == "Browser":
                                self.bridge.add_task(error_prompt, target_id=self.mw.get_current_target_id())
                            else:
                                old_prompt = self.mw.last_full_prompt
                                self.mw.last_full_prompt = error_prompt
                                self.execute_api_task(engine_data.get("provider_id"), engine_data.get("model"))
                                self.mw.last_full_prompt = old_prompt
                            return
                        
                        update["code"] = patched_code
                    
                    valid_updates.append(update)
                
                self.mw.proposed_updates = valid_updates
                
                if self.mw.proposed_updates:
                    self.mw.btn_reject_main.setVisible(True)
                    self.mw.btn_approve.setText(f"✅ Ревью (Файлов: {len(self.mw.proposed_updates)})")
                    self.mw.log_system(f"ИИ предлагает изменить {len(self.mw.proposed_updates)} файл(а). Жмите Ревью.", color="#31a24c", is_bold=True)
                    
        self.mw.scroll_chat()