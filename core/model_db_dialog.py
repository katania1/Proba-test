from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QInputDialog, QAbstractItemView,
                             QMenu, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import Qt

# Умные роли для хранения данных в элементах (дублируем для независимости файла)
ROLE_NAME = Qt.ItemDataRole.UserRole
ROLE_STATUS = Qt.ItemDataRole.UserRole + 1
ROLE_NOTE = Qt.ItemDataRole.UserRole + 2
ROLE_LAST_TESTED = Qt.ItemDataRole.UserRole + 3
ROLE_IS_NEW = Qt.ItemDataRole.UserRole + 4
ROLE_PROVIDER = Qt.ItemDataRole.UserRole + 5

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
        
        # Парсим данные напрямую из интерфейса родительского окна
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