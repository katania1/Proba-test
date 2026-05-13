import hashlib


class MCPHandler:
    """
    Обработчик циклов Model Context Protocol (MCP) и агентских вызовов инструментов.
    Содержит логику защиты от бесконечных циклов ("День сурка") и контроль лимита шагов.
    """

    def __init__(self, controller):
        self.ctrl = controller
        self.browser_mcp_step = 0
        self.max_browser_mcp_steps = 5
        self.auto_heal_attempts = 0
        self.last_tool_result_hash = None
        self.last_tool_name = None

    def reset_state(self):
        """Сбрасывает состояние счетчиков перед новым заданием"""
        self.browser_mcp_step = 0
        self.auto_heal_attempts = 0
        self.last_tool_result_hash = None
        self.last_tool_name = None

    def handle_tool_command(self, command):
        """
        Выполняет инструмент MCP, проверяет ошибки на зацикливание
        и отправляет результат обратно в мост связи.
        Возвращает True, если команда была распознана и обработана.
        """
        tool_name = command.get("tool")
        args = command.get("args", {})
        self.browser_mcp_step += 1

        status_color = "#bb86fc"
        self.ctrl.mw.chat_history.append(
            f"<div style='color: {status_color}; font-style: italic; margin-left: 20px;'>⚙️ Агент (шаг {self.browser_mcp_step}): использую {tool_name}...</div>"
        )

        if hasattr(self.ctrl.mw, "chat_handler"):
            self.ctrl.mw.chat_handler.scroll_chat()
        else:
            self.ctrl.mw.scroll_chat()

        if self.browser_mcp_step > self.max_browser_mcp_steps:
            log_func = (
                self.ctrl.mw.chat_handler.log_system
                if hasattr(self.ctrl.mw, "chat_handler")
                else self.ctrl.mw.log_system
            )
            log_func(
                "⚠️ Лимит шагов агента исчерпан. Запрашиваю финал.",
                color="#ffaa00",
                is_bold=True,
            )
            self.ctrl.bridge.add_task(
                "Лимит шагов агента исчерпан. Дай финальный ответ на основе того, что успел узнать.",
                target_id=self.ctrl.mw.get_current_target_id(),
            )
            return True

        tool_result = self.ctrl.mcp_manager.execute_tool(tool_name, args)

        current_hash = hashlib.md5(tool_result.encode("utf-8")).hexdigest()
        warning_block = ""

        if (
            "❌ Ошибка" in tool_result
            or "⚠️ Системная ошибка" in tool_result
            or "⛔ КОМАНДА ЗАБЛОКИРОВАНА" in tool_result
        ):
            if (
                self.last_tool_name == tool_name
                and self.last_tool_result_hash == current_hash
            ):
                self.auto_heal_attempts += 1
                warning_block = (
                    f"\n\n🚨 [КРИТИЧЕСКОЕ СИСТЕМНОЕ ПРЕДУПРЕЖДЕНИЕ: ДЕНЬ СУРКА]\n"
                    f"ТВОЕ ПРЕДЫДУЩЕЕ ДЕЙСТВИЕ ВЫЗВАЛО АБСОЛЮТНО ТУ ЖЕ ОШИБКУ (Попытка {self.auto_heal_attempts}/3).\n"
                    f"ПРАВИЛО: ПРИДУМАЙ ПРИНЦИПИАЛЬНО ДРУГОЙ ПОДХОД. Хватит повторять ту же команду!"
                )

                if self.auto_heal_attempts >= 3:
                    log_func = (
                        self.ctrl.mw.chat_handler.log_system
                        if hasattr(self.ctrl.mw, "chat_handler")
                        else self.ctrl.mw.log_system
                    )
                    log_func(
                        "⚠️ ИИ зациклился на одной ошибке. Принудительное прерывание агента.",
                        color="#ff4444",
                        is_bold=True,
                    )
                    self.ctrl.bridge.add_task(
                        "Я застрял в бесконечном цикле одних и тех же ошибок. Дай финальный ответ текстом: 'Я не смог решить проблему автоматически, нужна помощь человека'.",
                        target_id=self.ctrl.mw.get_current_target_id(),
                    )
                    return True
            else:
                self.auto_heal_attempts = 1
        else:
            self.auto_heal_attempts = 0

        self.last_tool_name = tool_name
        self.last_tool_result_hash = current_hash

        next_prompt = f"Результат выполнения '{tool_name}':\n---\n{tool_result}\n---{warning_block}\n\nЕсли информации достаточно, дай финальный ответ. Иначе - вызови следующий инструмент."

        self.ctrl.trace_manager.append_step(
            f"Результат '{tool_name}'", next_prompt
        )

        self.ctrl.mw.chat_history.append(
            "<div style='color: #858585; font-size: 12px; margin-left: 20px;'>📥 Данные получены, жду решения ИИ...</div>"
        )

        if hasattr(self.ctrl.mw, "chat_handler"):
            self.ctrl.mw.chat_handler.scroll_chat()
        else:
            self.ctrl.mw.scroll_chat()

        self.ctrl.bridge.add_task(
            next_prompt, target_id=self.ctrl.mw.get_current_target_id()
        )
        return True