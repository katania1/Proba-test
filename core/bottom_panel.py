from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt

class BottomPanelWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(40)
        self.setStyleSheet("""
            QWidget { background-color: #252526; border-top: 1px solid #3c3c3c; }
            QPushButton { 
                background-color: transparent; 
                color: #d4d4d4; 
                border: none; 
                padding: 5px 10px; 
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3c3c3c; }
            QLabel { color: #d4d4d4; font-size: 13px; padding: 5px; }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)
        
        # Кнопки панели
        self.btn_attach = QPushButton("📎 Прикрепить")
        self.btn_history = QPushButton("🕒 История")
        self.btn_relay = QPushButton("🔄 Эстафета")
        self.btn_git = QPushButton("📦 Git")
        self.btn_rag = QPushButton("🧠 RAG")
        self.btn_api = QPushButton("⚙️ API")
        
        # --- НОВОЕ: Индикатор здоровья MCP (Светофор) ---
        self.lbl_mcp_status = QLabel("🛠️ MCP: ⚪")
        self.lbl_mcp_status.setToolTip("Статус Model Context Protocol (инициализация...)")
        self.lbl_mcp_status.setStyleSheet("color: #858585;")
        
        # Добавляем элементы в левую часть
        layout.addWidget(self.btn_attach)
        layout.addWidget(self.btn_history)
        layout.addWidget(self.btn_relay)
        layout.addWidget(self.btn_git)
        layout.addWidget(self.btn_rag)
        
        # Пружина, чтобы прижать правые элементы к краю
        layout.addStretch()
        
        # Добавляем элементы в правую часть
        layout.addWidget(self.lbl_mcp_status)
        layout.addWidget(self.btn_api)

    def update_mcp_status(self, status, message):
        """Обновляет цвет и текст тултипа для индикатора MCP"""
        if status == "online":
            self.lbl_mcp_status.setText("🛠️ MCP: 🟢")
            self.lbl_mcp_status.setStyleSheet("color: #31a24c; font-weight: bold;")
            self.lbl_mcp_status.setToolTip(message)
        elif status == "error":
            self.lbl_mcp_status.setText("🛠️ MCP: 🔴")
            self.lbl_mcp_status.setStyleSheet("color: #ff4444; font-weight: bold;")
            self.lbl_mcp_status.setToolTip(message)
        else:
            self.lbl_mcp_status.setText("🛠️ MCP: ⚪")
            self.lbl_mcp_status.setStyleSheet("color: #858585;")
            self.lbl_mcp_status.setToolTip(message)