from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QTabWidget, QWidget, QMessageBox)
from PyQt6.QtCore import QSettings

class APISettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Настройки API Провайдеров")
        self.resize(500, 350)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        # QSettings для безопасного сохранения ключей (без записи в файлы проекта)
        self.settings = QSettings("VibeCoder", "API_Config")
        
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        lbl_info = QLabel("Введите API-ключи для нужных провайдеров.\nКлючи сохраняются безопасно и локально (QSettings).")
        lbl_info.setStyleSheet("color: #aaaaaa; font-size: 13px; margin-bottom: 10px;")
        layout.addWidget(lbl_info)

        # Создаем вкладки для разных провайдеров
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3c3c3c; }
            QTabBar::tab { background: #252526; color: #888888; padding: 6px 15px; border: 1px solid #3c3c3c; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px;}
            QTabBar::tab:selected { background: #1e1e1e; color: #d4d4d4; font-weight: bold; border-bottom: 1px solid #1e1e1e;}
            QTabBar::tab:hover:!selected { background: #2a2d2e; }
        """)
        
        # Инициализируем UI для вкладок
        self.setup_openai_tab()
        self.setup_anthropic_tab()
        self.setup_gemini_tab()

        layout.addWidget(self.tabs)

        # Кнопки Сохранить / Отмена
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setStyleSheet("background-color: #333333; padding: 6px 15px; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_save = QPushButton("💾 Сохранить")
        self.btn_save.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 6px 15px; border-radius: 4px;")
        self.btn_save.clicked.connect(self.save_settings)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        
        layout.addLayout(btn_layout)

    def _create_input_field(self, is_password=False, placeholder=""):
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        line_edit.setStyleSheet("""
            QLineEdit {
                background-color: #252526; 
                border: 1px solid #3c3c3c; 
                padding: 6px; 
                border-radius: 3px;
                font-family: Consolas, monospace;
            }
            QLineEdit:focus { border: 1px solid #0e639c; }
        """)
        if is_password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        return line_edit

    def setup_openai_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        layout.addWidget(QLabel("API Key (sk-...):"))
        self.openai_key = self._create_input_field(is_password=True, placeholder="Введите ключ OpenAI")
        layout.addWidget(self.openai_key)
        
        layout.addWidget(QLabel("Base URL (опционально, для локальных сетей/прокси):"))
        self.openai_url = self._create_input_field(placeholder="Например: http://localhost:1234/v1")
        layout.addWidget(self.openai_url)
        
        layout.addStretch()
        self.tabs.addTab(tab, "🟢 OpenAI / Local")

    def setup_anthropic_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        layout.addWidget(QLabel("API Key (sk-ant-...):"))
        self.anthropic_key = self._create_input_field(is_password=True, placeholder="Введите ключ Anthropic (Claude)")
        layout.addWidget(self.anthropic_key)
        
        layout.addWidget(QLabel("Base URL (опционально):"))
        self.anthropic_url = self._create_input_field(placeholder="По умолчанию: https://api.anthropic.com")
        layout.addWidget(self.anthropic_url)
        
        layout.addStretch()
        self.tabs.addTab(tab, "🟣 Anthropic")

    def setup_gemini_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        lbl = QLabel("Примечание: Если ключ не указан, VibeCoder\nпродолжит использовать браузерный мост Gemini Web.")
        lbl.setStyleSheet("color: #e6a822; margin-bottom: 5px;")
        layout.addWidget(lbl)
        
        layout.addWidget(QLabel("API Key (AIzaSy...):"))
        self.gemini_key = self._create_input_field(is_password=True, placeholder="Введите официальный ключ Google AI Studio")
        layout.addWidget(self.gemini_key)
        
        layout.addStretch()
        self.tabs.addTab(tab, "🤖 Gemini API")

    def load_settings(self):
        """Загружает сохраненные ключи при открытии окна"""
        self.openai_key.setText(self.settings.value("openai_api_key", ""))
        self.openai_url.setText(self.settings.value("openai_base_url", "https://api.openai.com/v1"))
        
        self.anthropic_key.setText(self.settings.value("anthropic_api_key", ""))
        self.anthropic_url.setText(self.settings.value("anthropic_base_url", "https://api.anthropic.com"))
        
        self.gemini_key.setText(self.settings.value("gemini_api_key", ""))

    def save_settings(self):
        """Сохраняет введенные ключи в системный реестр"""
        self.settings.setValue("openai_api_key", self.openai_key.text().strip())
        self.settings.setValue("openai_base_url", self.openai_url.text().strip() or "https://api.openai.com/v1")
        
        self.settings.setValue("anthropic_api_key", self.anthropic_key.text().strip())
        self.settings.setValue("anthropic_base_url", self.anthropic_url.text().strip() or "https://api.anthropic.com")
        
        self.settings.setValue("gemini_api_key", self.gemini_key.text().strip())
        
        QMessageBox.information(self, "Успех", "✅ Настройки API успешно сохранены!")
        self.accept()