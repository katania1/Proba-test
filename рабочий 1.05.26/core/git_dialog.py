import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTextEdit, QLabel, QMessageBox, QLineEdit, QFrame)

class GitDialog(QDialog):
    def __init__(self, parent, git_manager):
        super().__init__(parent)
        self.git_manager = git_manager
        self.parent_window = parent
        self.setWindowTitle("📦 Управление Git и GitHub")
        self.resize(550, 450)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")

        self.init_ui()
        self.load_remote_url()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # --- БЛОК 1: КОММИТЫ (Локально) ---
        lbl_local = QLabel("1. Локальное сохранение (Commit)")
        lbl_local.setStyleSheet("font-size: 14px; font-weight: bold; color: #569cd6;")
        layout.addWidget(lbl_local)

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

        # --- РАЗДЕЛИТЕЛЬ ---
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #3c3c3c; margin-top: 10px; margin-bottom: 10px;")
        layout.addWidget(line)

        # --- БЛОК 2: ОБЛАКО (GitHub) ---
        lbl_cloud = QLabel("2. Синхронизация с GitHub (Push)")
        lbl_cloud.setStyleSheet("font-size: 14px; font-weight: bold; color: #e6a822;")
        layout.addWidget(lbl_cloud)

        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; padding: 6px;")
        self.url_input.setPlaceholderText("https://github.com/Имя/Репозиторий.git")
        
        self.btn_link = QPushButton("🔗 Привязать")
        self.btn_link.setStyleSheet("background-color: #0e639c; color: white; font-weight: bold; padding: 6px 15px; border-radius: 4px;")
        self.btn_link.clicked.connect(self.link_remote)

        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.btn_link)
        layout.addLayout(url_layout)

        self.btn_push = QPushButton("☁️ Отправить код в облако (Push)")
        self.btn_push.setStyleSheet("background-color: #005f73; color: white; font-weight: bold; padding: 10px 15px; border-radius: 4px; font-size: 14px;")
        self.btn_push.clicked.connect(self.push_code)
        layout.addWidget(self.btn_push)

    def load_remote_url(self):
        """Загружает привязанную ссылку при открытии окна"""
        url = self.git_manager.get_remote_url()
        if url:
            self.url_input.setText(url)

    def generate_ai_commit(self):
        diff = self.git_manager.get_diff()
        if not diff:
            QMessageBox.information(self, "Пусто", "Нет изменений для генерации коммита.")
            return
        self.parent_window.request_ai_commit_message(diff)
        self.accept() 

    def make_commit(self):
        msg = self.text_input.toPlainText().strip()
        if not msg:
            QMessageBox.warning(self, "Ошибка", "Введите описание коммита!")
            return

        success, result = self.git_manager.commit_all(msg)
        if success:
            QMessageBox.information(self, "Успех", "✅ " + result)
            self.text_input.clear()
            self.parent_window.update_git_status()
            # Больше не закрываем окно автоматически, чтобы можно было сразу нажать Push
        else:
            QMessageBox.critical(self, "Ошибка Git", result)

    def link_remote(self):
        """Привязывает локальную папку к облаку"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Ошибка", "Введите ссылку на репозиторий GitHub!")
            return

        success, msg = self.git_manager.set_remote_url(url)
        if success:
            QMessageBox.information(self, "Успех", "✅ Репозиторий успешно привязан!")
        else:
            QMessageBox.critical(self, "Ошибка", f"Не удалось привязать репозиторий:\n{msg}")

    def push_code(self):
        """Отправляет коммиты на GitHub"""
        if not self.git_manager.get_remote_url():
            QMessageBox.warning(self, "Ошибка", "Сначала привяжите ссылку на репозиторий GitHub!")
            return
        
        # Меняем текст кнопки, так как интернет-запрос может занять пару секунд
        self.btn_push.setText("⏳ Отправка в облако...")
        self.btn_push.setEnabled(False)
        self.repaint() # Принудительное обновление интерфейса

        success, msg = self.git_manager.push_to_cloud()
        
        self.btn_push.setText("☁️ Отправить код в облако (Push)")
        self.btn_push.setEnabled(True)

        if success:
            QMessageBox.information(self, "Успех", "✅ Код успешно отправлен в GitHub!")
        else:
            QMessageBox.critical(self, "Ошибка Push", f"Не удалось отправить код:\n{msg}\n\nВозможно, нужно авторизоваться в браузере или репозиторий не пустой.")