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

    def _get_project_tree(self):
        """Собирает физическую структуру проекта с защитой от переполнения памяти Chrome API и учетом .gitignore"""
        tree = ["=== СТРУКТУРА ФАЙЛОВ ПРОЕКТА ==="]
        file_count = 0
        MAX_FILES = 800  # Жесткий лимит файлов для защиты канала связи браузера
        
        # 1. Читаем пользовательские правила из .gitignore и .vibeignore
        custom_ignores = set()
        for ignore_file in ['.gitignore', '.vibeignore']:
            ignore_path = os.path.join(self.mw.project_path, ignore_file)
            if os.path.exists(ignore_path):
                try:
                    with open(ignore_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                # Берем чистые имена (без слешей), чтобы легко фильтровать папки
                                clean_name = line.strip('/\\')
                                custom_ignores.add(clean_name)
                except Exception as e:
                    self.mw.log_system(f"⚠️ Ошибка чтения {ignore_file}: {e}", color="#ffaa00")

        # 2. Системные папки, которые 100% не нужны ИИ (предохранитель)
        system_ignore_dirs = {'venv', 'env', '__pycache__', 'node_modules', '.git', '.vibecoder', 'build', 'dist'}
        
        # Объединяем списки для папок
        all_ignore_dirs = system_ignore_dirs.union(custom_ignores)
        
        # Список бинарников и медиа, которые не нужны ИИ
        ignore_exts = (
            '.pyc', '.exe', '.dll', '.so', '.png', '.jpg', '.jpeg', '.gif', 
            '.mp4', '.mp3', '.wav', '.zip', '.tar', '.gz', '.pdf', '.psd'
        )

        try:
            for root, dirs, files in os.walk(self.mw.project_path):
                if file_count >= MAX_FILES:
                    break
                    
                # Фильтруем папки НА ЛЕТУ: Игнорируем скрытые (с точкой) и все из .gitignore
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in all_ignore_dirs]
                
                level = root.replace(self.mw.project_path, '').count(os.sep)
                indent = ' ' * 4 * level
                folder_name = os.path.basename(root)
                
                if level == 0:
                    tree.append(f"📁 [Корень Проекта] {os.path.basename(self.mw.project_path)}/")
                else:
                    tree.append(f"{indent}📁 {folder_name}/")
                    
                subindent = ' ' * 4 * (level + 1)
                for f in files:
                    if file_count >= MAX_FILES:
                        tree.append(f"{subindent}... [Слишком много файлов, дерево обрезано для защиты памяти] ...")
                        break
                        
                    # Фильтруем файлы по расширению и по правилам .gitignore
                    if not f.endswith(ignore_exts) and f not in custom_ignores:
                        tree.append(f"{subindent}📄 {f}")
                        file_count += 1
                        
        except Exception as e:
            tree.append(f"Ошибка чтения структуры папок: {str(e)}")
        
        return "\n".join(tree)

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
        attached_blocks_text = []
        tags_in_text = re.findall(r'@\[.*?\]|@[\w\.\-\/\\]+', user_text)
        for tag in tags_in_text:
            fname = tag[1:].strip("[]")
            if fname in self.mw.attached_files:
                content = self.mw.get_file_content_safe(fname)
                if content:
                    marker = '`' * 3
                    attached_blocks_text.append(f"### ФАЙЛ: {fname} ###\n{marker}python\n{content}\n{marker}")
                    
                    if is_browser:
                        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                        image_payload.append({"mime": "text/plain", "data": b64_content, "name": os.path.basename(fname)})

        # 4. MCP Инструменты (ГЕНЕРИРУЕМ СТРОГО ДЛЯ РЕЖИМА КОДИНГА)
        tools_instruction = ""
        if is_coding_mode:
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
            enriched_user_text = user_text
            if attached_blocks_text:
                enriched_user_text += "\n\n[СИСТЕМНЫЙ БЛОК: ИСХОДНЫЙ КОД ПРИКРЕПЛЕННЫХ ФАЙЛОВ]\n" + "\n\n".join(attached_blocks_text) + "\n[КОНЕЦ СИСТЕМНОГО БЛОКА]"

            if is_coding_mode:
                core_rules = tools_instruction + self.ctrl.orchestrator.system_prompt
                
                if rag_context_str:
                    b64_rag = base64.b64encode(rag_context_str.encode('utf-8')).decode('utf-8')
                    image_payload.append({"mime": "text/plain", "data": b64_rag, "name": "rag_context.txt"})

                status_block = "\n\n=== ТЕКУЩИЙ СТАТУС ПРОЕКТА ===\n"
                status_block += f"Путь проекта: {self.mw.project_path}\n"
                if self.mw.current_file_path:
                    status_block += f"Активный файл в редакторе: {self.mw.current_file_path}\n"
                status_block += "==============================\n\n"

                tree_text = self._get_project_tree()
                
                # 🔥 ФИКС ИИ-ЛЕНТЯЯ: Железобетонный ультиматум в самом конце промпта
                strict_reminder = (
                    "\n\n[🚨 КРИТИЧЕСКОЕ СИСТЕМНОЕ НАПОМИНАНИЕ: ТЫ НАХОДИШЬСЯ В РЕЖИМЕ КОДИНГА! "
                    "Актуальная структура файлов представлена выше. База знаний (RAG) прикреплена как файл. "
                    "ВНИМАНИЕ: Даже если пользователь просто задает вопрос или анализирует код без изменения файлов, "
                    "ТЫ ОБЯЗАН ответить СТРОГО валидным JSON-объектом. Свои мысли и текстовые ответы пиши в поле \"thoughts\", "
                    "а массивы файлов оставляй пустыми. ОТВЕТЫ ОБЫЧНЫМ ТЕКСТОМ (MARKDOWN) СТРОГО ЗАПРЕЩЕНЫ И СЛОМАЮТ СИСТЕМУ!]"
                )

                final_prompt_text = (
                    core_rules + 
                    status_block + 
                    tree_text + 
                    "\n\n=== ЗАДАЧА ПОЛЬЗОВАТЕЛЯ ===\n" + 
                    enriched_user_text + 
                    strict_reminder
                )
            else:
                # ИНТЕГРАЦИЯ: В режиме чата ИИ получает абсолютно чистый и легкий промпт без MCP
                chat_rules = "Ты — умный AI-помощник разработчика. Отвечай на вопросы пользователя в свободном формате (Markdown). Пиши понятно, приводи примеры кода, если нужно. НИКАКИХ JSON-структур."
                final_prompt_text = chat_rules + "\n\n=== ВОПРОС ПОЛЬЗОВАТЕЛЯ ===\n" + enriched_user_text + "\n\n[СИСТЕМНОЕ НАПОМИНАНИЕ: Мы находимся в режиме 'Чат'. Отвечай обычным текстом (Markdown), JSON-структура НЕ нужна.]"

        # ==================================
        # МАРШРУТ Б: Для прямых API
        # ==================================
        else:
            enriched_text = user_text
            if tools_instruction:
                enriched_text = tools_instruction + "\n\n" + enriched_text
            
            if rag_context_str:
                enriched_text += "\n\n" + rag_context_str

            if attached_blocks_text:
                enriched_text += "\n\n[СИСТЕМНЫЙ БЛОК: ПРИКРЕПЛЕННЫЙ КОД]\n" + "\n\n".join(attached_blocks_text) + "\n[КОНЕЦ СИСТЕМНОГО БЛОКА]"
            
            if is_coding_mode:
                tree_text = self._get_project_tree()
                
                # 🔥 ФИКС ИИ-ЛЕНТЯЯ для прямого API
                strict_reminder = (
                    "\n\n[🚨 КРИТИЧЕСКОЕ СИСТЕМНОЕ НАПОМИНАНИЕ: ТЫ НАХОДИШЬСЯ В РЕЖИМЕ КОДИНГА! "
                    "ВНИМАНИЕ: Даже если пользователь просто задает вопрос без изменения файлов, "
                    "ТЫ ОБЯЗАН ответить СТРОГО валидным JSON-объектом. Свои мысли и ответы пиши в поле \"thoughts\", "
                    "а массивы файлов оставляй пустыми. ОТВЕТЫ ОБЫЧНЫМ ТЕКСТОМ ЗАПРЕЩЕНЫ!]"
                )

                full_api_prompt = enriched_text + "\n\n" + tree_text + strict_reminder
                
                final_prompt_text = self.ctrl.orchestrator.format_request(user_prompt=full_api_prompt, project_path=self.mw.project_path, current_file_path=self.mw.current_file_path, file_content="")
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