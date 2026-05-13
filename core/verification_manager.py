from datetime import datetime
from PyQt6.QtCore import QObject, QTimer, Qt

# Импортируем воркер проверки и роли из наших компонентов
from core.verification_worker import VerificationWorker
from core.settings_components import (ROLE_NAME, ROLE_STATUS, ROLE_NOTE, 
                                      ROLE_LAST_TESTED, ROLE_IS_NEW)


class VerificationQueueManager(QObject):
    """
    Оркестратор пакетной проверки моделей (Batch Verification).
    Управляет асинхронной очередью потоков VerificationWorker и визуально
    обновляет элементы UI (статусы, цвета, автоматический скролл).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.workers = []

    def update_item_display(self, item):
        """
        Изолированная логика визуального форматирования элемента списка
        на основе его внутренних ролей данных (SRP).
        """
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

    def start_batch_verification(self, provider_id, tab_ui, provider_instance):
        """
        Запускает процесс проверки для всех отмеченных галочками моделей в списке.
        Блокирует элементы управления на время выполнения.
        """
        list_widget = tab_ui['list_models']
        
        items_to_verify = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                items_to_verify.append(item)
                
        if not items_to_verify:
            tab_ui['lbl_status'].setText("❌ Сначала отметьте галочками модели для проверки!")
            tab_ui['lbl_status'].setStyleSheet("color: #ff4444;")
            return
            
        if not provider_instance:
            return

        # Блокировка интерфейса вкладки
        tab_ui['btn_verify'].setEnabled(False)
        tab_ui['btn_fetch'].setEnabled(False)
        tab_ui['btn_sel_all'].setEnabled(False)
        tab_ui['btn_sel_none'].setEnabled(False)
        
        # Сброс статусов перед стартом
        for item in items_to_verify:
            item.setData(ROLE_STATUS, "unknown")
            item.setToolTip("") 
            self.update_item_display(item)
            
        self._verify_queue(provider_id, provider_instance, tab_ui, items_to_verify, 0)

    def _verify_queue(self, provider_id, provider, tab_ui, items, index):
        """
        Рекурсивный обход очереди проверки с задержкой между запросами.
        """
        if index >= len(items):
            tab_ui['lbl_status'].setText(f"🏁 Пакетная проверка завершена! Проверено {len(items)} моделей. Нажмите 'Сохранить всё'.")
            tab_ui['lbl_status'].setStyleSheet("color: #31a24c;")
            
            # Разблокировка интерфейса
            tab_ui['btn_verify'].setEnabled(True)
            tab_ui['btn_fetch'].setEnabled(True)
            tab_ui['btn_sel_all'].setEnabled(True)
            tab_ui['btn_sel_none'].setEnabled(True)
            return

        item = items[index]
        clean_name = item.data(ROLE_NAME)
        
        item.setData(ROLE_STATUS, "loading")
        self.update_item_display(item)
        
        tab_ui['lbl_status'].setText(f"Проверка [{index+1}/{len(items)}]: {clean_name}...")
        tab_ui['lbl_status'].setStyleSheet("color: #e6a822;")
        
        # Фокусировка и авто-скролл к проверяемой модели
        tab_ui['list_models'].scrollToItem(item)

        worker = VerificationWorker(provider, 'verify', model_to_verify=clean_name)
        
        def on_done(success, msg):
            item.setData(ROLE_STATUS, "ok" if success else "error")
            item.setData(ROLE_LAST_TESTED, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            item.setData(ROLE_IS_NEW, True) 
            
            if not success:
                item.setToolTip(msg) 
            self.update_item_display(item)
                
            # Задержка перед следующим вызовом для предотвращения блокировки (Rate Limit)
            QTimer.singleShot(1500, lambda: self._verify_queue(provider_id, provider, tab_ui, items, index + 1))
            
        worker.verification_done.connect(on_done)
        worker.error_signal.connect(lambda err: on_done(False, err))
        
        self.workers.append(worker)
        worker.start()

    def verify_single_model(self, provider_id, tab_ui, provider_instance, item):
        """
        Точечная проверка одной выбранной модели (например, из контекстного меню).
        """
        if not provider_instance:
            return
            
        clean_name = item.data(ROLE_NAME)
        item.setData(ROLE_STATUS, "loading")
        item.setToolTip("") 
        self.update_item_display(item)
        
        tab_ui['lbl_status'].setText(f"Точечная проверка: {clean_name}...")
        tab_ui['lbl_status'].setStyleSheet("color: #e6a822;")
        
        worker = VerificationWorker(provider_instance, 'verify', model_to_verify=clean_name)
        
        def on_done(success, msg):
            item.setData(ROLE_STATUS, "ok" if success else "error")
            item.setData(ROLE_LAST_TESTED, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            item.setData(ROLE_IS_NEW, True) 
            
            if not success:
                item.setToolTip(msg) 
            self.update_item_display(item)
            
            status_text = "успешно подтверждена" if success else "вернула ошибку"
            color = "#31a24c" if success else "#ff4444"
            tab_ui['lbl_status'].setText(f"Модель {clean_name} {status_text}.")
            tab_ui['lbl_status'].setStyleSheet(f"color: {color};")
            
        worker.verification_done.connect(on_done)
        worker.error_signal.connect(lambda err: on_done(False, err))
        
        self.workers.append(worker)
        worker.start()

    def fetch_provider_models(self, provider_id, tab_ui, provider_instance, settings):
        """
        Загружает актуальный список моделей от провайдера и заполняет виджет списка.
        """
        if not provider_instance:
            tab_ui['lbl_status'].setText("❌ Введите API ключ и URL!")
            tab_ui['lbl_status'].setStyleSheet("color: #ff4444;")
            return
            
        tab_ui['btn_fetch'].setText("⏳ Загрузка...")
        tab_ui['btn_fetch'].setEnabled(False)
        tab_ui['lbl_status'].setText("Подключение к серверу...")
        tab_ui['lbl_status'].setStyleSheet("color: #e6a822;")
        
        worker = VerificationWorker(provider_instance, 'fetch_models')
        
        def on_fetched(models):
            tab_ui['btn_fetch'].setText("🔄 Загрузить список")
            tab_ui['btn_fetch'].setEnabled(True)
            
            list_widget = tab_ui['list_models']
            list_widget.clear()
            
            if models:
                import json
                from PyQt6.QtWidgets import QListWidgetItem
                
                states_json = settings.value(f"{provider_id}_model_states", "{}")
                try:
                    states = json.loads(states_json)
                except Exception:
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
                    
                    self.update_item_display(item)
                    list_widget.addItem(item)
                    
                # Применение активного фильтра поиска, если строка не пуста
                current_search = tab_ui['search'].text()
                if current_search and hasattr(tab_ui['tab_widget'], 'filter_models'):
                    tab_ui['tab_widget'].filter_models(current_search)
                    
                tab_ui['lbl_status'].setText(f"✅ Успешно загружено {len(models)} моделей.")
                tab_ui['lbl_status'].setStyleSheet("color: #31a24c;")
            else:
                tab_ui['lbl_status'].setText("⚠️ Сервер не вернул список моделей.")
                tab_ui['lbl_status'].setStyleSheet("color: #e6a822;")
                
        def on_error(err_msg):
            tab_ui['btn_fetch'].setText("🔄 Загрузить список")
            tab_ui['btn_fetch'].setEnabled(True)
            tab_ui['lbl_status'].setText(f"❌ Ошибка: {err_msg}")
            tab_ui['lbl_status'].setStyleSheet("color: #ff4444;")
            
        worker.models_fetched.connect(on_fetched)
        worker.error_signal.connect(on_error)
        
        self.workers.append(worker)
        worker.start()