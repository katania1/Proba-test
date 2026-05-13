class PromptService:
    """
    Сервис инкапсуляции объемных системных промптов, HTML-разметки алертов
    и логики сборки специализированных пакетов (отладка, коммиты, эстафета).
    """

    def __init__(self, controller):
        self.ctrl = controller

    def build_terminal_error_alert(self, error_text, trace_id):
        safe_error = (
            error_text.replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        return (
            f"<div style='border: 1px solid #d32f2f; background-color: #3b1b1b; padding: 10px; border-radius: 5px; margin: 10px 0;'>"
            f"<a href='trace://{trace_id}' style='text-decoration: none;'><b style='color: #ff4444;'>🚨 [АВТО-ОТЛАДКА] Перехвачена ошибка из системного терминала:</b></a><br><br>"
            f"<span style='color: #d4d4d4; font-family: Consolas, monospace; font-size: 12px;'>{safe_error}</span><br><br>"
            f"<b style='color: #e6a822;'>⚙️ Формирую системную задачу и передаю ИИ...</b>"
            f"</div>"
        )

    def build_terminal_error_prompt(self, error_text):
        marker = "`" * 3
        return (
            "[СИСТЕМНОЕ СООБЩЕНИЕ: АВТО-ОТЛАДКА]\n"
            "При выполнении программы в системном терминале произошла ошибка. Вот полный Traceback:\n\n"
            f"{marker}text\n{error_text}\n{marker}\n\n"
            "Проанализируй эту ошибку, найди её причину и верни JSON с исправлением кода. "
            "Если причина в отсутствии библиотеки — вызови инструмент 'run_terminal_command' (pip install ...)."
        )

    def build_commit_message_prompt(self, diff_text):
        if len(diff_text) > 10000:
            diff_text = (
                diff_text[:10000] + "\n...[DIFF СЛИШКОМ БОЛЬШОЙ, ОБРЕЗАН]..."
            )
        marker = "`" * 3
        return (
            "Сгенерируй короткое, профессиональное сообщение для Git коммита на основе предоставленного Diff кода.\n"
            "Выдай ТОЛЬКО текст коммита обычным текстом (Markdown). НЕ ИСПОЛЬЗУЙ JSON! Пиши на русском языке, используй общепринятые префиксы (feat:, fix:, refactor:).\n\n"
            f"=== DIFF КОД ===\n{marker}diff\n{diff_text}\n{marker}\n"
        )

    def build_force_relay_prompt(self):
        return (
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

    def build_requested_files_prompt(self, file_paths):
        marker = "`" * 3
        attached_blocks = []
        for path in file_paths:
            content = self.ctrl.mw.get_file_content_safe(path)
            if content:
                attached_blocks.append(
                    f"### ФАЙЛ: {path} ###\n{marker}python\n{content}\n{marker}"
                )
            else:
                attached_blocks.append(
                    f"### ФАЙЛ: {path} ###\n[ФАЙЛ НЕ НАЙДЕН ИЛИ ПУСТ]"
                )

        return (
            "[СИСТЕМНОЕ СООБЩЕНИЕ: ПОЛЬЗОВАТЕЛЬ ПРЕДОСТАВИЛ ЗАПРОШЕННЫЕ ФАЙЛЫ]\n"
            "Ниже представлен исходный код запрошенных файлов.\n"
            "Проанализируй его и выполни предыдущую задачу на поиск и замену (Smart Diff).\n"
            "Отвечай СТРОГО в формате JSON Оркестратора.\n\n"
        ) + "\n\n".join(attached_blocks)

    def build_relay_mega_prompt(self, ai_summary):
        return (
            "Привет! Это транзитный пакет (эстафета) из предыдущего чата. Мы продолжаем работу над нашим проектом.\n\n"
            "=== БРИФ ОТ ПРЕДЫДУЩЕГО ИИ (СТАТУС И ПЛАН) ===\n"
            f"{ai_summary}\n\n"
            "Пожалуйста, внимательно прочитай бриф и вникай в архитектуру.\n"
            "Ответь обычным текстом: 'Контекст принял, план ясен, готов к работе.' НЕ используй JSON."
        )

    def build_json_fix_prompt(self, err_msg):
        if (
            "Invalid control character" in err_msg
            or "control character" in err_msg
        ):
            reason_block = (
                "🚨 ГЛАВНАЯ ПРИЧИНА: Ты вставил реальный (неэкранированный) перенос строки или табуляцию прямо внутрь строкового значения JSON.\n"
                "ПРАВИЛО: Внутри JSON-полей все строки обязаны быть строго однострочными! Любые переносы строк внутри полей 'thoughts', 'search', 'replace' или 'code' должны быть записаны спецсимволом `\\n`."
            )
        else:
            reason_block = (
                "🚨 ГЛАВНАЯ ПРИЧИНА: Ты используешь неэкранированные двойные кавычки внутри JSON-строки.\n"
                "ПРАВИЛО: Внутри полей 'code', 'search' и 'replace' используй ТОЛЬКО одинарные кавычки (') для строк, импортов и HTML-атрибутов. Либо тщательно экранируй двойные (\\\")."
            )

        return (
            f"Твой предыдущий ответ вызвал ошибку парсера: {err_msg}\n"
            f"{reason_block}\n\n"
            "Исправь свой ответ и пришли валидный, чистый JSON без синтаксических ошибок."
        )

    def build_commit_message_prompt(self, diff_text):
        if len(diff_text) > 10000:
            diff_text = (
                diff_text[:10000] + "\n...[DIFF СЛИШКОМ БОЛЬШОЙ, ОБРЕЗАН]..."
            )
        marker = "`" * 3
        return (
            "Сгенерируй короткое, профессиональное сообщение для Git коммита на основе предоставленного Diff кода.\n"
            "ОТВЕЧАЙ СТРОГО СЫРЫМ ТЕКСТОМ. Без форматирования, без JSON, без markdown-блоков с обратными кавычками. "
            "Пиши на русском языке, используй общепринятые префиксы (feat:, fix:, refactor:).\n\n"
            f"=== DIFF КОД ===\n{marker}diff\n{diff_text}\n{marker}\n"
        )