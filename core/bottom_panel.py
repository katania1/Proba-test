from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt

class BottomPanelWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(35)
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(5)

        flex_policy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        # === ЛЕВЫЙ БЛОК ===
        btn_icon_style = "background-color: #333333; color: white; font-size: 15px; border-radius: 4px; padding: 0px;"
        
        self.btn_attach = QPushButton("📎")
        self.btn_attach.setToolTip("Прикрепить медиа-файл (картинку)")
        self.btn_attach.setFixedSize(30, 30)
        self.btn_attach.setStyleSheet(btn_icon_style)

        self.btn_history = QPushButton("📜")
        self.btn_history.setToolTip("Умная история проекта и сессий")
        self.btn_history.setFixedSize(30, 30)
        self.btn_history.setStyleSheet(btn_icon_style)

        self.btn_relay = QPushButton("🔄")
        self.btn_relay.setToolTip("Сформировать транзитный пакет (эстафету)")
        self.btn_relay.setFixedSize(30, 30)
        self.btn_relay.setStyleSheet("background-color: #005f73; color: white; font-size: 15px; border-radius: 4px; padding: 0px;")

        layout.addWidget(self.btn_attach)
        layout.addWidget(self.btn_history)
        layout.addWidget(self.btn_relay)

        # ПРУЖИНА (Разделяет блоки)
        layout.addStretch()

        # === ПРАВЫЙ БЛОК ===
        btn_text_style = "background-color: #333333; color: white; font-weight: bold; border-radius: 4px; padding: 0 10px;"

        self.btn_api = QPushButton("⚙️ API")
        self.btn_api.setFixedHeight(30)
        self.btn_api.setSizePolicy(flex_policy)
        self.btn_api.setStyleSheet(btn_text_style)

        self.btn_git = QPushButton("📦 Git")
        self.btn_git.setFixedHeight(30)
        self.btn_git.setSizePolicy(flex_policy)
        self.btn_git.setStyleSheet("background-color: #4a148c; color: white; font-weight: bold; border-radius: 4px; padding: 0 10px;")

        self.btn_rag = QPushButton("🧠 RAG (Индекс)")
        self.btn_rag.setFixedHeight(30)
        self.btn_rag.setSizePolicy(flex_policy)
        self.btn_rag.setStyleSheet("background-color: #00838f; color: white; font-weight: bold; border-radius: 4px; padding: 0 10px;")

        layout.addWidget(self.btn_api)
        layout.addWidget(self.btn_git)
        layout.addWidget(self.btn_rag)