import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, 
                             QPushButton, QLabel, QScrollArea, QWidget)

class FileCreationDialog(QDialog):
    def __init__(self, parent, files_list):
        super().__init__(parent)
        self.setWindowTitle("✨ ИИ предлагает создать структуру")
        self.resize(450, 350)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-size: 14px;")
        self.selected_files = []

        layout = QVBoxLayout(self)
        
        lbl = QLabel("ИИ просит создать следующие файлы и папки.\nУтвердите список (снимите галочки с ненужных):")
        lbl.setStyleSheet("font-weight: bold; color: #e6a822; margin-bottom: 10px;")
        layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #3c3c3c; background-color: #252526; }")
        
        content = QWidget()
        content.setStyleSheet("background-color: #252526;")
        self.vbox = QVBoxLayout(content)
        self.checkboxes = []

        for f in files_list:
            # Если путь заканчивается на слеш - это папка
            cb = QCheckBox(f"📁 {f}" if f.endswith('/') or f.endswith('\\') else f"📄 {f}")
            cb.setChecked(True) # По умолчанию всё выбрано
            cb.setStyleSheet("""
                QCheckBox { color: #d4d4d4; padding: 5px; } 
                QCheckBox::indicator { width: 18px; height: 18px; }
                QCheckBox:hover { background-color: #37373d; border-radius: 4px; }
            """)
            self.vbox.addWidget(cb)
            self.checkboxes.append((cb, f))

        self.vbox.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("✅ Создать выбранное")
        btn_ok.setStyleSheet("background-color: #2e7d32; color: white; padding: 8px 15px; font-weight: bold; border-radius: 4px;")
        btn_ok.clicked.connect(self.on_accept)
        
        btn_cancel = QPushButton("❌ Отмена")
        btn_cancel.setStyleSheet("background-color: #d32f2f; color: white; padding: 8px 15px; font-weight: bold; border-radius: 4px;")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

    def on_accept(self):
        self.selected_files = [f for cb, f in self.checkboxes if cb.isChecked()]
        self.accept()