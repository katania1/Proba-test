import os
import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QListWidget, QAbstractItemView,
                             QSizePolicy)
from PyQt6.QtCore import Qt

# Импортируем роли и переиспользуемые виджеты из нашего модуля компонентов
from core.settings_components import (ROLE_NAME, ROLE_NOTE, ROLE_STATUS, 
                                      ROLE_LAST_TESTED, ROLE_IS_NEW, 
                                      RagKeyRowWidget)


class ProviderTabWidget(QWidget):
    """
    Изолированный виджет содержимого вкладки настроек конкретного API-провайдера.
    Инкапсулирует всю внутреннюю верстку и локальную логику.
    """
    def __init__(self, provider_id, key_placeholder, has_base_url=True, 
                 is_custom=False, has_embedding_key=False, 
                 callbacks=None, parent=None):
        super().__init__(parent)
        self.provider_id = provider_id
        self.key_placeholder = key_placeholder
        self.has_base_url = has_base_url
        self.is_custom = is_custom
        self.has_embedding_key = has_embedding_key
        self.callbacks = callbacks or {}
        
        # Внутренние ссылки на элементы интерфейса для быстрого доступа
        self.key_input = None
        self.url_input = None
        self.emb_keys_container = None 
        self.emb_keys_layout = None
        self.search_input = None
        self.btn_fetch = None
        self.btn_delete = None
        self.list_models = None
        self.btn_sel_all = None
        self.btn_sel_none = None
        self.btn_verify = None
        self.lbl_status = None
        
        self.init_ui()

    def showEvent(self, event):
        super().showEvent(event)

    def _create_standard_input(self, is_password=False, placeholder=""):
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        line_edit.setStyleSheet(
            "background-color: #252526; border: 1px solid #3c3c3c; "
            "padding: 6px; border-radius: 3px; font-family: Consolas, monospace;"
        )
        if is_password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        return line_edit

    def init_ui(self):
        # Главный макет вкладки
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        
        # ==========================================
        # ВЕРХНИЙ ХОЛСТ (Настройки API и Ключи)
        # ==========================================
        self.top_widget = QWidget(self)
        self.top_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed) 
        self.top_layout = QVBoxLayout(self.top_widget)
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        self.top_layout.setSpacing(5)
        
        # --- БЛОК 1: Основной ключ ---
        lbl_main_key = QLabel("API Key (Для чата и генерации кода):")
        lbl_main_key.setStyleSheet("color: #d4d4d4; font-weight: bold;")
        self.top_layout.addWidget(lbl_main_key)
        
        self.key_input = self._create_standard_input(is_password=True, placeholder=self.key_placeholder)
        self.top_layout.addWidget(self.key_input)
        
        if self.has_base_url:
            self.top_layout.addWidget(QLabel("Base URL:"))
            self.url_input = self._create_standard_input(placeholder="https://api...")
            self.top_layout.addWidget(self.url_input)
        else:
            self.url_input = None
            
        # --- БЛОК 2: Пул ключей RAG ---
        if self.has_embedding_key:
            lbl_emb_key = QLabel("Пул ключей Embedding (Для RAG / Авто-ротации):")
            lbl_emb_key.setStyleSheet("color: #e6a822; font-weight: bold; margin-top: 10px;")
            self.top_layout.addWidget(lbl_emb_key)
            
            # Изолированный контейнер ТОЛЬКО для строк RAG-ключей
            self.emb_keys_container = QWidget(self.top_widget)
            self.emb_keys_layout = QVBoxLayout(self.emb_keys_container)
            self.emb_keys_layout.setContentsMargins(0, 0, 0, 0)
            self.emb_keys_layout.setSpacing(5)
            self.top_layout.addWidget(self.emb_keys_container)
            
            self.btn_add_key = QPushButton("➕ Добавить резервный ключ")
            self.btn_add_key.setStyleSheet(
                "background-color: #333333; color: #d4d4d4; "
                "padding: 6px; border-radius: 3px; font-weight: bold;"
            )
            self.btn_add_key.clicked.connect(self.add_emb_key_row)
            self.top_layout.addWidget(self.btn_add_key)
        
        self.main_layout.addWidget(self.top_widget)
        self.main_layout.addSpacing(5)
        
        # ==========================================
        # НИЖНИЙ ХОЛСТ (Список моделей)
        # ==========================================
        list_header_layout = QHBoxLayout()
        
        self.search_input = self._create_standard_input(placeholder="🔍 Поиск по модели или примечанию...")
        self.search_input.setStyleSheet(
            "background-color: #1e1e1e; border: 1px solid #3c3c3c; "
            "padding: 6px; border-radius: 3px; font-size: 13px;"
        )
        list_header_layout.addWidget(self.search_input, stretch=2)
        
        self.btn_fetch = QPushButton("🔄 Загрузить список")
        self.btn_fetch.setStyleSheet(
            "background-color: #0e639c; color: white; "
            "padding: 6px 15px; border-radius: 4px; font-weight: bold;"
        )
        list_header_layout.addWidget(self.btn_fetch, stretch=1)
        
        if self.is_custom:
            self.btn_delete = QPushButton("🗑️")
            self.btn_delete.setToolTip("Удалить провайдера")
            self.btn_delete.setStyleSheet(
                "background-color: #d32f2f; color: white; padding: 6px 10px; border-radius: 4px;"
            )
            if "delete_provider" in self.callbacks:
                self.btn_delete.clicked.connect(self.callbacks["delete_provider"])
            list_header_layout.addWidget(self.btn_delete)
            
        self.main_layout.addLayout(list_header_layout)
        
        self.list_models = QListWidget()
        self.list_models.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.list_models.setStyleSheet("""
            QListWidget { background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; font-size: 13px; outline: none; padding: 5px; }
            QListWidget::item { padding: 4px; margin: 2px; border-radius: 3px; }
            QListWidget::item:hover { background-color: #2a2d2e; }
            QListWidget::indicator { width: 16px; height: 16px; border: 1px solid #888; border-radius: 3px; background-color: #1e1e1e; }
            QListWidget::indicator:checked { background-color: #31a24c; border: 1px solid #31a24c; }
        """)
        self.list_models.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_models.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        if "context_menu" in self.callbacks:
            self.list_models.customContextMenuRequested.connect(self.callbacks["context_menu"])
            
        self.main_layout.addWidget(self.list_models, stretch=1) 
        
        self.search_input.textChanged.connect(self.filter_models)
        
        sel_layout = QHBoxLayout()
        self.btn_sel_all = QPushButton("Выбрать все")
        self.btn_sel_all.setStyleSheet("background-color: #333333; padding: 4px 10px; border-radius: 3px;")
        
        self.btn_sel_none = QPushButton("Снять выделение")
        self.btn_sel_none.setStyleSheet("background-color: #333333; padding: 4px 10px; border-radius: 3px;")
        
        sel_layout.addWidget(self.btn_sel_all)
        sel_layout.addWidget(self.btn_sel_none)
        sel_layout.addStretch()
        self.main_layout.addLayout(sel_layout)
        
        verify_layout = QHBoxLayout()
        self.btn_verify = QPushButton("🚀 Проверить выбранные модели")
        self.btn_verify.setStyleSheet(
            "background-color: #b26500; color: white; padding: 10px; "
            "border-radius: 4px; font-weight: bold; font-size: 14px;"
        )
        verify_layout.addWidget(self.btn_verify)
        self.main_layout.addLayout(verify_layout)
        
        self.lbl_status = QLabel("Готово к работе. Загрузите или выберите models.")
        self.lbl_status.setStyleSheet("color: #888888; margin-top: 5px;")
        self.lbl_status.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_status)
        
        if "fetch_models" in self.callbacks:
            self.btn_fetch.clicked.connect(self.callbacks["fetch_models"])
        if "verify_models" in self.callbacks:
            self.btn_verify.clicked.connect(self.callbacks["verify_models"])
            
        self.btn_sel_all.clicked.connect(lambda: self.toggle_selection(True))
        self.btn_sel_none.clicked.connect(lambda: self.toggle_selection(False))

    def filter_models(self, text):
        search_text = text.lower()
        for i in range(self.list_models.count()):
            item = self.list_models.item(i)
            clean_name = item.data(ROLE_NAME).lower()
            note = (item.data(ROLE_NOTE) or "").lower()
            item.setHidden(search_text not in clean_name and search_text not in note)

    def toggle_selection(self, check):
        state = Qt.CheckState.Checked if check else Qt.CheckState.Unchecked
        for i in range(self.list_models.count()):
            item = self.list_models.item(i)
            if not item.isHidden():
                item.setCheckState(state)

    def add_emb_key_row(self, key_data=None):
        """Добавляет новую строку ввода ключа RAG в динамический пул"""
        # ✅ ФИКС КРАША: Если функция вызвана кнопкой (передан False), обнуляем до None
        if isinstance(key_data, bool):
            key_data = None
            
        if self.emb_keys_layout is None:
            return
            
        def remove_row(row_widget):
            self.emb_keys_layout.removeWidget(row_widget)
            row_widget.setParent(None) 
            row_widget.deleteLater()
            
        row_w = RagKeyRowWidget(
            key_data=key_data, 
            removal_callback=remove_row,
            parent=self.emb_keys_container
        )
        self.emb_keys_layout.addWidget(row_w)
        row_w.show()

    def load_emb_keys(self, keys_json_str):
        """Загружает и отрисовывает пул ключей RAG из JSON-строки настроек."""
        # ✅ ФИКС: Проверяем именно на None
        if self.emb_keys_layout is None:
            return
            
        while self.emb_keys_layout.count():
            item = self.emb_keys_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
                
        try:
            keys_data = json.loads(keys_json_str)
            if not isinstance(keys_data, list):
                raise ValueError("Неверный формат")
        except Exception:
            keys_data = [
                {"key": k.strip(), "enabled": True, "comment": ""} 
                for k in keys_json_str.split(',') if k.strip()
            ]
            
        if not keys_data:
            self.add_emb_key_row()
        else:
            for k_data in keys_data:
                self.add_emb_key_row(k_data)

    def get_emb_keys_data(self):
        """Сбор актуальных данных из всех строк пула RAG для сохранения в QSettings"""
        # ✅ ФИКС: Проверяем именно на None
        if self.emb_keys_layout is None:
            return []
            
        keys_list = []
        for i in range(self.emb_keys_layout.count()):
            row_w = self.emb_keys_layout.itemAt(i).widget()
            if row_w and hasattr(row_w, 'le_key'):
                k_val = row_w.le_key.text().strip()
                if k_val:
                    keys_list.append({
                        "key": k_val,
                        "enabled": row_w.cb_enabled.isChecked(),
                        "comment": row_w.le_comment.text().strip()
                    })
        return keys_list

    def to_ui_dict(self):
        return {
            'tab_widget': self,
            'key': self.key_input,
            'url': self.url_input,
            'emb_keys_layout': self.emb_keys_layout,
            'search': self.search_input,
            'btn_fetch': self.btn_fetch,
            'btn_delete': self.btn_delete,
            'list_models': self.list_models,
            'btn_sel_all': self.btn_sel_all,
            'btn_sel_none': self.btn_sel_none,
            'btn_verify': self.btn_verify,
            'lbl_status': self.lbl_status,
            'is_custom': self.is_custom
        }