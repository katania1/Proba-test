from PyQt6.QtWidgets import QMessageBox
from core.git_dialog import GitDialog

class GitWorkflow:
    def __init__(self, main_window):
        self.mw = main_window # Ссылка на главное окно

    def update_git_status(self):
        if not self.mw.git_manager.is_repo():
            self.mw.btn_git.setText("📦 Git (Инициализировать)")
            self.mw.btn_git.setStyleSheet("background-color: #4a148c; color: white; font-weight: bold; border-radius: 4px;")
            return

        status_count = self.mw.git_manager.get_status()
        if status_count == -1:
            self.mw.btn_git.setText("📦 Git (Ошибка)")
        elif status_count == 0:
            self.mw.btn_git.setText("📦 Git (Чисто)")
            self.mw.btn_git.setStyleSheet("background-color: #252526; color: #888888; font-weight: bold; border-radius: 4px;")
        else:
            self.mw.btn_git.setText(f"📦 Git (Изменено: {status_count})")
            self.mw.btn_git.setStyleSheet("background-color: #e65100; color: white; font-weight: bold; border-radius: 4px;")

    def open_git_dialog(self, prefill_msg=""):
        if not self.mw.git_manager.is_repo():
            reply = QMessageBox.question(self.mw, "Git", "В этой папке нет Git-репозитория. Инициализировать сейчас?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                success, msg = self.mw.git_manager.init_repo()
                if success:
                    self.mw.log_system("Git репозиторий инициализирован!", color="#31a24c")
                    self.update_git_status()
                else:
                    self.mw.show_popup("Ошибка", f"Не удалось инициализировать Git:\n{msg}", is_error=True)
            return

        self.mw.current_git_dialog = GitDialog(self.mw, self.mw.git_manager)
        if prefill_msg:
            self.mw.current_git_dialog.text_input.setPlainText(prefill_msg)
        self.mw.current_git_dialog.exec()
        self.mw.current_git_dialog = None