import os


class FileOpsHandler:
    """
    Сервис инкапсуляции операций с файловой системой и безопасности путей.
    Отвечает за проверку Path Traversal, создание файлов/папок и накатывание Smart Diff.
    """

    def __init__(self, controller):
        self.ctrl = controller

    def is_path_safe(self, file_path):
        """Делегирует проверку безопасности пути главному окну / CodeApplier"""
        return self.ctrl.mw.is_path_safe(file_path)

    def process_created_files(self, create_files_list):
        """
        Обрабатывает запрос на создание файлов/папок от ИИ.
        Открывает диалог подтверждения и физически создает одобренные элементы.
        """
        from core.creation_dialog import FileCreationDialog
        from PyQt6.QtWidgets import QDialog

        dlg = FileCreationDialog(self.ctrl.mw, create_files_list)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_files:
            for path in dlg.selected_files:
                if not self.is_path_safe(path):
                    log_func = (
                        self.ctrl.mw.chat_handler.log_system
                        if hasattr(self.ctrl.mw, "chat_handler")
                        else self.ctrl.mw.log_system
                    )
                    log_func(
                        f"⚠️ Блокировка: ИИ попытался создать файл вне проекта ({path})",
                        color="#ffaa00",
                        is_bold=True,
                    )
                    continue

                abs_path = os.path.abspath(
                    os.path.join(self.ctrl.mw.project_path, path)
                )
                dir_name = os.path.dirname(abs_path)

                if path.endswith("/") or path.endswith("\\"):
                    os.makedirs(abs_path, exist_ok=True)
                    log_func = (
                        self.ctrl.mw.chat_handler.log_system
                        if hasattr(self.ctrl.mw, "chat_handler")
                        else self.ctrl.mw.log_system
                    )
                    log_func(f"📁 Создана папка: {path}", color="#31a24c")
                else:
                    if dir_name:
                        os.makedirs(dir_name, exist_ok=True)
                    if not os.path.exists(abs_path):
                        with open(
                            abs_path, "w", encoding="utf-8"
                        ) as f:
                            pass
                        log_func = (
                            self.ctrl.mw.chat_handler.log_system
                            if hasattr(self.ctrl.mw, "chat_handler")
                            else self.ctrl.mw.log_system
                        )
                        log_func(f"📄 Создан файл: {path}", color="#31a24c")

            self.ctrl.mw.update_git_status()

    def process_proposed_updates(self, updates_list, engine_data):
        """
        Применяет блоки поиска и замены (Smart Diff) к локальным файлам.
        В случае ошибки контекста запрашивает у ИИ переделку пакета.
        Возвращает список успешно сформированных (валидных) обновлений.
        """
        valid_updates = []
        for update in updates_list:
            rel_path = update.get("file_path", "")
            action = update.get("action", "modify")

            if not self.is_path_safe(rel_path):
                continue

            abs_path = os.path.abspath(
                os.path.join(self.ctrl.mw.project_path, rel_path)
            )

            if action == "modify":
                if not os.path.exists(abs_path):
                    with open(
                        abs_path, "w", encoding="utf-8"
                    ) as f:
                        pass

                with open(abs_path, "r", encoding="utf-8") as f:
                    patched_code = f.read()

                patch_failed = False
                failed_search_block = ""

                for change in update.get("changes", []):
                    search_block = change.get("search", "").replace(
                        "\r\n", "\n"
                    )
                    replace_block = change.get("replace", "").replace(
                        "\r\n", "\n"
                    )

                    if search_block == "":
                        patched_code = replace_block
                    elif search_block in patched_code:
                        patched_code = patched_code.replace(
                            search_block, replace_block
                        )
                    else:
                        patch_failed = True
                        failed_search_block = search_block
                        break

                if patch_failed:
                    log_func = (
                        self.ctrl.mw.chat_handler.log_system
                        if hasattr(self.ctrl.mw, "chat_handler")
                        else self.ctrl.mw.log_system
                    )
                    log_func(
                        f"ИИ ОШИБСЯ С КОНТЕКСТОМ! Блок не найден в {rel_path}. Запрос переделки...",
                        color="#ffaa00",
                        is_bold=True,
                    )

                    self.ctrl.retry_count += 1
                    error_prompt = (
                        self.ctrl.prompt_service.build_smart_diff_error_prompt(
                            rel_path, failed_search_block
                        )
                    )

                    self.ctrl.trace_manager.append_step(
                        f"Запрос переделки Smart Diff (Попытка {self.ctrl.retry_count})",
                        error_prompt,
                    )

                    if engine_data.get("provider_id") == "Browser":
                        self.ctrl.bridge.add_task(
                            error_prompt,
                            target_id=self.ctrl.mw.get_current_target_id(),
                        )
                    else:
                        old_prompt = self.ctrl.mw.last_full_prompt
                        self.ctrl.mw.last_full_prompt = error_prompt
                        self.ctrl.execute_api_task(
                            engine_data.get("provider_id"),
                            engine_data.get("model"),
                        )
                        self.ctrl.mw.last_full_prompt = old_prompt
                    return None  # Сигнализирует о прерывании пайплайна

                update["code"] = patched_code

            valid_updates.append(update)

        return valid_updates