import difflib
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, 
                             QHBoxLayout, QPushButton, QLabel)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt

class DiffDialog(QDialog):
    def __init__(self, parent, old_text, new_text, file_path):
        super().__init__(parent)
        self.setWindowTitle(f"Ревью изменений: {file_path}")
        self.resize(1000, 700)
        self.setModal(True) # Окно блокирует остальной интерфейс, пока вы не примете решение
        
        # Устанавливаем темный стиль для самого окна
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        layout = QVBoxLayout(self)
        
        # Заголовок
        lbl = QLabel(f"<b>Файл:</b> {file_path}")
        lbl.setStyleSheet("font-size: 14px; margin-bottom: 5px;")
        layout.addWidget(lbl)
        
        # Текстовое поле для HTML-разметки
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3c3c3c;")
        layout.addWidget(self.text_edit)
        
        # Генерируем красивый цветной Diff
        self.generate_diff_html(old_text, new_text)
        
        # Кнопки управления
        btn_layout = QHBoxLayout()
        
        self.btn_reject = QPushButton("Отклонить (Esc)")
        self.btn_reject.setStyleSheet("background-color: #512525; color: white; padding: 10px; font-weight: bold;")
        
        self.btn_approve = QPushButton("Утвердить и Сохранить (Enter)")
        self.btn_approve.setStyleSheet("background-color: #2e7d32; color: white; padding: 10px; font-weight: bold;")
        
        self.btn_reject.clicked.connect(self.reject)  # Встроенный метод закрытия с отказом
        self.btn_approve.clicked.connect(self.accept) # Встроенный метод закрытия с успехом
        
        btn_layout.addWidget(self.btn_reject)
        btn_layout.addWidget(self.btn_approve)
        layout.addLayout(btn_layout)

    def generate_diff_html(self, old_text, new_text):
        """Сравнивает тексты и превращает их в цветной HTML-код"""
        diff = list(difflib.ndiff(old_text.splitlines(), new_text.splitlines()))
        
        html = "<div style='font-family: Consolas, monospace; font-size: 13px; white-space: pre-wrap;'>"
        
        for line in diff:
            # Экранируем HTML-символы, чтобы код не сломал верстку окна
            safe_line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            if safe_line.startswith('+ '):
                # Добавленные ИИ строки (Зеленый фон)
                html += f"<div style='background-color: #204e26; color: #e4e6eb; padding: 2px;'>{safe_line}</div>"
            elif safe_line.startswith('- '):
                # Удаленные ИИ строки (Красный фон)
                html += f"<div style='background-color: #5a1d1d; color: #e4e6eb; padding: 2px; text-decoration: line-through;'>{safe_line}</div>"
            elif safe_line.startswith('? '):
                # Техническая строка difflib, пропускаем
                continue
            else:
                # Неизмененные строки (Серый текст)
                html += f"<div style='color: #858585; padding: 2px;'>{safe_line}</div>"
                
        html += "</div>"
        self.text_edit.setHtml(html)