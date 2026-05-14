import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QListWidget, QApplication)
from PyQt6.QtCore import Qt, QMimeData, QUrl
from PyQt6.QtGui import QDrag

class DragFilesButton(QPushButton):
    """
    Умная кнопка для Гибридного Драг-энд-Дропа.
    Вешает файлы на курсор, а в буфер обмена кладет короткую отбивку.
    """
    def __init__(self, text, file_paths, controller, parent_dialog):
        super().__init__(text, parent_dialog)
        self.file_paths = file_paths
        self.controller = controller
        self.parent_dialog = parent_dialog
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet(
            "background-color: #b26500; color: white; padding: 10px; "
            "border-radius: 4px; font-weight: bold; font-size: 13px;"
        )
        
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            drag = QDrag(self)
            mime_data = QMimeData()
            
            # 1. Вешаем физические файлы на курсор мыши (QMimeData)
            urls = []
            for path in self.file_paths:
                abs_path = os.path.abspath(os.path.join(self.controller.mw.project_path, path))
                if os.path.exists(abs_path):
                    urls.append(QUrl.fromLocalFile(abs_path))
            mime_data.setUrls(urls)
            drag.setMimeData(mime_data)
            
            # 2. В буфер кладем ТОЛЬКО короткий текст-заглушку (чтобы кнопка отправки стала активной)
            # Никакого исходного кода, чтобы не засорять чат.
            QApplication.clipboard().setText("Вот файлы, которые ты запрашивал для анализа.")
            
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            
            # 3. Выполняем физический бросок в систему
            drag.exec(Qt.DropAction.CopyAction)
            
            # Закрываем диалог (Reject означает, что мы отменили авто-отправку текстом)
            self.parent_dialog.reject()
                
        super().mouseMoveEvent(event)


class RequestedFilesDialog(QDialog):
    """
    Интерактивное окно запроса файлов от ИИ.
    Два режима: Авто-текст (для мелких правок) и Drag-and-Drop (для тяжелых файлов).
    """
    def __init__(self, controller, requested_files, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.requested_files = requested_files
        
        self.setWindowTitle("🤖 Запрос контекста (ИИ просит файлы)")
        self.setMinimumWidth(500)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        lbl_info = QLabel("ИИ просит предоставить код следующих файлов для работы:")
        lbl_info.setStyleSheet("font-size: 13px; margin-bottom: 5px;")
        layout.addWidget(lbl_info)
        
        list_widget = QListWidget()
        list_widget.addItems(self.requested_files)
        list_widget.setStyleSheet("""
            QListWidget { background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 5px; font-family: Consolas, monospace;}
            QListWidget::item { padding: 4px; }
        """)
        layout.addWidget(list_widget)
        
        btn_layout = QHBoxLayout()
        
        # Режим 1: Обычный клик (Автоматически текстом)
        self.btn_auto = QPushButton("⚡ Отправить текстом (Авто)")
        self.btn_auto.setStyleSheet(
            "background-color: #0e639c; color: white; padding: 10px; "
            "border-radius: 4px; font-weight: bold; font-size: 13px;"
        )
        self.btn_auto.setToolTip("Файлы будут напечатаны в чате. Безопасно для мелких файлов.")
        self.btn_auto.clicked.connect(self.accept) 
        
        # Режим 2: Наш новый чистый Гибридный бросок
        self.btn_drag = DragFilesButton("✋ Перетащить в чат (Fast)", self.requested_files, self.controller, self)
        self.btn_drag.setToolTip("Зажмите ЛКМ и перетащите в Gemini. Затем Ctrl+V (короткая фраза) и Enter.")
        
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setStyleSheet("background-color: #333333; padding: 10px; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_auto)
        btn_layout.addWidget(self.btn_drag)
        
        layout.addLayout(btn_layout)
        layout.addWidget(self.btn_cancel)