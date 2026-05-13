import json
import uuid
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QTabWidget, QMessageBox, QInputDialog, 
                             QMenu, QApplication)
from PyQt6.QtCore import QSettings, Qt

# Импортируем провайдеров
from core.providers import OpenAIProvider, AnthropicProvider, GeminiAPIProvider

# Импортируем роли из модуля компонентов
from core.settings_components import (ROLE_NAME, ROLE_STATUS, ROLE_NOTE, 
                                      ROLE_LAST_TESTED, ROLE_IS_NEW)

# Импортируем изолированные модули рефакторинга (SOLID)
from core.verified_models_dialog import ModelDatabaseDialog
from core.provider_tab import ProviderTabWidget
from core.verification_manager import VerificationQueueManager


class APISettingsDialog(QDialog):
    """
    Главное окно настроек API-провайдеров (Облегченный Роутер).
    Отвечает исключительно за маршрутизацию вкладок, вызов базы моделей
    и чтение/запись параметров сессии через QSettings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Настройки API Провайдеров (Pro)")
        self.resize(750, 750)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        self.settings = QSettings("VibeCoder", "API_Config")
        
        # Инициализация делегированного менеджера очередей (SRP)
        self.queue_manager = VerificationQueueManager(self)
        
        # Словарь для обратной совместимости: хранит UI-ссылки каждой вкладки
        self.tabs_ui = {}
        
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # --- Шапка окна ---
        header_layout = QHBoxLayout()
        lbl_info = QLabel(
            "Отметьте галочками модели, которые хотите видеть в меню программы.\n"
            "Снимите галочку, чтобы скрыть модель. ПКМ — для заметок и переименования."
        )
        lbl_info.setStyleSheet("color: #aaaaaa; font-size: 13px;")
        
        self.btn_db = QPushButton("📚 База проверенных моделей")
        self.btn_db.setStyleSheet(
            "background-color: #4a148c; color: white; padding: 6px 12px; "
            "border-radius: 4px; font-weight: bold;"
        )
        self.btn_db.clicked.connect(self.open_model_database)
        
        self.btn_add_custom = QPushButton("➕ Добавить API (OpenRouter/Groq/etc)")
        self.btn_add_custom.setStyleSheet(
            "background-color: #0e639c; color: white; padding: 6px 12px; "
            "border-radius: 4px; font-weight: bold;"
        )
        self.btn_add_custom.clicked.connect(self.add_custom_provider_dialog)
        
        header_layout.addWidget(lbl_info)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_db)
        header_layout.addWidget(self.btn_add_custom)
        layout.addLayout(header_layout)

        # --- Панель вкладок ---
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

        # Инициализация базовых системных провайдеров
        self.create_provider_tab("OpenAI", "🟢 OpenAI", "sk-...", has_base_url=True, has_embedding_key=True)
        self.create_provider_tab("Anthropic", "🟣 Anthropic", "sk-ant-...", has_base_url=True)
        self.create_provider_tab("Gemini", "🤖 Gemini API", "AIzaSy...", has_base_url=False, has_embedding_key=True)

        self.load_custom_tabs()

        # --- Нижняя панель кнопок ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setStyleSheet(
            "background-color: #333333; padding: 8px 20px; "
            "border-radius: 4px; font-weight: bold;"
        )
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_save = QPushButton("💾 Сохранить всё")
        self.btn_save.setStyleSheet(
            "background-color: #2e7d32; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 4px;"
        )
        self.btn_save.clicked.connect(self.save_settings)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        
        layout.addLayout(btn_layout)

    def _update_item_display(self, item):
        """Проброс метода визуального обновления для окна ModelDatabaseDialog"""
        self.queue_manager.update_item_display(item)

    def open_model_database(self):
        """Открывает дашборд базы всех проверенных моделей"""
        dlg = ModelDatabaseDialog(self)
        dlg.exec()

    def create_provider_tab(self, provider_id, default_tab_title, key_placeholder, 
                            has_base_url=True, is_custom=False, has_embedding_key=False):
        """
        Инициализирует и подключает вкладку провайдера через изолированный
        компонент ProviderTabWidget.
        """
        tab_title = self.settings.value(f"{provider_id}_tab_name", default_tab_title)
        
        # Сборка карты колбэков для делегирования событий в менеджер очередей
        callbacks = {
            "fetch_models": lambda: self.queue_manager.fetch_provider_models(
                provider_id, self.tabs_ui[provider_id], 
                self._get_provider_instance(provider_id), self.settings
            ),
            "verify_models": lambda: self.queue_manager.start_batch_verification(
                provider_id, self.tabs_ui[provider_id], 
                self._get_provider_instance(provider_id)
            ),
            "context_menu": lambda pos: self.show_list_context_menu(pos, provider_id)
        }
        
        if is_custom:
            callbacks["delete_provider"] = lambda: self.delete_custom_provider(
                provider_id, self.tabs_ui[provider_id]['tab_widget']
            )
            
        tab_widget = ProviderTabWidget(
            provider_id=provider_id,
            key_placeholder=key_placeholder,
            has_base_url=has_base_url,
            is_custom=is_custom,
            has_embedding_key=has_embedding_key,
            callbacks=callbacks,
            parent=self
        )
        
        # Экспорт словаря ссылок для полной совместимости с роутингом
        self.tabs_ui[provider_id] = tab_widget.to_ui_dict()
        self.tabs.addTab(tab_widget, tab_title)

    def _show_tab_context_menu(self, pos):
        """Контекстное меню для переименования вкладок в панели QTabBar"""
        index = self.tabs.tabBar().tabAt(pos)
        if index < 0:
            return

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
            new_name, ok = QInputDialog.getText(
                self, "Переименование", "Новое имя вкладки:", text=old_name
            )
            
            if ok and new_name.strip():
                clean_name = new_name.strip()
                self.tabs.setTabText(index, clean_name)
                
                target_widget = self.tabs.widget(index)
                for pid, ui in self.tabs_ui.items():
                    if ui['tab_widget'] == target_widget:
                        self.settings.setValue(f"{pid}_tab_name", clean_name)
                        break

    def show_list_context_menu(self, pos, provider_id):
        """Отрисовка и обработка контекстного меню для элемента списка моделей"""
        ui = self.tabs_ui[provider_id]
        list_widget = ui['list_models']
        item = list_widget.itemAt(pos)
        if not item:
            return

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
                new_note, ok = QInputDialog.getText(
                    self, "Примечание", f"Заметка для {clean_name}:", text=old_note
                )
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
                provider_instance = self._get_provider_instance(provider_id)
                self.queue_manager.verify_single_model(
                    provider_id, ui, provider_instance, item
                )

    def _get_provider_instance(self, provider_id):
        """Фабричный метод инициализации сетевого клиента выбранного API"""
        ui = self.tabs_ui[provider_id]
        key = ui['key'].text().strip()
        url = ui['url'].text().strip() if ui['url'] else None
        
        if provider_id == "OpenAI":
            return OpenAIProvider(key, url)
        elif provider_id == "Anthropic":
            return AnthropicProvider(key, url)
        elif provider_id == "Gemini":
            return GeminiAPIProvider(key)
        else:
            return OpenAIProvider(key, url)

    def load_custom_tabs(self):
        """Динамически загружает и восстанавливает вкладки пользовательских сетей"""
        custom_data = self.settings.value("custom_providers", "[]")
        try:
            providers = json.loads(custom_data)
            for p in providers:
                self.create_provider_tab(
                    p['id'], f"⚙️ {p['name']}", "sk-... (Опционально)", 
                    has_base_url=True, is_custom=True
                )
                self.tabs_ui[p['id']]['key'].setText(p.get('key', ''))
                self.tabs_ui[p['id']]['url'].setText(p.get('url', ''))
        except Exception:
            pass

    def add_custom_provider_dialog(self):
        """Диалог добавления нового пользовательского OpenAI-совместимого эндпоинта"""
        name, ok = QInputDialog.getText(
            self, "Новый провайдер", "Введите имя (например: OpenRouter, Groq, Ollama):"
        )
        if ok and name.strip():
            p_id = f"custom_{uuid.uuid4().hex[:8]}"
            self.create_provider_tab(
                p_id, f"⚙️ {name.strip()}", "sk-... (Опционально)", 
                has_base_url=True, is_custom=True
            )
            self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def delete_custom_provider(self, provider_id, tab_widget):
        """Удаляет вкладку пользовательской сети и затирает связанные с ней ключи"""
        reply = QMessageBox.question(
            self, "Удаление", "Удалить этого провайдера навсегда?", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            index = self.tabs.indexOf(tab_widget)
            if index != -1:
                self.tabs.removeTab(index)
            if provider_id in self.tabs_ui:
                del self.tabs_ui[provider_id]
                
            self.settings.remove(f"{provider_id}_verified")
            self.settings.remove(f"{provider_id}_model_states")
            self.settings.remove(f"{provider_id}_tab_name")

    def load_settings(self):
        """Загружает сохраненные ключи, адреса и списки моделей в элементы UI"""
        if 'OpenAI' in self.tabs_ui:
            self.tabs_ui['OpenAI']['key'].setText(self.settings.value("openai_api_key", ""))
            self.tabs_ui['OpenAI']['url'].setText(
                self.settings.value("openai_base_url", "https://api.openai.com/v1")
            )
            tab_w = self.tabs_ui['OpenAI']['tab_widget']
            tab_w.load_emb_keys(self.settings.value("openai_embedding_key", "[]"))
        
        if 'Anthropic' in self.tabs_ui:
            self.tabs_ui['Anthropic']['key'].setText(self.settings.value("anthropic_api_key", ""))
            self.tabs_ui['Anthropic']['url'].setText(
                self.settings.value("anthropic_base_url", "https://api.anthropic.com")
            )
            
        if 'Gemini' in self.tabs_ui:
            self.tabs_ui['Gemini']['key'].setText(self.settings.value("gemini_api_key", ""))
            tab_w = self.tabs_ui['Gemini']['tab_widget']
            tab_w.load_emb_keys(self.settings.value("gemini_embedding_key", "[]"))

        # Восстановление сохраненного состояния моделей для всех вкладок
        for p_id, ui in self.tabs_ui.items():
            states_json = self.settings.value(f"{p_id}_model_states", "{}")
            try:
                from PyQt6.QtWidgets import QListWidgetItem
                states = json.loads(states_json)
                
                for m, info in states.items():
                    item = QListWidgetItem()
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    
                    item.setData(ROLE_NAME, m)
                    item.setCheckState(
                        Qt.CheckState.Checked if info.get("checked") else Qt.CheckState.Unchecked
                    )
                    item.setData(ROLE_STATUS, info.get("state", "unknown"))
                    item.setData(ROLE_NOTE, info.get("note", ""))
                    item.setData(ROLE_LAST_TESTED, info.get("last_tested", ""))
                    item.setData(ROLE_IS_NEW, False)
                    item.setToolTip(info.get("msg", ""))
                    
                    self._update_item_display(item)
                    ui['list_models'].addItem(item)
            except Exception:
                pass

    def save_settings(self):
        """Собирает и сохраняет все введенные параметры и состояния в реестр"""
        custom_providers_data = []

        for p_id, ui in self.tabs_ui.items():
            tab_w = ui['tab_widget']
            key_val = ui['key'].text().strip()
            url_val = ui['url'].text().strip() if ui['url'] else ""
            
            if not ui['is_custom']:
                self.settings.setValue(f"{p_id.lower()}_api_key", key_val)
                
                # Делегированный сбор JSON-пула резервных ключей RAG
                if hasattr(tab_w, 'get_emb_keys_data'):
                    keys_list = tab_w.get_emb_keys_data()
                    self.settings.setValue(f"{p_id.lower()}_embedding_key", json.dumps(keys_list))
                    
                if ui['url']:
                    default_url = (
                        "https://api.openai.com/v1" if p_id == "OpenAI" 
                        else "https://api.anthropic.com"
                    )
                    self.settings.setValue(f"{p_id.lower()}_base_url", url_val or default_url)
            else:
                clean_name = self.tabs.tabText(self.tabs.indexOf(tab_w)).replace("⚙️ ", "")
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
        
        QMessageBox.information(
            self, "Успех", "✅ Настройки API и статусы моделей успешно сохранены!"
        )
        self.accept()