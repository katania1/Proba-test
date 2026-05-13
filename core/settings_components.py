from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QCheckBox
from PyQt6.QtCore import Qt

# Умные роли для хранения расширенных данных списка
ROLE_NAME = Qt.ItemDataRole.UserRole
ROLE_STATUS = Qt.ItemDataRole.UserRole + 1
ROLE_NOTE = Qt.ItemDataRole.UserRole + 2
ROLE_LAST_TESTED = Qt.ItemDataRole.UserRole + 3
ROLE_IS_NEW = Qt.ItemDataRole.UserRole + 4
ROLE_PROVIDER = Qt.ItemDataRole.UserRole + 5


class SecureInputWidget(QWidget):
    """
    Переиспользуемый виджет безопасного ввода (поле с глазиком для скрытия/отображения символов).
    """
    def __init__(self, placeholder="", text="", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.setText(text)
        self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.line_edit.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; padding: 6px; border-radius: 3px; font-family: Consolas, monospace;")
        
        self.btn_eye = QPushButton("V")
        self.btn_eye.setFixedSize(28, 28)
        self.btn_eye.setStyleSheet("background-color: #333333; color: white; border-radius: 3px; font-size: 14px; font-weight: bold; padding: 0px;")
        self.btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.btn_eye.clicked.connect(self.toggle_echo)
        
        layout.addWidget(self.line_edit)
        layout.addWidget(self.btn_eye)

    def toggle_echo(self):
        if self.line_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_eye.setStyleSheet("background-color: #0e639c; color: white; border-radius: 3px; font-size: 14px; font-weight: bold; padding: 0px;")
        else:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_eye.setStyleSheet("background-color: #333333; color: white; border-radius: 3px; font-size: 14px; font-weight: bold; padding: 0px;")


class RagKeyRowWidget(QWidget):
    """
    Строка управления резервным ключом пула RAG (чекбокс активности, безопасный ввод, комментарий, удаление).
    """
    def __init__(self, key_data=None, removal_callback=None, parent=None):
        super().__init__(parent)
        if key_data is None:
            key_data = {"key": "", "enabled": True, "comment": ""}
            
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 1. Чекбокс активности
        self.cb_enabled = QCheckBox()
        self.cb_enabled.setChecked(key_data.get("enabled", True))
        self.cb_enabled.setToolTip("Использовать этот ключ при индексации")
        self.cb_enabled.setStyleSheet("""
            QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #888; border-radius: 3px; background-color: #252526; }
            QCheckBox::indicator:checked { background-color: #31a24c; border: 1px solid #31a24c; }
        """)
        layout.addWidget(self.cb_enabled)
        
        # 2. Поле ключа (с глазиком)
        self.secure_input = SecureInputWidget("sk-... (Ключ)", key_data.get("key", ""))
        layout.addWidget(self.secure_input, stretch=3)
        
        # Пробрасываем ссылку на внутренний QLineEdit для прозрачного доступа при парсинге и сохранении настроек
        self.le_key = self.secure_input.line_edit
        
        # 3. Поле комментария
        self.le_comment = QLineEdit()
        self.le_comment.setPlaceholderText("Комментарий (напр. Студенческий 1)")
        self.le_comment.setText(key_data.get("comment", ""))
        self.le_comment.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; padding: 6px; border-radius: 3px;")
        layout.addWidget(self.le_comment, stretch=2)
        
        # 4. Кнопка удаления
        self.btn_del = QPushButton("X")
        self.btn_del.setFixedSize(28, 28)
        self.btn_del.setStyleSheet("background-color: #512525; color: white; border-radius: 3px; font-size: 14px; font-weight: bold; padding: 0px;")
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        
        if removal_callback:
            self.btn_del.clicked.connect(lambda: removal_callback(self))
            
        layout.addWidget(self.btn_del)