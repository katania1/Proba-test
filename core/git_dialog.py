import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTextEdit, QLabel, QMessageBox)

class GitDialog(QDialog):
    def __init__(self, parent, git_manager):
        super().__init__(parent)
        self.git_manager = git_manager
        self.parent_window = parent
        self.setWindowTitle("📦 Управление Git")
        self.resize(500, 300)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        label = QLabel("Описание коммита:")
        label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(label)

        self.text_input = QTextEdit()
        self.text_input.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; font-size: 14px; padding: 10px;")
        self.text_input.setPlaceholderText("Напишите текст коммита (или нажмите '✨ Сгенерировать ИИ-описание')...")
        layout.addWidget(self.text_input)

        btn_layout = QHBoxLayout()

        self.btn_ai = QPushButton("✨ Сгенерировать ИИ-описание")
        self.btn_ai.setStyleSheet("background-color: #673ab7; color: white; font-weight: bold; padding: 8px 15px; border-radius: 4px;")
        self.btn_ai.clicked.connect(self.generate_ai_commit)

        self.btn_commit = QPushButton("✅ Сделать Commit")
        self.btn_commit.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 8px 15px; border-radius: 4px;")
        self.btn_commit.clicked.connect(self.make_commit)

        btn_layout.addWidget(self.btn_ai)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_commit)

        layout.addLayout(btn_layout)

    def generate_ai_commit(self):
        diff = self.git_manager.get_diff()
        if not diff:
            QMessageBox.information(self, "Пусто", "Нет изменений для генерации коммита.")
            return

        # Отправляем запрос Главному окну, чтобы оно передало Diff в ИИ
        self.parent_window.request_ai_commit_message(diff)
        self.accept() # Закрываем окно, ответ появится в чате!

    def make_commit(self):
        msg = self.text_input.toPlainText().strip()
        if not msg:
            QMessageBox.warning(self, "Ошибка", "Введите описание коммита!")
            return

        success, result = self.git_manager.commit_all(msg)
        if success:
            QMessageBox.information(self, "Успех", "✅ " + result)
            self.parent_window.update_git_status()
            self.accept()
        else:
            QMessageBox.critical(self, "Ошибка Git", result)