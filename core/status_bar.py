import json
from PyQt6.QtWidgets import QStatusBar, QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QStandardItemModel, QStandardItem

class VibeStatusBar(QStatusBar):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.locked_tab_id = None
        self.init_ui()
        
        self.tab_timer = QTimer(self)
        self.tab_timer.timeout.connect(self.update_tabs_ui)
        self.tab_timer.start(2000)

    def init_ui(self):
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(5, 0, 10, 0)
        
        lbl_engine = QLabel("Движок: ")
        lbl_engine.setStyleSheet("color: #d4d4d4; font-weight: bold; margin-left: 10px;")
        
        self.combo_engine = QComboBox()
        self.combo_engine.setStyleSheet("""
            QComboBox { background-color: #252526; color: white; border: 1px solid #3c3c3c; padding: 2px 10px; border-radius: 3px; font-weight: bold; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #1e1e1e; color: #d4d4d4; selection-background-color: #0e639c; selection-color: white; border: 1px solid #3c3c3c; }
        """)
        self.combo_engine.setMinimumWidth(150)
        
        self.engine_model = QStandardItemModel()
        self.combo_engine.setModel(self.engine_model)
        
        status_layout.addWidget(lbl_engine)
        status_layout.addWidget(self.combo_engine)
        
        self.refresh_engine_list()
        self.combo_engine.currentTextChanged.connect(self._save_engine_selection)
        
        lbl_browser = QLabel("Браузер: ")
        lbl_browser.setStyleSheet("color: #d4d4d4; font-weight: bold; margin-left: 10px;")
        
        self.combo_tabs = QComboBox()
        self.combo_tabs.setStyleSheet(self.combo_engine.styleSheet())
        self.combo_tabs.setMinimumWidth(120)
        
        status_layout.addWidget(lbl_browser)
        status_layout.addWidget(self.combo_tabs)

        # Оставляем только кнопку ТЕРМИНАЛА
        self.btn_terminal = QPushButton("💻 Терминал")
        self.btn_terminal.setCheckable(True)
        self.btn_terminal.setFixedHeight(22)
        self.btn_terminal.setStyleSheet("""
            QPushButton { background-color: transparent; color: #aaaaaa; font-weight: bold; border-radius: 3px; padding: 0 10px; margin-left: 15px; border: 1px solid #3c3c3c;}
            QPushButton:hover { background-color: #333333; color: white; }
            QPushButton:checked { background-color: #0e639c; color: white; border: 1px solid #0e639c; }
        """)
        status_layout.addWidget(self.btn_terminal)
        
        self.addPermanentWidget(status_container)
        self.combo_tabs.currentIndexChanged.connect(self.on_tab_manually_changed)

    def _add_engine_category(self, title):
        item = QStandardItem(title)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
        item.setData(title, Qt.ItemDataRole.DisplayRole)
        item.setForeground(Qt.GlobalColor.darkGray)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.engine_model.appendRow(item)

    def _add_engine_item(self, text, provider_id, icon=""):
        item = QStandardItem(f"  {icon} {text}" if icon else f"  {text}")
        item.setData({"provider_id": provider_id, "model": text}, Qt.ItemDataRole.UserRole)
        self.engine_model.appendRow(item)

    def get_selected_engine_data(self):
        index = self.combo_engine.currentIndex()
        if index >= 0:
            item = self.engine_model.item(index)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data: return data
        return {"provider_id": "Browser", "model": "Gemini Web"}

    def refresh_engine_list(self):
        self.combo_engine.blockSignals(True)
        self.engine_model.clear()
        
        self._add_engine_category("--- БРАУЗЕР (ВКЛАДКИ) ---")
        self._add_engine_item("Gemini Web", "Browser", icon="🌐")
        
        oai_models = self.mw.api_settings.value("OpenAI_verified", [])
        if isinstance(oai_models, str): oai_models = [oai_models]
        if oai_models:
            self._add_engine_category("--- OPENAI API ---")
            for m in oai_models: self._add_engine_item(m, "OpenAI", icon="🟢")
                
        ant_models = self.mw.api_settings.value("Anthropic_verified", [])
        if isinstance(ant_models, str): ant_models = [ant_models]
        if ant_models:
            self._add_engine_category("--- ANTHROPIC API ---")
            for m in ant_models: self._add_engine_item(m, "Anthropic", icon="🟣")
                
        gem_models = self.mw.api_settings.value("Gemini_verified", [])
        if isinstance(gem_models, str): gem_models = [gem_models]
        if gem_models:
            self._add_engine_category("--- GEMINI API ---")
            for m in gem_models: self._add_engine_item(m, "Gemini", icon="🤖")

        custom_data = self.mw.api_settings.value("custom_providers", "[]")
        try:
            custom_providers = json.loads(custom_data)
            for p in custom_providers:
                p_id = p['id']
                p_name = p['name']
                
                c_models = self.mw.api_settings.value(f"{p_id}_verified", [])
                if isinstance(c_models, str): c_models = [c_models]
                
                if c_models:
                    self._add_engine_category(f"--- {p_name.upper()} ---")
                    for m in c_models:
                        self._add_engine_item(m, p_id, icon="⚡")
        except Exception:
            pass

        last_selection = self.mw.settings.value("last_engine", "  🌐 Gemini Web")
        index = self.combo_engine.findText(last_selection)
        if index >= 0:
            self.combo_engine.setCurrentIndex(index)
        else:
            self.combo_engine.setCurrentIndex(1) 
            
        self.combo_engine.blockSignals(False)

    def _save_engine_selection(self, text):
        self.mw.settings.setValue("last_engine", text)

    def on_tab_manually_changed(self, index):
        if index >= 0:
            text = self.combo_tabs.itemText(index)
            if "[" in text and "]" in text:
                self.locked_tab_id = text.split("[")[-1].split("]")[0]

    def get_current_target_id(self):
        return self.locked_tab_id

    def update_tabs_ui(self):
        if not hasattr(self.mw, 'ai_controller') or not hasattr(self.mw.ai_controller.bridge, 'get_active_tabs'): return
        raw_tabs = self.mw.ai_controller.bridge.get_active_tabs()

        if not raw_tabs:
            if self.combo_tabs.count() != 1 or self.combo_tabs.itemText(0) != "🔴 Нет связи":
                self.combo_tabs.blockSignals(True)
                self.combo_tabs.clear()
                self.combo_tabs.addItem("🔴 Нет связи")
                self.combo_tabs.blockSignals(False)
            return

        incoming_tabs = {}
        for t in raw_tabs:
            if "[" in t and "]" in t:
                t_id = t.split("[")[-1].split("]")[0]
                incoming_tabs[t_id] = f"🟢 {t}"

        current_tabs = {}
        for i in range(self.combo_tabs.count()):
            text = self.combo_tabs.itemText(i)
            if "[" in text and "]" in text:
                t_id = text.split("[")[-1].split("]")[0]
                current_tabs[t_id] = (i, text)

        if set(incoming_tabs.keys()) == set(current_tabs.keys()):
            self.combo_tabs.blockSignals(True)
            for t_id, (index, old_text) in current_tabs.items():
                new_text = incoming_tabs[t_id]
                if old_text != new_text:
                    self.combo_tabs.setItemText(index, new_text)
            self.combo_tabs.blockSignals(False)
            return

        self.combo_tabs.blockSignals(True)
        self.combo_tabs.clear()

        for t_id in sorted(incoming_tabs.keys()):
            self.combo_tabs.addItem(incoming_tabs[t_id])

        if self.locked_tab_id:
            for i in range(self.combo_tabs.count()):
                if f"[{self.locked_tab_id}]" in self.combo_tabs.itemText(i):
                    self.combo_tabs.setCurrentIndex(i)
                    break
        else:
            if self.combo_tabs.count() > 0:
                text = self.combo_tabs.itemText(0)
                if "[" in text and "]" in text:
                    self.locked_tab_id = text.split("[")[-1].split("]")[0]

        self.combo_tabs.blockSignals(False)