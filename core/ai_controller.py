import os
import re
import json
from PyQt6.QtCore import QObject, pyqtSignal, QSettings
from PyQt6.QtWidgets import QMessageBox, QApplication, QDialog

from core.ai_orchestrator import AIOrchestrator
from core.bridge import VibeBridge

# --- НОВЫЕ ИМПОРТЫ ДЛЯ ФАЗЫ 18 ---
from core.api_worker import APIWorker
from core.providers import OpenAIProvider, AnthropicProvider, GeminiAPIProvider
# ---------------------------------

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

    def start(self):
        self.bridge.start_server()

    def estimate_tokens(self, text):
        return int(len(text) / 2.5)

    def send_task(self):
        user_text = self.mw.prompt_input.toPlainText().strip()
        if not user_text: return
        
        # Получаем выбранный движок и вкладку
        engine = self.mw.combo_engine.currentText()
        target_id = self.mw.get_current_target_id()
        selected_tab = self.mw.combo_tabs.currentText()
        
        # Блокировка: если выбран браузер, а он мертв
        if "Браузер" in engine and "🔴" in selected_tab:
            self.mw.show_popup("Ошибка связи", "Нет активных вкладок браузера!\nОткройте Gemini и обновите страницу.", is_error=True)
            return

        # Сбор прикрепленных файлов
        attached_blocks = []
        tags_in_text = re.findall(r'@\[.*?\]|@[\w\.\-\/\\]+', user_text)
        for tag in tags_in_text:
            fname = tag[1:].strip("[]")
            if fname in self.mw.attached_files:
                content = self.mw.get_file_content_safe(fname)
                if content: 
                    attached_blocks.append(f"### ФАЙЛ: {fname} ###\n```\n{content}\n```")
        
        final_prompt_text = user_text + ("\n\n[СИСТЕМНЫЙ БЛОК: ПРИКРЕПЛЕННЫЙ КОД]\n" + "\n\n".join(attached_blocks) + "\n[КОНЕЦ СИСТЕМНОГО БЛОКА]" if attached_blocks else "")
        
        self.mw.chat_logger.log("USER", user_text)
        
        # Определяем красивое имя для отображения в чате (Имя вкладки или Имя API)
        if "Браузер" in engine:
            tab_display_name = selected_tab.split(" [")[0].replace("🟢 ", "")
        else:
            tab_display_name = engine.split(" ")[1] # Достаем слово "OpenAI", "Anthropic", и тд
            
        self.mw.chat_history.append(f"<br><span style='color: #569cd6;'><b>ВЫ</b> (в <i>{tab_display_name}</i>)<b>:</b> {user_text}</span>")
        self.mw.chat_history.append(f"<a href='view_prompt:last' style='color: #65676b; font-size: 10px;'>[Показать сырой промпт]</a>")
            
        file_content = "" 
        
        self.mw.last_full_prompt = self.orchestrator.format_request(
            user_prompt=final_prompt_text, 
            project_path=self.mw.project_path, 
            current_file_path=self.mw.current_file_path, 
            file_content=file_content
        )
        
        self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
        self.mw.update_status_bar()
        self.retry_count = 0 
        self.mw.prompt_input.clear()
        
        # --- РОУТИНГ ЗАДАЧИ ---
        if "Браузер" in engine:
            self.bridge.add_task(self.mw.last_full_prompt, is_relay=False, target_id=target_id)
            self.mw.log_system(f"Задача отправлена в {tab_display_name}. Ожидание ответа...")
        else:
            self.execute_api_task(engine)

    def execute_api_task(self, engine):
        """Запускает прямой запрос к API в отдельном потоке"""
        settings = QSettings("VibeCoder", "API_Config")
        provider = None
        selected_model = ""
        
        try:
            if "OpenAI" in engine:
                key = settings.value("openai_api_key", "")
                url = settings.value("openai_base_url", "https://api.openai.com/v1")
                selected_model = settings.value("openai_model", "gpt-4o")
                if not key: raise Exception("API ключ OpenAI не задан! Откройте ⚙️ API.")
                provider = OpenAIProvider(key, url)
            
            elif "Anthropic" in engine:
                key = settings.value("anthropic_api_key", "")
                url = settings.value("anthropic_base_url", "https://api.anthropic.com")
                selected_model = settings.value("anthropic_model", "claude-3-5-sonnet-20241022")
                if not key: raise Exception("API ключ Anthropic не задан! Откройте ⚙️ API.")
                provider = AnthropicProvider(key, url)
                
            elif "Gemini API" in engine:
                key = settings.value("gemini_api_key", "")
                selected_model = settings.value("gemini_model", "gemini-1.5-pro")
                if not key: raise Exception("API ключ Gemini не задан! Откройте ⚙️ API.")
                provider = GeminiAPIProvider(key)

            if provider:
                self.mw.log_system(f"Отправка запроса через {engine} (Модель: {selected_model})...")
                
                # Мы не можем передать model напрямую в APIWorker, если не меняли его подпись.
                # Сделаем костыль: подменим дефолтную генерацию через лямбду или обновим свойства самого провайдера.
                # Но проще всего просто обернуть provider.generate
                original_generate = provider.generate
                provider.generate = lambda p, sp: original_generate(p, sp, model=selected_model)
                
                self.worker = APIWorker(provider, self.mw.last_full_prompt, self.orchestrator.system_prompt)
                self.worker.finished_signal.connect(self.process_ai_response)
                self.worker.error_signal.connect(lambda err: self.mw.log_system(f"ОШИБКА API: {err}", color="#ff4444"))
                self.worker.start()
                
        except Exception as e:
            self.mw.show_popup("Ошибка конфигурации API", str(e), is_error=True)
            self.mw.log_system(f"Сбой запуска API: {str(e)}", color="#ff4444")

    def request_ai_commit_message(self, diff_text):
        self.is_waiting_for_commit_msg = True 
        
        if len(diff_text) > 10000:
            diff_text = diff_text[:10000] + "\n...[DIFF СЛИШКОМ БОЛЬШОЙ, ОБРЕЗАН]..."

        prompt = (f"Сгенерируй короткое, профессиональное сообщение для Git коммита на основе этого Diff кода:\n\n"
                  f"```diff\n{diff_text}\n```\n\n"
                  f"Напиши текст коммита в поле 'thoughts', а массив 'updates' оставь пустым []. "
                  f"Пиши на русском языке, используй общепринятые префиксы (feat:, fix:, refactor:). "
                  f"ВАЖНО: КАТЕГОРИЧЕСКИ ЗАПРЕЩАЕТСЯ использовать двойные кавычки (\") внутри текста коммита. "
                  f"Используй только одинарные (') или елочки («»).")

        self.mw.chat_logger.log("SYSTEM", "Запрос ИИ-коммита...")
        self.mw.chat_history.append(f"<br><span style='color: #673ab7;'><b>[СИСТЕМА] Отправка diff для генерации ИИ-коммита...</b></span>")
        self.mw.scroll_chat()

        self.mw.last_full_prompt = self.orchestrator.format_request(
            user_prompt=prompt,
            project_path=self.mw.project_path,
            current_file_path=None,
            file_content=""
        )

        self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
        self.mw.update_status_bar()
        self.retry_count = 0

        # РОУТИНГ ДЛЯ КОММИТА
        engine = self.mw.combo_engine.currentText()
        if "Браузер" in engine:
            self.bridge.add_task(self.mw.last_full_prompt, target_id=self.mw.get_current_target_id())
        else:
            self.execute_api_task(engine)

    def force_relay(self):
        self.is_waiting_for_relay_msg = True
        
        prompt = (
            "[СИСТЕМНАЯ КОМАНДА: ФОРМИРОВАНИЕ ТРАНЗИТНОГО ПАКЕТА]\n"
            "Наша сессия подходит к концу из-за исчерпания контекста/лимитов. Твоя задача — передать дела своему 'сменщику'.\n"
            "Проанализируй всю нашу текущую переписку и составь максимально подробный бриф для продолжения работы.\n\n"
            "Напиши текст в поле 'thoughts' (массив 'updates' оставь пустым), строго следуя этой структуре:\n"
            "1. Глобальная цель: Кратко, что за проект мы пишем.\n"
            "2. Архитектурные правила: Какие технологии используем.\n"
            "3. Текущий прогресс: Что уже успешно реализовано и работает.\n"
            "4. Точка прерывания: На чем конкретно мы остановились прямо сейчас?\n"
            "5. План действий (Next Steps): Четкие инструкции для следующего ИИ.\n\n"
            "ВАЖНО: КАТЕГОРИЧЕСКИ ЗАПРЕЩАЕТСЯ использовать двойные кавычки (\") внутри текста! Используй только одинарные (') или елочки («»)."
        )
        
        self.mw.chat_logger.log("SYSTEM", "Запрос транзитного пакета у ИИ...")
        self.mw.chat_history.append("<br><span style='color: #005f73;'><b>[СИСТЕМА] Сбор Транзитного Пакета (эстафеты)...</b></span>")
        self.mw.scroll_chat()

        self.mw.last_full_prompt = self.orchestrator.format_request(
            user_prompt=prompt,
            project_path=self.mw.project_path,
            current_file_path=self.mw.current_file_path,
            file_content=""
        )
        
        self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
        self.mw.update_status_bar()
        self.retry_count = 0
        
        # РОУТИНГ ДЛЯ ЭСТАФЕТЫ
        engine = self.mw.combo_engine.currentText()
        if "Браузер" in engine:
            self.bridge.add_task(self.mw.last_full_prompt, target_id=self.mw.get_current_target_id())
        else:
            self.execute_api_task(engine)

    def send_requested_files(self, file_paths):
        attached_blocks = []
        for path in file_paths:
            fname = os.path.basename(path)
            content = self.mw.get_file_content_safe(path)
            if content: 
                attached_blocks.append(f"### ФАЙЛ: {path} ###\n```\n{content}\n```")
            else:
                attached_blocks.append(f"### ФАЙЛ: {path} ###\n[ФАЙЛ НЕ НАЙДЕН ИЛИ ПУСТ]")
        
        system_text = "[СИСТЕМНОЕ СООБЩЕНИЕ: ПОЛЬЗОВАТЕЛЬ ПРЕДОСТАВИЛ ЗАПРОШЕННЫЕ ФАЙЛЫ]\n\n" + "\n\n".join(attached_blocks) + "\n\nПроанализируй их и выполни предыдущую задачу."
        
        self.mw.chat_logger.log("SYSTEM", f"Авто-отправка файлов: {', '.join(file_paths)}")
        self.mw.chat_history.append(f"<br><span style='color: #0e639c;'><b>[СИСТЕМА] Автоматически отправлены:</b> {', '.join(file_paths)}</span>")
        self.mw.scroll_chat()
        
        self.mw.last_full_prompt = self.orchestrator.format_request(
            user_prompt=system_text, 
            project_path=self.mw.project_path, 
            current_file_path=self.mw.current_file_path, 
            file_content=""
        )
        
        self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
        self.mw.update_status_bar()
        self.retry_count = 0 
        
        # РОУТИНГ ДЛЯ ФАЙЛОВ
        engine = self.mw.combo_engine.currentText()
        if "Браузер" in engine:
            self.bridge.add_task(self.mw.last_full_prompt, target_id=self.mw.get_current_target_id())
            self.mw.log_system("Файлы отправлены. Ожидание ответа...")
        else:
            self.execute_api_task(engine)

    def process_limit_reached(self):
        if not self.mw.btn_pause.isChecked():
            self.mw.btn_pause.setChecked(True)
            self.mw.toggle_pause()
        self.mw.log_system("🚨 ЛИМИТЫ GEMINI ИСЧЕРПАНЫ! Запускаю авто-сборку Транзитного Пакета...", color="#ff4444")
        self.force_relay()

    # --- БРОНЕБОЙНЫЙ ЭКСТРАКТОР ТЕКСТА ---
    def _extract_thoughts_robustly(self, raw_text):
        """Извлекает текст thoughts, обходя строгие правила валидатора кода"""
        result = self.orchestrator.parse_and_validate_response(raw_text)
        if result["status"] == "success":
            return result["data"].get("thoughts", "")

        # Если валидатор забраковал (пустые updates или кривые переносы), парсим жестко
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}') + 1
        if start_idx != -1 and end_idx != -1:
            json_str = raw_text[start_idx:end_idx]
            try:
                data = json.loads(json_str)
                return data.get("thoughts", "")
            except Exception:
                # Если JSON сломан неэкранированными \n, выдираем регуляркой
                match = re.search(r'"thoughts"\s*:\s*"(.*?)"\s*,\s*"(?:request_files|create_files|updates)"', json_str, re.DOTALL)
                if match:
                    return match.group(1).replace('\\n', '\n').replace('\\"', '"')
                    
        return raw_text.replace('```json', '').replace('```', '').strip()

    def process_ai_response(self, raw_text):
        # --- ПЕРЕХВАТ ТРАНЗИТНОГО ПАКЕТА (ЭСТАФЕТЫ) ---
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
                "Для ответа используй СТРОГИЙ ФОРМАТ JSON согласно нашим правилам Оркестратора.\n"
                "В поле 'thoughts' напиши 'Контекст принял, план ясен, готов к работе', а массивы 'updates' и 'create_files' оставь пустыми []."
            )
            
            clipboard = QApplication.clipboard()
            clipboard.setText(mega_prompt)
            
            self.mw.chat_history.append("<span style='color: #31a24c;'><b>[СИСТЕМА] Транзитный пакет успешно скопирован в буфер обмена!</b></span>")
            self.mw.scroll_chat()
            
            self.mw.show_popup("Эстафета готова!", 
                            "Мега-промпт (бриф + контекст) успешно скопирован в буфер обмена!\n\n"
                            "1. Откройте новый чат Gemini (в другом браузере или аккаунте).\n"
                            "2. Выберите эту новую вкладку в VibeCoder.\n"
                            "3. Нажмите Ctrl+V прямо на сайте Gemini и отправьте.\n\n"
                            "Работа будет бесшовно продолжена!")
            return
            
        # --- ПЕРЕХВАТ ИИ-КОММИТА ---
        if self.is_waiting_for_commit_msg:
            self.is_waiting_for_commit_msg = False
            self.retry_count = 0
            self.mw.tokens_received += self.estimate_tokens(raw_text)
            self.mw.update_status_bar()
            
            commit_msg = self._extract_thoughts_robustly(raw_text)
            if not commit_msg:
                 commit_msg = "Автоматический коммит (не удалось распарсить ответ ИИ)"
                 
            # Экранируем HTML, чтобы текст 100% отобразился в чате
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
        
        # --- СТАНДАРТНАЯ ОБРАБОТКА КОДА ---
        self.mw.tokens_received += self.estimate_tokens(raw_text)
        self.mw.update_status_bar()
        self.mw.chat_history.append("<span style='color: #bb86fc;'><b>[GEMINI/API] Ответ получен. Проверка и патчинг...</b></span>")
        result = self.orchestrator.parse_and_validate_response(raw_text)
        
        if result["status"] == "error":
            self.retry_count += 1
            if self.retry_count > 2:
                self.mw.log_system("ИИ не смог выдать код. Включена АВТО-ПАУЗА.", color="#ff4444")
                if not self.mw.btn_pause.isChecked():
                    self.mw.btn_pause.setChecked(True)
                    self.mw.toggle_pause()
                return

            self.mw.log_system(f"ОШИБКА ИИ: {result['error_message']}", color="#ff4444")
            self.mw.log_system(f"Авто-исправление (Попытка {self.retry_count} из 2)...", color="#ffaa00")
            fix_prompt = (f"Твой предыдущий ответ вызвал фатальную ошибку: {result['error_message']}\nКАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать извинения вне JSON.\nВот исходная задача. Пришли чистый JSON для неё:\n{self.mw.last_full_prompt}\n")
            
            # РОУТИНГ АВТО-ИСПРАВЛЕНИЯ
            engine = self.mw.combo_engine.currentText()
            if "Браузер" in engine:
                self.bridge.add_task(fix_prompt, target_id=self.mw.get_current_target_id())
            else:
                # Временно подменяем промпт, чтобы отправить фикс через APIWorker
                old_prompt = self.mw.last_full_prompt
                self.mw.last_full_prompt = fix_prompt
                self.execute_api_task(engine)
                self.mw.last_full_prompt = old_prompt
        else:
            self.retry_count = 0 
            data = result["data"]
            thoughts = data.get('thoughts', '')
            self.mw.chat_logger.log("AI", thoughts)
            if thoughts: self.mw.chat_history.append(f"<span style='color: #31a24c;'><b>[МЫСЛИ ИИ]:</b> {thoughts}</span>")
            
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
                            self.mw.log_system(f"⚠️ Блокировка: ИИ попытался создать файл вне проекта ({path})", color="#ffaa00")
                            continue
                            
                        abs_path = os.path.abspath(os.path.join(self.mw.project_path, path))
                        dir_name = os.path.dirname(abs_path)
                        
                        if path.endswith('/') or path.endswith('\\'):
                            os.makedirs(abs_path, exist_ok=True)
                            self.mw.log_system(f"📁 Создана папка: {path}", color="#31a24c")
                        else:
                            if dir_name: 
                                os.makedirs(dir_name, exist_ok=True)
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
                    
                    if not self.mw.is_path_safe(rel_path):
                        continue

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
                            self.mw.log_system(f"ИИ ОШИБСЯ С КОНТЕКСТОМ! Блок не найден в {rel_path}. Запрос переделки...", color="#ffaa00")
                            self.retry_count += 1
                            error_prompt = f"Твой ответ отклонен системой (Smart Diff Error).\nЯ не нашел следующий блок 'search' в файле {rel_path}:\n```python\n{failed_search_block}\n```\nПожалуйста, скопируй ТОЧНЫЕ строки из моего исходного файла в поле 'search'. Или оставь 'search' пустым, если пишешь файл с нуля. Повтори JSON."
                            
                            # РОУТИНГ ФИКСА ДИФФА
                            engine = self.mw.combo_engine.currentText()
                            if "Браузер" in engine:
                                self.bridge.add_task(error_prompt, target_id=self.mw.get_current_target_id())
                            else:
                                old_prompt = self.mw.last_full_prompt
                                self.mw.last_full_prompt = error_prompt
                                self.execute_api_task(engine)
                                self.mw.last_full_prompt = old_prompt
                            return
                        
                        update["code"] = patched_code
                    
                    valid_updates.append(update)
                
                self.mw.proposed_updates = valid_updates
                
                if self.mw.proposed_updates:
                    self.mw.btn_reject_main.setVisible(True)
                    self.mw.btn_approve.setText(f"✅ Ревью (Файлов: {len(self.mw.proposed_updates)})")
                    self.mw.log_system(f"ИИ предлагает изменить {len(self.mw.proposed_updates)} файл(а). Жмите Ревью.", color="#31a24c")
                    
        self.mw.scroll_chat()