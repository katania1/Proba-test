from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QTabWidget, QWidget, QMessageBox, QComboBox)
from PyQt6.QtCore import QSettings, QThread, pyqtSignal, Qt

from core.providers import OpenAIProvider, AnthropicProvider, GeminiAPIProvider

# ==========================================
# ФОНОВЫЙ ВОРКЕР ДЛЯ ПРОВЕРКИ API
# ==========================================
class VerificationWorker(QThread):
    models_fetched = pyqtSignal(list)
    verification_done = pyqtSignal(bool, str)
    error_signal = pyqtSignal(str)

    def __init__(self, provider, action, model_to_verify=""):
        super().__init__()
        self.provider = provider
        self.action = action # 'fetch_models' или 'verify'
        self.model_to_verify = model_to_verify

    def run(self):
        try:
            if self.action == 'fetch_models':
                models = self.provider.get_models()
                self.models_fetched.emit(models)
            elif self.action == 'verify':
                success, msg = self.provider.verify_model(self.model_to_verify)
                self.verification_done.emit(success, msg)
        except Exception as e:
            self.error_signal.emit(str(e))

# ==========================================
# ОКНО НАСТРОЕК
# ==========================================
class APISettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Настройки API Провайдеров")
        self.resize(550, 450)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        self.settings = QSettings("VibeCoder", "API_Config")
        self.workers = [] # Храним ссылки на потоки, чтобы их не уничтожил сборщик мусора
        
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        lbl_info = QLabel("Введите API-ключи, загрузите список моделей и проверьте доступ.\nКлючи сохраняются локально (QSettings).")
        lbl_info.setStyleSheet("color: #aaaaaa; font-size: 13px; margin-bottom: 5px;")
        layout.addWidget(lbl_info)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3c3c3c; }
            QTabBar::tab { background: #252526; color: #888888; padding: 6px 15px; border: 1px solid #3c3c3c; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px;}
            QTabBar::tab:selected { background: #1e1e1e; color: #d4d4d4; font-weight: bold; border-bottom: 1px solid #1e1e1e;}
            QTabBar::tab:hover:!selected { background: #2a2d2e; }
        """)
        
        # Инициализация вкладок
        self.setup_provider_tab("OpenAI", "🟢 OpenAI", "sk-...", True)
        self.setup_provider_tab("Anthropic", "🟣 Anthropic", "sk-ant-...", True)
        self.setup_provider_tab("Gemini", "🤖 Gemini API", "AIzaSy...", False)

        layout.addWidget(self.tabs)

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
        line_edit.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; padding: 6px; border-radius: 3px; font-family: Consolas, monospace;")
        if is_password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        return line_edit

    def setup_provider_tab(self, provider_id, tab_title, key_placeholder, has_base_url):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Хранилище UI элементов для этого провайдера
        ui = {}
        
        # 1. API Ключ
        layout.addWidget(QLabel("API Key:"))
        ui['key'] = self._create_input_field(is_password=True, placeholder=key_placeholder)
        layout.addWidget(ui['key'])
        
        # 2. Base URL (если нужен)
        if has_base_url:
            layout.addWidget(QLabel("Base URL (опционально):"))
            ui['url'] = self._create_input_field(placeholder="https://api...")
            layout.addWidget(ui['url'])
        else:
            ui['url'] = None
            
        # Разделитель
        layout.addSpacing(10)
        
        # 3. Блок выбора модели и проверки
        model_layout = QHBoxLayout()
        ui['btn_fetch'] = QPushButton("🔄 Загрузить модели")
        ui['btn_fetch'].setStyleSheet("background-color: #0e639c; color: white; padding: 4px 10px; border-radius: 3px;")
        
        ui['combo_models'] = QComboBox()
        ui['combo_models'].setStyleSheet("QComboBox { background-color: #252526; border: 1px solid #3c3c3c; padding: 4px; }")
        ui['combo_models'].setMinimumWidth(150)
        ui['combo_models'].addItem("Сначала загрузите список...")
        
        model_layout.addWidget(ui['btn_fetch'])
        model_layout.addWidget(ui['combo_models'], 1)
        layout.addLayout(model_layout)
        
        ui['btn_verify'] = QPushButton("✅ Проверить доступ к выбранной модели")
        ui['btn_verify'].setStyleSheet("background-color: #4a148c; color: white; padding: 6px; border-radius: 3px; font-weight: bold;")
        layout.addWidget(ui['btn_verify'])
        
        ui['lbl_status'] = QLabel("Статус: ожидание...")
        ui['lbl_status'].setStyleSheet("color: #888888;")
        ui['lbl_status'].setWordWrap(True)
        
        # --- НОВАЯ СТРОКА: Разрешаем выделение и копирование текста мышкой ---
        ui['lbl_status'].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        layout.addWidget(ui['lbl_status'])
        
        layout.addStretch()
        self.tabs.addTab(tab, tab_title)
        
        # Привязка логики
        ui['btn_fetch'].clicked.connect(lambda: self.fetch_models(provider_id, ui))
        ui['btn_verify'].clicked.connect(lambda: self.verify_access(provider_id, ui))
        
        # Сохраняем UI в свойства класса, чтобы потом достать значения при сохранении
        setattr(self, f"ui_{provider_id}", ui)

    def _get_provider_instance(self, provider_id, ui):
        key = ui['key'].text().strip()
        url = ui['url'].text().strip() if ui['url'] else None
        
        if not key:
            ui['lbl_status'].setText("❌ Ошибка: Введите API ключ!")
            ui['lbl_status'].setStyleSheet("color: #ff4444;")
            return None
            
        if provider_id == "OpenAI": return OpenAIProvider(key, url)
        elif provider_id == "Anthropic": return AnthropicProvider(key, url)
        elif provider_id == "Gemini": return GeminiAPIProvider(key)
        return None

    def fetch_models(self, provider_id, ui):
        provider = self._get_provider_instance(provider_id, ui)
        if not provider: return
            
        ui['btn_fetch'].setText("⏳ Загрузка...")
        ui['btn_fetch'].setEnabled(False)
        ui['lbl_status'].setText("Статус: Подключение к серверу...")
        ui['lbl_status'].setStyleSheet("color: #e6a822;")
        
        worker = VerificationWorker(provider, 'fetch_models')
        
        # Обработчики
        worker.models_fetched.connect(lambda models: self._on_models_fetched(models, ui, provider_id))
        worker.error_signal.connect(lambda err: self._on_worker_error(err, ui, "btn_fetch", "🔄 Загрузить модели"))
        
        self.workers.append(worker)
        worker.start()

    def _on_models_fetched(self, models, ui, provider_id):
        ui['btn_fetch'].setText("🔄 Загрузить модели")
        ui['btn_fetch'].setEnabled(True)
        
        ui['combo_models'].clear()
        if models:
            ui['combo_models'].addItems(models)
            ui['lbl_status'].setText(f"✅ Загружено {len(models)} моделей. Выберите нужную и проверьте доступ.")
            ui['lbl_status'].setStyleSheet("color: #31a24c;")
            
            # Пытаемся восстановить ранее выбранную модель
            saved_model = self.settings.value(f"{provider_id.lower()}_model", "")
            if saved_model in models:
                ui['combo_models'].setCurrentText(saved_model)
        else:
            ui['combo_models'].addItem("Модели не найдены")
            ui['lbl_status'].setText("⚠️ Сервер не вернул список моделей.")
            ui['lbl_status'].setStyleSheet("color: #e6a822;")

    def verify_access(self, provider_id, ui):
        provider = self._get_provider_instance(provider_id, ui)
        if not provider: return
        
        selected_model = ui['combo_models'].currentText()
        if not selected_model or selected_model == "Сначала загрузите список...":
            ui['lbl_status'].setText("❌ Сначала загрузите и выберите модель!")
            ui['lbl_status'].setStyleSheet("color: #ff4444;")
            return
            
        ui['btn_verify'].setText("⏳ Проверка...")
        ui['btn_verify'].setEnabled(False)
        ui['lbl_status'].setText("Статус: Выполнение тестового запроса (1 токен)...")
        ui['lbl_status'].setStyleSheet("color: #e6a822;")
        
        worker = VerificationWorker(provider, 'verify', model_to_verify=selected_model)
        worker.verification_done.connect(lambda success, msg: self._on_verified(success, msg, ui))
        worker.error_signal.connect(lambda err: self._on_worker_error(err, ui, "btn_verify", "✅ Проверить доступ к выбранной модели"))
        
        self.workers.append(worker)
        worker.start()

    def _on_verified(self, success, msg, ui):
        ui['btn_verify'].setText("✅ Проверить доступ к выбранной модели")
        ui['btn_verify'].setEnabled(True)
        
        if success:
            ui['lbl_status'].setText(f"✅ {msg}")
            ui['lbl_status'].setStyleSheet("color: #31a24c;")
        else:
            ui['lbl_status'].setText(f"❌ {msg}")
            ui['lbl_status'].setStyleSheet("color: #ff4444;")

    def _on_worker_error(self, err_msg, ui, btn_key, btn_text):
        ui[btn_key].setText(btn_text)
        ui[btn_key].setEnabled(True)
        ui['lbl_status'].setText(f"❌ Ошибка сети/ключа: {err_msg}")
        ui['lbl_status'].setStyleSheet("color: #ff4444;")

    def load_settings(self):
        """Загружает сохраненные ключи при открытии окна"""
        # OpenAI
        self.ui_OpenAI['key'].setText(self.settings.value("openai_api_key", ""))
        self.ui_OpenAI['url'].setText(self.settings.value("openai_base_url", "https://api.openai.com/v1"))
        saved_oai = self.settings.value("openai_model", "")
        if saved_oai:
            self.ui_OpenAI['combo_models'].clear()
            self.ui_OpenAI['combo_models'].addItem(saved_oai)
        
        # Anthropic
        self.ui_Anthropic['key'].setText(self.settings.value("anthropic_api_key", ""))
        self.ui_Anthropic['url'].setText(self.settings.value("anthropic_base_url", "https://api.anthropic.com"))
        saved_ant = self.settings.value("anthropic_model", "")
        if saved_ant:
            self.ui_Anthropic['combo_models'].clear()
            self.ui_Anthropic['combo_models'].addItem(saved_ant)
            
        # Gemini
        self.ui_Gemini['key'].setText(self.settings.value("gemini_api_key", ""))
        saved_gem = self.settings.value("gemini_model", "")
        if saved_gem:
            self.ui_Gemini['combo_models'].clear()
            self.ui_Gemini['combo_models'].addItem(saved_gem)

    def save_settings(self):
        """Сохраняет введенные ключи и формирует списки проверенных моделей"""
        # --- OpenAI ---
        self.settings.setValue("openai_api_key", self.ui_OpenAI['key'].text().strip())
        self.settings.setValue("openai_base_url", self.ui_OpenAI['url'].text().strip() or "https://api.openai.com/v1")
        m_oai = self.ui_OpenAI['combo_models'].currentText()
        
        # Если статус зеленый (успешная проверка), добавляем в рабочие
        if m_oai and m_oai != "Сначала загрузите список..." and "✅" in self.ui_OpenAI['lbl_status'].text():
            # Берем текущий список из настроек, или пустой, если его нет
            verified_oai = self.settings.value("openai_verified", [])
            # Если это строка (старый формат), делаем списком
            if isinstance(verified_oai, str): verified_oai = [verified_oai]
            # Добавляем модель, если ее там еще нет
            if m_oai not in verified_oai:
                verified_oai.append(m_oai)
            self.settings.setValue("openai_verified", verified_oai)
            self.settings.setValue("openai_model", m_oai) # Для обратной совместимости
            
        # --- Anthropic ---
        self.settings.setValue("anthropic_api_key", self.ui_Anthropic['key'].text().strip())
        self.settings.setValue("anthropic_base_url", self.ui_Anthropic['url'].text().strip() or "https://api.anthropic.com")
        m_ant = self.ui_Anthropic['combo_models'].currentText()
        
        if m_ant and m_ant != "Сначала загрузите список..." and "✅" in self.ui_Anthropic['lbl_status'].text():
            verified_ant = self.settings.value("anthropic_verified", [])
            if isinstance(verified_ant, str): verified_ant = [verified_ant]
            if m_ant not in verified_ant:
                verified_ant.append(m_ant)
            self.settings.setValue("anthropic_verified", verified_ant)
            self.settings.setValue("anthropic_model", m_ant)
            
        # --- Gemini ---
        self.settings.setValue("gemini_api_key", self.ui_Gemini['key'].text().strip())
        m_gem = self.ui_Gemini['combo_models'].currentText()
        
        if m_gem and m_gem != "Сначала загрузите список..." and "✅" in self.ui_Gemini['lbl_status'].text():
            verified_gem = self.settings.value("gemini_verified", [])
            if isinstance(verified_gem, str): verified_gem = [verified_gem]
            if m_gem not in verified_gem:
                verified_gem.append(m_gem)
            self.settings.setValue("gemini_verified", verified_gem)
            self.settings.setValue("gemini_model", m_gem)
        
        QMessageBox.information(self, "Успех", "✅ Настройки API успешно сохранены!")
        self.accept()