import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QSplitter, 
                             QListWidget, QTextBrowser, QLineEdit, QListWidgetItem,
                             QPushButton)
from PyQt6.QtCore import Qt

class HistoryDialog(QDialog):
    def __init__(self, parent, chat_logger):
        super().__init__(parent)
        self.chat_logger = chat_logger
        self.setWindowTitle("📜 Умная история проекта")
        self.resize(1000, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        self.logs = self.chat_logger.get_all()
        self.sort_descending = True
        self.init_ui()
        self.populate_list()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Тулбар (Поиск и сортировка)
        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Мгновенный поиск по запросам, ответам и мыслям ИИ...")
        self.search_input.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; padding: 6px; font-size: 14px;")
        self.search_input.textChanged.connect(self.populate_list)
        
        self.btn_sort = QPushButton("⬇️ Новые сверху")
        self.btn_sort.setStyleSheet("background-color: #3c3c3c; padding: 6px 15px; font-weight: bold; border-radius: 3px;")
        self.btn_sort.clicked.connect(self.toggle_sort)
        
        toolbar.addWidget(self.search_input)
        toolbar.addWidget(self.btn_sort)
        layout.addLayout(toolbar)
        
        # Сплиттер (Список слева, детали справа)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.log_list = QListWidget()
        self.log_list.setStyleSheet("QListWidget { background-color: #252526; border: 1px solid #3c3c3c; font-size: 13px; } QListWidget::item { padding: 8px; border-bottom: 1px solid #333; } QListWidget::item:selected { background-color: #0e639c; }")
        self.log_list.itemSelectionChanged.connect(self.show_details)
        
        self.details_view = QTextBrowser()
        self.details_view.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3c3c3c; font-family: Consolas; padding: 10px; font-size: 13px;")
        
        self.splitter.addWidget(self.log_list)
        self.splitter.addWidget(self.details_view)
        self.splitter.setSizes([350, 650])
        
        layout.addWidget(self.splitter)

    def toggle_sort(self):
        self.sort_descending = not self.sort_descending
        self.btn_sort.setText("⬇️ Новые сверху" if self.sort_descending else "⬆️ Старые сверху")
        self.populate_list()

    def populate_list(self):
        self.log_list.clear()
        search_text = self.search_input.text().lower()
        
        # Фильтрация
        filtered_logs = []
        for log in self.logs:
            content = log.get("content", "").lower()
            hidden = log.get("hidden_data", "").lower()
            if search_text in content or search_text in hidden:
                filtered_logs.append(log)
                
        # Сортировка по времени
        filtered_logs.sort(key=lambda x: x.get("timestamp", 0), reverse=self.sort_descending)
        
        # Добавление в список
        for log in filtered_logs:
            role = log.get("role", "UNKNOWN")
            if role == "SYSTEM": continue # Прячем системные логи для чистоты списка
            
            dt = datetime.datetime.fromtimestamp(log.get("timestamp", 0))
            time_str = dt.strftime("%d.%m %H:%M:%S")
            
            # Очищаем текст от HTML тегов для превью
            preview_text = log.get("content", "").replace("\n", " ").replace("<br>", " ")
            preview = preview_text[:45] + "..." if len(preview_text) > 45 else preview_text
            
            icon = "👤" if role == "USER" else "🤖" if role == "AI" else "🔄"
            
            item = QListWidgetItem(f"{icon} [{time_str}]\n{preview}")
            item.setData(Qt.ItemDataRole.UserRole, log)
            
            if role == "USER": item.setForeground(Qt.GlobalColor.cyan)
            elif role == "AI": item.setForeground(Qt.GlobalColor.green)
            elif role == "RELAY": item.setForeground(Qt.GlobalColor.yellow)
            
            self.log_list.addItem(item)
            
        if self.log_list.count() > 0:
            self.log_list.setCurrentRow(0) # Авто-выбор первого элемента

    def show_details(self):
        selected = self.log_list.selectedItems()
        if not selected: return
        
        log = selected[0].data(Qt.ItemDataRole.UserRole)
        role = log.get("role", "")
        content = log.get("content", "")
        hidden = log.get("hidden_data", "")
        dt = datetime.datetime.fromtimestamp(log.get("timestamp", 0)).strftime("%Y-%m-%d %H:%M:%S")
        
        # Формируем HTML для правой панели
        html = f"<div style='color: #888; margin-bottom: 10px;'><b>Время:</b> {dt} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Роль:</b> {role}</div>"
        html += f"<div style='background-color: #252526; padding: 15px; border-radius: 5px; color: #d4d4d4; white-space: pre-wrap;'>{content}</div>"
        
        if hidden:
            html += f"<div style='margin-top: 20px; color: #888;'><b>Скрытые данные (Промпт Оркестратора / Контекст):</b></div>"
            html += f"<div style='background-color: #1a1a1a; padding: 15px; border-radius: 5px; color: #a0a0a0; white-space: pre-wrap; font-size: 11px;'>{hidden}</div>"
            
        self.details_view.setHtml(html)