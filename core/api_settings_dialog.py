import json
import uuid
from datetime import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QTabWidget, QWidget, QMessageBox, 
                             QListWidget, QListWidgetItem, QInputDialog, QAbstractItemView,
                             QMenu, QApplication, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox)
from PyQt6.QtCore import QSettings, QThread, pyqtSignal, Qt, QTimer

from core.providers import OpenAIProvider, AnthropicProvider, GeminiAPIProvider

# Умные роли для хранения расширенных данных списка
ROLE_NAME = Qt.ItemDataRole.UserRole
ROLE_STATUS = Qt.ItemDataRole.UserRole + 1
ROLE_NOTE = Qt.ItemDataRole.UserRole + 2
ROLE_LAST_TESTED = Qt.ItemDataRole.UserRole + 3
ROLE_IS_NEW = Qt.ItemDataRole.UserRole + 4
ROLE_PROVIDER = Qt.ItemDataRole.UserRole + 5

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
        self.action = action 
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
# ОКНО: БАЗА ПРОВЕРЕННЫХ МОДЕЛЕЙ (DASHBOARD)
# ==========================================
class ModelDatabaseDialog(QDialog):
    def __init__(self, parent_dialog):
        super().__init__(parent_dialog)
        self.parent_dialog = parent_dialog
        self.setWindowTitle("📚 База проверенных моделей")
        self.resize(850, 500)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        layout = QVBoxLayout(self)
        
        lbl_info = QLabel("Здесь собраны все модели, которые вы когда-либо проверяли.\nВы можете редактировать примечания или удалять модели из этой базы (их статус будет сброшен).")
        lbl_info.setStyleSheet("color: #aaaaaa; font-size: 13px; margin-bottom: 10px;")
        layout.addWidget(lbl_info)
        
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Провайдер", "Модель", "Статус", "Дата проверки", "Примечание", ""])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setStyleSheet("""
            QTableWidget { background-color: #252526; color: #d4d4d4; gridline-color: #3c3c3c; border: 1px solid #3c3c3c; font-size: 13px; }
            QHeaderView::section { background-color: #1e1e1e; color: #aaaaaa; padding: 6px; border: 1px solid #3c3c3c; font-weight: bold; }
            QTableWidget::item { padding: 4px; }
            QTableWidget::item:selected { background-color: #0e639c; }
        """)
        
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.table)
        
        btn_close = QPushButton("Закрыть окно")
        btn_close.setStyleSheet("background-color: #333333; padding: 8px 20px; border-radius: 4px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(0)
        row = 0
        
        for provider_id, ui in self.parent_dialog.tabs_ui.items():
            list_widget = ui['list_models']
            provider_name = self.parent_dialog.tabs.tabText(self.parent_dialog.tabs.indexOf(ui['tab_widget'])).replace("⚙️ ", "")
            
            for i in range(list_widget.count()):
                orig_item = list_widget.item(i)
                status = orig_item.data(ROLE_STATUS)
                
                if status in ["ok", "error"]:
                    self.table.insertRow(row)
                    
                    is_new = orig_item.data(ROLE_IS_NEW)
                    name = orig_item.data(ROLE_NAME)
                    display_name = f"🆕 {name}" if is_new else name
                    
                    status_text = "✅ Работает" if status == "ok" else "❌ Ошибка"
                    
                    item_prov = QTableWidgetItem(provider_name)
                    item_prov.setData(Qt.ItemDataRole.UserRole, orig_item)
                    item_prov.setFlags(item_prov.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    
                    item_name = QTableWidgetItem(display_name)
                    item_name.setFlags(item_name.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if is_new: item_name.setForeground(Qt.GlobalColor.cyan)
                    
                    item_status = QTableWidgetItem(status_text)
                    item_status.setFlags(item_status.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item_status.setForeground(Qt.GlobalColor.green if status == "ok" else Qt.GlobalColor.red)
                    if status == "error": item_status.setToolTip(orig_item.toolTip())
                    
                    item_date = QTableWidgetItem(orig_item.data(ROLE_LAST_TESTED) or "Неизвестно")
                    item_date.setFlags(item_date.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item_date.setForeground(Qt.GlobalColor.darkGray)
                    
                    item_note = QTableWidgetItem(orig_item.data(ROLE_NOTE) or "")
                    item_note.setFlags(item_note.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item_note.setForeground(Qt.GlobalColor.yellow)
                    
                    self.table.setItem(row, 0, item_prov)
                    self.table.setItem(row, 1, item_name)
                    self.table.setItem(row, 2, item_status)
                    self.table.setItem(row, 3, item_date)
                    self.table.setItem(row, 4, item_note)
                    row += 1

    def show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item: return
        
        row = item.row()
        orig_item = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; }
            QMenu::item { padding: 6px 20px; font-size: 13px; }
            QMenu::item:selected { background-color: #0e639c; }
            QMenu::separator { height: 1px; background: #3c3c3c; margin: 4px 0; }
        """)
        
        action_note = menu.addAction("📝 Изменить примечание")
        menu.addSeparator()
        action_delete = menu.addAction("🗑️ Удалить из базы (Сбросить статус)")
        
        action = menu.exec(self.table.mapToGlobal(pos))
        
        if action == action_note:
            old_note = orig_item.data(ROLE_NOTE) or ""
            clean_name = orig_item.data(ROLE_NAME)
            new_note, ok = QInputDialog.getText(self, "Примечание", f"Заметка для {clean_name}:", text=old_note)
            if ok:
                orig_item.setData(ROLE_NOTE, new_note.strip())
                self.parent_dialog._update_item_display(orig_item) 
                self.table.item(row, 4).setText(new_note.strip()) 
                
        elif action == action_delete:
            orig_item.setData(ROLE_STATUS, "unknown")
            orig_item.setData(ROLE_LAST_TESTED, "")
            orig_item.setData(ROLE_IS_NEW, False)
            orig_item.setData(ROLE_NOTE, "")
            orig_item.setCheckState(Qt.CheckState.Unchecked) 
            self.parent_dialog._update_item_display(orig_item)
            self.table.removeRow(row)

# ==========================================
# ОКНО НАСТРОЕК С ДИНАМИЧЕСКИМИ ВКЛАДКАМИ
# ==========================================
class APISettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Настройки API Провайдеров (Pro)")
        self.resize(750, 750) 
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        self.settings = QSettings("VibeCoder", "API_Config")
        self.workers = [] 
        self.tabs_ui = {} 
        
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        lbl_info = QLabel(
            "Отметьте галочками модели, которые хотите видеть в меню программы.\n"
            "Снимите галочку, чтобы скрыть модель. ПКМ — для заметок и переименования."
        )
        lbl_info.setStyleSheet("color: #aaaaaa; font-size: 13px;")
        
        self.btn_db = QPushButton("📚 База проверенных моделей")
        self.btn_db.setStyleSheet("background-color: #4a148c; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_db.clicked.connect(self.open_model_database)
        
        self.btn_add_custom = QPushButton("➕ Добавить API (OpenRouter/Groq/etc)")
        self.btn_add_custom.setStyleSheet("background-color: #0e639c; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_add_custom.clicked.connect(self.add_custom_provider_dialog)
        
        header_layout.addWidget(lbl_info)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_db)
        header_layout.addWidget(self.btn_add_custom)
        layout.addLayout(header_layout)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3c3c3c; background: #1e1e1e; }
            QTabBar::tab { background: #252526; color: #888888; padding: 8px 15px; border: 1px solid #3c3c3c; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #1e1e1e; color: #d4d4d4; font-weight: bold; border-top: 2px solid #0e639c; border-bottom: 1px solid #1e1e1e; }
            QTabBar::tab:hover:!selected { background: #2a2d2e; }
        """)
        
        self.tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self._show_tab_context_menu)
        
        layout.addWidget(self.tabs)

        self.create_provider_tab("OpenAI", "🟢 OpenAI", "sk-...", has_base_url=True, has_embedding_key=True)
        self.create_provider_tab("Anthropic", "🟣 Anthropic", "sk-ant-...", has_base_url=True)
        self.create_provider_tab("Gemini", "🤖 Gemini API", "AIzaSy...", has_base_url=False, has_embedding_key=True)

        self.load_custom_tabs()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setStyleSheet("background-color: #333333; padding: 8px 20px; border-radius: 4px; font-weight: bold;")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_save = QPushButton("💾 Сохранить всё")
        self.btn_save.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 8px 20px; border-radius: 4px;")
        self.btn_save.clicked.connect(self.save_settings)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        
        layout.addLayout(btn_layout)

    def open_model_database(self):
        dlg = ModelDatabaseDialog(self)
        dlg.exec()

    def _create_input_field(self, is_password=False, placeholder=""):
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        line_edit.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; padding: 6px; border-radius: 3px; font-family: Consolas, monospace;")
        if is_password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        return line_edit

    # --- ИНТЕГРАЦИЯ УМНЫХ ПОЛЕЙ ВВОДА С ГЛАЗИКОМ ---
    def _create_secure_input(self, placeholder="", text=""):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        line_edit.setText(text)
        line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        line_edit.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; padding: 6px; border-radius: 3px; font-family: Consolas, monospace;")
        
        btn_eye = QPushButton("V")
        btn_eye.setFixedSize(28, 28)
        btn_eye.setStyleSheet("background-color: #333333; color: white; border-radius: 3px; font-size: 14px; font-weight: bold; padding: 0px;")
        btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        
        def toggle_echo():
            if line_edit.echoMode() == QLineEdit.EchoMode.Password:
                line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
                btn_eye.setStyleSheet("background-color: #0e639c; color: white; border-radius: 3px; font-size: 14px; font-weight: bold; padding: 0px;")
            else:
                line_edit.setEchoMode(QLineEdit.EchoMode.Password)
                btn_eye.setStyleSheet("background-color: #333333; color: white; border-radius: 3px; font-size: 14px; font-weight: bold; padding: 0px;")
                
        btn_eye.clicked.connect(toggle_echo)
        
        layout.addWidget(line_edit)
        layout.addWidget(btn_eye)
        container.line_edit = line_edit
        return container

    # --- НОВЫЙ ДИЗАЙН ПУЛА КЛЮЧЕЙ RAG (JSON-ФОРМАТ) ---
    def _add_emb_key_row(self, layout, key_data=None):
        if key_data is None: 
            key_data = {"key": "", "enabled": True, "comment": ""}
            
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        
        # 1. Чекбокс активности
        cb_enabled = QCheckBox()
        cb_enabled.setChecked(key_data.get("enabled", True))
        cb_enabled.setToolTip("Использовать этот ключ при индексации")
        cb_enabled.setStyleSheet("""
            QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #888; border-radius: 3px; background-color: #252526; }
            QCheckBox::indicator:checked { background-color: #31a24c; border: 1px solid #31a24c; }
        """)
        row_layout.addWidget(cb_enabled)
        
        # 2. Поле ключа (с глазиком)
        input_container = self._create_secure_input("sk-... (Ключ)", key_data.get("key", ""))
        row_layout.addWidget(input_container, stretch=3)
        
        # 3. Поле комментария
        le_comment = QLineEdit()
        le_comment.setPlaceholderText("Комментарий (напр. Студенческий 1)")
        le_comment.setText(key_data.get("comment", ""))
        le_comment.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; padding: 6px; border-radius: 3px;")
        row_layout.addWidget(le_comment, stretch=2)
        
        # 4. Кнопка удаления
        btn_del = QPushButton("X")
        btn_del.setFixedSize(28, 28)
        btn_del.setStyleSheet("background-color: #512525; color: white; border-radius: 3px; font-size: 14px; font-weight: bold; padding: 0px;")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(lambda: self._remove_emb_key_row(row_widget, layout))
        row_layout.addWidget(btn_del)
        
        # Сохраняем ссылки для удобного парсинга при сохранении
        row_widget.cb_enabled = cb_enabled
        row_widget.le_key = input_container.line_edit
        row_widget.le_comment = le_comment
        
        layout.addWidget(row_widget)

    def _remove_emb_key_row(self, row_widget, layout):
        layout.removeWidget(row_widget)
        row_widget.deleteLater()

    def _load_emb_keys(self, layout, keys_json_str):
        # Пытаемся загрузить как новый JSON
        try:
            keys_data = json.loads(keys_json_str)
            if not isinstance(keys_data, list):
                raise ValueError("Неверный формат")
        except:
            # Фолбэк (Умная конвертация): если это старая строка через запятую
            keys_data = [{"key": k.strip(), "enabled": True, "comment": ""} for k in keys_json_str.split(',') if k.strip()]
            
        if not keys_data:
            self._add_emb_key_row(layout)
        else:
            for k_data in keys_data:
                self._add_emb_key_row(layout, k_data)

    def _update_item_display(self, item):
        name = item.data(ROLE_NAME)
        status = item.data(ROLE_STATUS)
        note = item.data(ROLE_NOTE)
        is_new = item.data(ROLE_IS_NEW)
        
        icon = ""
        color = Qt.GlobalColor.white
        new_tag = "🆕 " if is_new else ""
        
        if status == "ok":
            icon = "✅ "
            color = Qt.GlobalColor.green
        elif status == "error":
            icon = "❌ "
            color = Qt.GlobalColor.red
        elif status == "loading":
            icon = "⏳ "
            color = Qt.GlobalColor.yellow
        else:
            color = Qt.GlobalColor.lightGray
            
        display_text = f"{new_tag}{icon}{name}"
        if note:
            display_text += f"   [📝 {note}]"
            
        item.setText(display_text)
        item.setForeground(color)

    def create_provider_tab(self, provider_id, default_tab_title, key_placeholder, has_base_url=True, is_custom=False, has_embedding_key=False):
        tab_title = self.settings.value(f"{provider_id}_tab_name", default_tab_title)
        
        tab = QWidget()
        layout = QVBoxLayout(tab)
        ui = {'tab_widget': tab} 
        
        creds_layout = QVBoxLayout()
        
        # --- БЛОК 1: Основной ключ ---
        lbl_main_key = QLabel("API Key (Для чата и генерации кода):")
        lbl_main_key.setStyleSheet("color: #d4d4d4; font-weight: bold;")
        creds_layout.addWidget(lbl_main_key)
        ui['key'] = self._create_input_field(is_password=True, placeholder=key_placeholder)
        creds_layout.addWidget(ui['key'])
        
        if has_base_url:
            creds_layout.addWidget(QLabel("Base URL:"))
            ui['url'] = self._create_input_field(placeholder="https://api...")
            creds_layout.addWidget(ui['url'])
        else:
            ui['url'] = None
            
        # --- БЛОК 2: Пул ключей RAG (Динамический) ---
        if has_embedding_key:
            lbl_emb_key = QLabel("Пул ключей Embedding (Для RAG / Авто-ротации):")
            lbl_emb_key.setStyleSheet("color: #e6a822; font-weight: bold; margin-top: 10px;")
            creds_layout.addWidget(lbl_emb_key)
            
            ui['emb_keys_layout'] = QVBoxLayout()
            ui['emb_keys_layout'].setSpacing(5)
            creds_layout.addLayout(ui['emb_keys_layout'])
            
            btn_add_key = QPushButton("➕ Добавить резервный ключ")
            btn_add_key.setStyleSheet("background-color: #333333; color: #d4d4d4; padding: 4px; border-radius: 3px; font-weight: bold;")
            btn_add_key.clicked.connect(lambda _, l=ui['emb_keys_layout']: self._add_emb_key_row(l))
            creds_layout.addWidget(btn_add_key)
            
        layout.addLayout(creds_layout)
        layout.addSpacing(5)
        
        list_header_layout = QHBoxLayout()
        
        ui['search'] = self._create_input_field(placeholder="🔍 Поиск по модели или примечанию...")
        ui['search'].setStyleSheet("background-color: #1e1e1e; border: 1px solid #3c3c3c; padding: 6px; border-radius: 3px; font-size: 13px;")
        list_header_layout.addWidget(ui['search'], stretch=2)
        
        ui['btn_fetch'] = QPushButton("🔄 Загрузить список")
        ui['btn_fetch'].setStyleSheet("background-color: #0e639c; color: white; padding: 6px 15px; border-radius: 4px; font-weight: bold;")
        list_header_layout.addWidget(ui['btn_fetch'], stretch=1)
        
        if is_custom:
            ui['btn_delete'] = QPushButton("🗑️")
            ui['btn_delete'].setToolTip("Удалить провайдера")
            ui['btn_delete'].setStyleSheet("background-color: #d32f2f; color: white; padding: 6px 10px; border-radius: 4px;")
            ui['btn_delete'].clicked.connect(lambda: self.delete_custom_provider(provider_id, tab))
            list_header_layout.addWidget(ui['btn_delete'])
            
        layout.addLayout(list_header_layout)
        
        ui['list_models'] = QListWidget()
        ui['list_models'].setStyleSheet("""
            QListWidget { background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; font-size: 13px; outline: none; padding: 5px; }
            QListWidget::item { padding: 4px; margin: 2px; border-radius: 3px; }
            QListWidget::item:hover { background-color: #2a2d2e; }
            QListWidget::indicator { width: 16px; height: 16px; border: 1px solid #888; border-radius: 3px; background-color: #1e1e1e; }
            QListWidget::indicator:checked { background-color: #31a24c; border: 1px solid #31a24c; }
        """)
        ui['list_models'].setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        ui['list_models'].setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        ui['list_models'].customContextMenuRequested.connect(lambda pos, pid=provider_id: self.show_list_context_menu(pos, pid))
        layout.addWidget(ui['list_models'])
        
        ui['search'].textChanged.connect(lambda text, lw=ui['list_models']: self._filter_models(text, lw))
        
        sel_layout = QHBoxLayout()
        ui['btn_sel_all'] = QPushButton("Выбрать все")
        ui['btn_sel_all'].setStyleSheet("background-color: #333333; padding: 4px 10px; border-radius: 3px;")
        ui['btn_sel_none'] = QPushButton("Снять выделение")
        ui['btn_sel_none'].setStyleSheet("background-color: #333333; padding: 4px 10px; border-radius: 3px;")
        sel_layout.addWidget(ui['btn_sel_all'])
        sel_layout.addWidget(ui['btn_sel_none'])
        sel_layout.addStretch()
        layout.addLayout(sel_layout)
        
        verify_layout = QHBoxLayout()
        ui['btn_verify'] = QPushButton("🚀 Проверить выбранные модели")
        ui['btn_verify'].setStyleSheet("background-color: #b26500; color: white; padding: 10px; border-radius: 4px; font-weight: bold; font-size: 14px;")
        verify_layout.addWidget(ui['btn_verify'])
        layout.addLayout(verify_layout)
        
        ui['lbl_status'] = QLabel("Готово к работе. Загрузите или выберите модели.")
        ui['lbl_status'].setStyleSheet("color: #888888; margin-top: 5px;")
        ui['lbl_status'].setWordWrap(True)
        layout.addWidget(ui['lbl_status'])
        
        ui['is_custom'] = is_custom
        self.tabs_ui[provider_id] = ui
        self.tabs.addTab(tab, tab_title)
        
        ui['btn_fetch'].clicked.connect(lambda: self.fetch_models(provider_id))
        ui['btn_sel_all'].clicked.connect(lambda: self._toggle_list_selection(provider_id, True))
        ui['btn_sel_none'].clicked.connect(lambda: self._toggle_list_selection(provider_id, False))
        ui['btn_verify'].clicked.connect(lambda: self.start_batch_verification(provider_id))

    def _filter_models(self, text, list_widget):
        search_text = text.lower()
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            clean_name = item.data(ROLE_NAME).lower()
            note = (item.data(ROLE_NOTE) or "").lower()
            item.setHidden(search_text not in clean_name and search_text not in note)

    def _show_tab_context_menu(self, pos):
        index = self.tabs.tabBar().tabAt(pos)
        if index < 0: return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; }
            QMenu::item { padding: 6px 20px; font-size: 13px; }
            QMenu::item:selected { background-color: #0e639c; }
        """)
        
        action_rename = menu.addAction("✏️ Переименовать вкладку")
        action = menu.exec(self.tabs.tabBar().mapToGlobal(pos))
        
        if action == action_rename:
            old_name = self.tabs.tabText(index)
            new_name, ok = QInputDialog.getText(self, "Переименование", "Новое имя вкладки:", text=old_name)
            
            if ok and new_name.strip():
                clean_name = new_name.strip()
                self.tabs.setTabText(index, clean_name)
                
                target_widget = self.tabs.widget(index)
                for pid, ui in self.tabs_ui.items():
                    if ui['tab_widget'] == target_widget:
                        self.settings.setValue(f"{pid}_tab_name", clean_name)
                        break

    def show_list_context_menu(self, pos, provider_id):
        ui = self.tabs_ui[provider_id]
        list_widget = ui['list_models']
        item = list_widget.itemAt(pos)
        if not item: return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; }
            QMenu::item { padding: 6px 20px; font-size: 13px; }
            QMenu::item:selected { background-color: #0e639c; }
            QMenu::separator { height: 1px; background: #3c3c3c; margin: 4px 0; }
        """)
        
        action_note = menu.addAction("📝 Изменить примечание")
        action_del_note = None
        if item.data(ROLE_NOTE):
            action_del_note = menu.addAction("🗑️ Удалить примечание")
            
        menu.addSeparator()
        action_reverify = menu.addAction("🔄 Проверить эту модель заново")
        menu.addSeparator()
        action_copy_name = menu.addAction("📋 Копировать имя модели")
        
        tooltip = item.toolTip()
        action_copy_error = None
        if tooltip and item.data(ROLE_STATUS) == "error":
            action_copy_error = menu.addAction("⚠️ Копировать текст ошибки")

        action = menu.exec(list_widget.mapToGlobal(pos))
        
        if action:
            clean_name = item.data(ROLE_NAME)
            
            if action == action_note:
                old_note = item.data(ROLE_NOTE) or ""
                new_note, ok = QInputDialog.getText(self, "Примечание", f"Заметка для {clean_name}:", text=old_note)
                if ok:
                    item.setData(ROLE_NOTE, new_note.strip())
                    self._update_item_display(item)
                    ui['lbl_status'].setText("Примечание обновлено. Не забудьте 'Сохранить всё'.")
                    ui['lbl_status'].setStyleSheet("color: #e6a822;")
                    
            elif action_del_note and action == action_del_note:
                item.setData(ROLE_NOTE, "")
                self._update_item_display(item)
                
            elif action == action_copy_name:
                QApplication.clipboard().setText(clean_name)
                ui['lbl_status'].setText("Имя модели скопировано в буфер обмена!")
                ui['lbl_status'].setStyleSheet("color: #31a24c;")
                
            elif action_copy_error and action == action_copy_error:
                QApplication.clipboard().setText(tooltip)
                ui['lbl_status'].setText("Текст ошибки скопирован в буфер обмена!")
                ui['lbl_status'].setStyleSheet("color: #31a24c;")
                
            elif action == action_reverify:
                item.setData(ROLE_STATUS, "loading")
                item.setToolTip("") 
                self._update_item_display(item)
                provider = self._get_provider_instance(provider_id)
                if provider:
                    self._verify_queue(provider_id, provider, [item], 0)

    def _toggle_list_selection(self, provider_id, check):
        list_widget = self.tabs_ui[provider_id]['list_models']
        state = Qt.CheckState.Checked if check else Qt.CheckState.Unchecked
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(state)

    def _get_provider_instance(self, provider_id):
        ui = self.tabs_ui[provider_id]
        key = ui['key'].text().strip()
        url = ui['url'].text().strip() if ui['url'] else None
        
        if not key and provider_id != "OpenAI" and not ui['is_custom']: 
            pass 
            
        if provider_id == "OpenAI": return OpenAIProvider(key, url)
        elif provider_id == "Anthropic": return AnthropicProvider(key, url)
        elif provider_id == "Gemini": return GeminiAPIProvider(key)
        else:
            return OpenAIProvider(key, url)

    def load_custom_tabs(self):
        custom_data = self.settings.value("custom_providers", "[]")
        try:
            providers = json.loads(custom_data)
            for p in providers:
                self.create_provider_tab(p['id'], f"⚙️ {p['name']}", "sk-... (Опционально)", has_base_url=True, is_custom=True)
                self.tabs_ui[p['id']]['key'].setText(p.get('key', ''))
                self.tabs_ui[p['id']]['url'].setText(p.get('url', ''))
        except Exception as e:
            print(f"Ошибка загрузки кастомных провайдеров: {e}")

    def add_custom_provider_dialog(self):
        name, ok = QInputDialog.getText(self, "Новый провайдер", "Введите имя (например: OpenRouter, Groq, Ollama):")
        if ok and name.strip():
            p_id = f"custom_{uuid.uuid4().hex[:8]}"
            self.create_provider_tab(p_id, f"⚙️ {name.strip()}", "sk-... (Опционально)", has_base_url=True, is_custom=True)
            self.tabs.setCurrentIndex(self.tabs.count() - 1) 

    def delete_custom_provider(self, provider_id, tab_widget):
        reply = QMessageBox.question(self, "Удаление", "Удалить этого провайдера навсегда?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            index = self.tabs.indexOf(tab_widget)
            if index != -1:
                self.tabs.removeTab(index)
            if provider_id in self.tabs_ui:
                del self.tabs_ui[provider_id]
            self.settings.remove(f"{provider_id}_verified")
            self.settings.remove(f"{provider_id}_model_states")
            self.settings.remove(f"{provider_id}_tab_name")

    def fetch_models(self, provider_id):
        ui = self.tabs_ui[provider_id]
        provider = self._get_provider_instance(provider_id)
        if not provider:
            ui['lbl_status'].setText("❌ Введите API ключ и URL!")
            ui['lbl_status'].setStyleSheet("color: #ff4444;")
            return
            
        ui['btn_fetch'].setText("⏳ Загрузка...")
        ui['btn_fetch'].setEnabled(False)
        ui['lbl_status'].setText("Подключение к серверу...")
        ui['lbl_status'].setStyleSheet("color: #e6a822;")
        
        worker = VerificationWorker(provider, 'fetch_models')
        worker.models_fetched.connect(lambda models: self._on_models_fetched(models, provider_id))
        worker.error_signal.connect(lambda err: self._on_worker_error(err, provider_id))
        
        self.workers.append(worker)
        worker.start()

    def _on_models_fetched(self, models, provider_id):
        ui = self.tabs_ui[provider_id]
        ui['btn_fetch'].setText("🔄 Загрузить список")
        ui['btn_fetch'].setEnabled(True)
        
        list_widget = ui['list_models']
        list_widget.clear()
        
        if models:
            states_json = self.settings.value(f"{provider_id}_model_states", "{}")
            try:
                states = json.loads(states_json)
            except:
                states = {}

            for m in models:
                item = QListWidgetItem()
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                
                item.setData(ROLE_NAME, m)
                state_info = states.get(m, {})
                item.setCheckState(Qt.CheckState.Checked if state_info.get("checked") else Qt.CheckState.Unchecked)
                item.setData(ROLE_STATUS, state_info.get("state", "unknown"))
                item.setData(ROLE_NOTE, state_info.get("note", ""))
                item.setData(ROLE_LAST_TESTED, state_info.get("last_tested", ""))
                item.setData(ROLE_IS_NEW, False) 
                item.setToolTip(state_info.get("msg", ""))
                
                self._update_item_display(item)
                list_widget.addItem(item)
                
            current_search = ui['search'].text()
            if current_search:
                self._filter_models(current_search, list_widget)
                
            ui['lbl_status'].setText(f"✅ Успешно загружено {len(models)} моделей.")
            ui['lbl_status'].setStyleSheet("color: #31a24c;")
        else:
            ui['lbl_status'].setText("⚠️ Сервер не вернул список моделей.")
            ui['lbl_status'].setStyleSheet("color: #e6a822;")

    def start_batch_verification(self, provider_id):
        ui = self.tabs_ui[provider_id]
        list_widget = ui['list_models']
        
        items_to_verify = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                items_to_verify.append(item)
                
        if not items_to_verify:
            ui['lbl_status'].setText("❌ Сначала отметьте галочками модели для проверки!")
            ui['lbl_status'].setStyleSheet("color: #ff4444;")
            return
            
        provider = self._get_provider_instance(provider_id)
        if not provider: return

        ui['btn_verify'].setEnabled(False)
        ui['btn_fetch'].setEnabled(False)
        ui['btn_sel_all'].setEnabled(False)
        ui['btn_sel_none'].setEnabled(False)
        
        for item in items_to_verify:
            item.setData(ROLE_STATUS, "unknown")
            item.setToolTip("") 
            self._update_item_display(item)
            
        self._verify_queue(provider_id, provider, items_to_verify, 0)

    def _verify_queue(self, provider_id, provider, items, index):
        ui = self.tabs_ui[provider_id]
        
        if index >= len(items):
            ui['lbl_status'].setText(f"🏁 Пакетная проверка завершена! Проверено {len(items)} моделей. Нажмите 'Сохранить'.")
            ui['lbl_status'].setStyleSheet("color: #31a24c;")
            ui['btn_verify'].setEnabled(True)
            ui['btn_fetch'].setEnabled(True)
            ui['btn_sel_all'].setEnabled(True)
            ui['btn_sel_none'].setEnabled(True)
            return

        item = items[index]
        clean_name = item.data(ROLE_NAME)
        
        item.setData(ROLE_STATUS, "loading")
        self._update_item_display(item)
        
        ui['lbl_status'].setText(f"Проверка [{index+1}/{len(items)}]: {clean_name}...")
        ui['lbl_status'].setStyleSheet("color: #e6a822;")
        
        ui['list_models'].scrollToItem(item)

        worker = VerificationWorker(provider, 'verify', model_to_verify=clean_name)
        
        def on_done(success, msg):
            item.setData(ROLE_STATUS, "ok" if success else "error")
            item.setData(ROLE_LAST_TESTED, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            item.setData(ROLE_IS_NEW, True) 
            
            if not success:
                item.setToolTip(msg) 
            self._update_item_display(item)
                
            QTimer.singleShot(1500, lambda: self._verify_queue(provider_id, provider, items, index + 1))
            
        worker.verification_done.connect(on_done)
        worker.error_signal.connect(lambda err: on_done(False, err))
        
        self.workers.append(worker)
        worker.start()

    def _on_worker_error(self, err_msg, provider_id):
        ui = self.tabs_ui[provider_id]
        ui['btn_fetch'].setText("🔄 Загрузить список")
        ui['btn_fetch'].setEnabled(True)
        ui['lbl_status'].setText(f"❌ Ошибка: {err_msg}")
        ui['lbl_status'].setStyleSheet("color: #ff4444;")

    def load_settings(self):
        # Читаем основные ключи
        if 'OpenAI' in self.tabs_ui:
            self.tabs_ui['OpenAI']['key'].setText(self.settings.value("openai_api_key", ""))
            self.tabs_ui['OpenAI']['url'].setText(self.settings.value("openai_base_url", "https://api.openai.com/v1"))
            if 'emb_keys_layout' in self.tabs_ui['OpenAI']:
                self._load_emb_keys(self.tabs_ui['OpenAI']['emb_keys_layout'], self.settings.value("openai_embedding_key", "[]"))
        
        if 'Anthropic' in self.tabs_ui:
            self.tabs_ui['Anthropic']['key'].setText(self.settings.value("anthropic_api_key", ""))
            self.tabs_ui['Anthropic']['url'].setText(self.settings.value("anthropic_base_url", "https://api.anthropic.com"))
            
        if 'Gemini' in self.tabs_ui:
            self.tabs_ui['Gemini']['key'].setText(self.settings.value("gemini_api_key", ""))
            if 'emb_keys_layout' in self.tabs_ui['Gemini']:
                self._load_emb_keys(self.tabs_ui['Gemini']['emb_keys_layout'], self.settings.value("gemini_embedding_key", "[]"))

        for p_id, ui in self.tabs_ui.items():
            states_json = self.settings.value(f"{p_id}_model_states", "{}")
            try:
                states = json.loads(states_json)
                for m, info in states.items():
                    item = QListWidgetItem()
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    
                    item.setData(ROLE_NAME, m)
                    item.setCheckState(Qt.CheckState.Checked if info.get("checked") else Qt.CheckState.Unchecked)
                    item.setData(ROLE_STATUS, info.get("state", "unknown"))
                    item.setData(ROLE_NOTE, info.get("note", ""))
                    item.setData(ROLE_LAST_TESTED, info.get("last_tested", ""))
                    item.setData(ROLE_IS_NEW, False) 
                    item.setToolTip(info.get("msg", ""))
                    
                    self._update_item_display(item)
                    ui['list_models'].addItem(item)
            except:
                pass

    def save_settings(self):
        custom_providers_data = []

        for p_id, ui in self.tabs_ui.items():
            key_val = ui['key'].text().strip()
            url_val = ui['url'].text().strip() if ui['url'] else ""
            
            if not ui['is_custom']:
                self.settings.setValue(f"{p_id.lower()}_api_key", key_val)
                
                # --- УМНОЕ СОХРАНЕНИЕ ПУЛА RAG КЛЮЧЕЙ В JSON ---
                if 'emb_keys_layout' in ui:
                    keys_list = []
                    for i in range(ui['emb_keys_layout'].count()):
                        row_w = ui['emb_keys_layout'].itemAt(i).widget()
                        if row_w and hasattr(row_w, 'le_key'):
                            k_val = row_w.le_key.text().strip()
                            if k_val:
                                keys_list.append({
                                    "key": k_val,
                                    "enabled": row_w.cb_enabled.isChecked(),
                                    "comment": row_w.le_comment.text().strip()
                                })
                    self.settings.setValue(f"{p_id.lower()}_embedding_key", json.dumps(keys_list))
                    
                if ui['url']:
                    default_url = "https://api.openai.com/v1" if p_id == "OpenAI" else "https://api.anthropic.com"
                    self.settings.setValue(f"{p_id.lower()}_base_url", url_val or default_url)
            else:
                clean_name = self.tabs.tabText(self.tabs.indexOf(ui['tab_widget'])).replace("⚙️ ", "")
                custom_providers_data.append({
                    "id": p_id,
                    "name": clean_name,
                    "key": key_val,
                    "url": url_val
                })

            verified_models = []
            model_states = {}
            list_widget = ui['list_models']
            
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                clean_name = item.data(ROLE_NAME)
                status = item.data(ROLE_STATUS)
                note = item.data(ROLE_NOTE)
                last_tested = item.data(ROLE_LAST_TESTED)
                is_checked = item.checkState() == Qt.CheckState.Checked
                
                item.setData(ROLE_IS_NEW, False)
                self._update_item_display(item)
                
                model_states[clean_name] = {
                    "state": status,
                    "msg": item.toolTip(),
                    "checked": is_checked,
                    "note": note,
                    "last_tested": last_tested
                }
                
                if is_checked and status == "ok":
                    verified_models.append(clean_name)
                    
            self.settings.setValue(f"{p_id}_verified", verified_models) 
            self.settings.setValue(f"{p_id}_model_states", json.dumps(model_states)) 

        self.settings.setValue("custom_providers", json.dumps(custom_providers_data))
        
        QMessageBox.information(self, "Успех", "✅ Настройки API и статусы моделей успешно сохранены!")
        self.accept()