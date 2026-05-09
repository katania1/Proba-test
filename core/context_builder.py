import os
import re
import json
import base64
import mimetypes

class ContextBuilder:
    def __init__(self, ai_controller):
        self.ctrl = ai_controller
        self.mw = ai_controller.mw

    def _encode_image_base64(self, filepath):
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def build_payload(self, user_text, is_coding_mode, is_browser):
        # 1. Физические картинки
        image_paths = list(self.mw.attachment_panel.get_attachments())
        image_payload = []
        if image_paths:
            for path in image_paths:
                base64_img = self._encode_image_base64(path)
                mime_type, _ = mimetypes.guess_type(path)
                if not mime_type: mime_type = "image/jpeg"
                image_payload.append({"mime": mime_type, "data": base64_img, "name": os.path.basename(path)})

        # 2. RAG Контекст
        rag_context_str = ""
        if is_coding_mode:
            rag_context_str = self.mw.rag_controller.get_context_for_prompt(user_text)
        else:
            self.mw.log_system("💬 Режим чата: умный RAG-поиск отключен.")

        # 3. Прикрепленные файлы кода (@теги)
        # ИСПРАВЛЕНИЕ: Теперь код явно прикрепленных файлов ВСЕГДА извлекается в виде текста,
        # независимо от режима (API или Браузер), чтобы ИИ не ослеп.
        attached_blocks_text = []
        tags_in_text = re.findall(r'@\[.*?\]|@[\w\.\-\/\\]+', user_text)
        for tag in tags_in_text:
            fname = tag[1:].strip("[]")
            if fname in self.mw.attached_files:
                content = self.mw.get_file_content_safe(fname)
                if content:
                    marker = '`' * 3
                    attached_blocks_text.append(f"### ФАЙЛ: {fname} ###\n{marker}python\n{content}\n{marker}")
                    
                    # Для браузера дополнительно кидаем в VFS для отрисовки красивого чипа в UI
                    if is_browser:
                        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                        image_payload.append({"mime": "text/plain", "data": b64_content, "name": os.path.basename(fname)})

        # 4. MCP Инструменты
        tools_instruction = ""
        tools_schema = self.ctrl.mcp_manager.get_tools_schema()
        if tools_schema:
            tools_instruction = (
                "--- ДОСТУПНЫЕ ИНСТРУМЕНТЫ (MCP) ---\n"
                "У тебя есть доступ к внешним инструментам (Context7, Поиск, БД).\n"
                "АБСОЛЮТНЫЙ ПРИОРИТЕТ: Если тебе нужно вызвать инструмент, ВЕРНИ ТОЛЬКО ОДИН JSON в формате:\n"
                '{"tool": "имя_инструмента", "args": {"ключ": "значение"}}\n'
                "Список инструментов:\n" + json.dumps(tools_schema, ensure_ascii=False, indent=2) + "\n\n"
            )

        api_sys_prompt = ""
        final_prompt_text = ""

        # ==================================
        # МАРШРУТ А: Для веб-браузера (VFS)
        # ==================================
        if is_browser:
            # Добавляем текстовые блоки прикрепленных файлов прямо в промпт
            enriched_user_text = user_text
            if attached_blocks_text:
                enriched_user_text += "\n\n[СИСТЕМНЫЙ БЛОК: ИСХОДНЫЙ КОД ПРИКРЕПЛЕННЫХ ФАЙЛОВ]\n" + "\n\n".join(attached_blocks_text) + "\n[КОНЕЦ СИСТЕМНОГО БЛОКА]"

            if is_coding_mode:
                core_rules = tools_instruction + self.ctrl.orchestrator.system_prompt
                
                # Тяжелые данные пакуем в VFS-файлы, чтобы не грузить браузер
                if rag_context_str:
                    b64_rag = base64.b64encode(rag_context_str.encode('utf-8')).decode('utf-8')
                    image_payload.append({"mime": "text/plain", "data": b64_rag, "name": "rag_context.txt"})

                state_text = self.ctrl.orchestrator.format_request("", project_path=self.mw.project_path, current_file_path=self.mw.current_file_path, file_content="")
                b64_state = base64.b64encode(state_text.encode('utf-8')).decode('utf-8')
                image_payload.append({"mime": "text/plain", "data": b64_state, "name": "project_state.txt"})

                final_prompt_text = core_rules + "\n\n=== ЗАДАЧА ПОЛЬЗОВАТЕЛЯ ===\n" + enriched_user_text + "\n\n[СИСТЕМНОЕ НАПОМИНАНИЕ: Структура папок и RAG-контекст прикреплены в виде файлов (rag_context.txt и project_state.txt). Отвечай СТРОГО в формате JSON Оркестратора.]"
            else:
                chat_rules = tools_instruction + "Ты — умный AI-помощник разработчика. Отвечай на вопросы пользователя в свободном формате (Markdown). Пиши понятно, приводи примеры кода, если нужно. НИКАКИХ JSON-структур."
                final_prompt_text = chat_rules + "\n\n=== ВОПРОС ПОЛЬЗОВАТЕЛЯ ===\n" + enriched_user_text + "\n\n[СИСТЕМНОЕ НАПОМИНАНИЕ: Мы находимся в режиме 'Чат'. Отвечай обычным текстом (Markdown), JSON-структура НЕ нужна.]"

        # ==================================
        # МАРШРУТ Б: Для прямых API
        # ==================================
        else:
            enriched_text = user_text
            if tools_schema:
                enriched_text = tools_instruction + "\n\n" + enriched_text
            
            if rag_context_str:
                enriched_text += "\n\n" + rag_context_str

            if attached_blocks_text:
                enriched_text += "\n\n[СИСТЕМНЫЙ БЛОК: ПРИКРЕПЛЕННЫЙ КОД]\n" + "\n\n".join(attached_blocks_text) + "\n[КОНЕЦ СИСТЕМНОГО БЛОКА]"
            
            if is_coding_mode:
                final_prompt_text = self.ctrl.orchestrator.format_request(user_prompt=enriched_text, project_path=self.mw.project_path, current_file_path=self.mw.current_file_path, file_content="")
                api_sys_prompt = self.ctrl.orchestrator.system_prompt
            else:
                final_prompt_text = enriched_text
                api_sys_prompt = "Ты — умный AI-помощник разработчика. Отвечай на вопросы пользователя в свободном формате (Markdown). Пиши понятно, приводи примеры кода, если нужно."

        return {
            "text": final_prompt_text,
            "images": image_payload,
            "image_paths": image_paths,
            "api_sys_prompt": api_sys_prompt
        }