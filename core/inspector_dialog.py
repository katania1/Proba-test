import os
import json
from datetime import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, 
                             QWidget, QTextBrowser, QListWidget, QListWidgetItem, 
                             QPushButton, QCheckBox, QLabel, QFileDialog, QApplication, QSplitter)
from PyQt6.QtCore import Qt

class InspectorDialog(QDialog):
    def __init__(self, parent, current_trace=None, trace_id=None):
        super().__init__(parent)
        self.mw = parent
        self.current_trace = current_trace or []
        self.requested_trace_id = trace_id
        
        self.setWindowTitle("🐞 Инспектор отладки и Архив логов")
        self.resize(1000, 700)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        self.init_ui()
        
        # Если открыли по ссылке из чата, переключаемся на архив
        if self.requested_trace_id:
            self.tabs.setCurrentIndex(1)
            self.load_trace_from_archive(self.requested_trace_id)

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3c3c3c; background: #1e1e1e; }
            QTabBar::tab { background: #252526; color: #888888; padding: 8px 15px; border: 1px solid #3c3c3c; border-bottom: none; }
            QTabBar::tab:selected { background: #1e1e1e; color: #569cd6; font-weight: bold; border-top: 2px solid #0e639c; }
        """)
        
        # --- Вкладка 1: Текущая сессия ---
        self.tab_current = QWidget()
        self.setup_trace_view(self.tab_current, self.current_trace, is_archive=False)
        self.tabs.addTab(self.tab_current, "⚡ Текущая задача")
        
        # --- Вкладка 2: Архив за 7 дней ---
        self.tab_archive = QWidget()
        archive_layout = QHBoxLayout(self.tab_archive)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Левая часть архива: Список сессий
        self.list_archive = QListWidget()
        self.list_archive.setStyleSheet("background-color: #252526; border: none; outline: none;")
        self.list_archive.itemClicked.connect(self.on_archive_item_clicked)
        splitter.addWidget(self.list_archive)
        
        # Правая часть архива: Детали (создаем пустой контейнер)
        self.archive_detail_container = QWidget()
        self.setup_trace_view(self.archive_detail_container, [], is_archive=True)
        splitter.addWidget(self.archive_detail_container)
        
        splitter.setSizes([300, 700])
        archive_layout.addWidget(splitter)
        
        self.tabs.addTab(self.tab_archive, "📅 Архив (7 дней)")
        
        layout.addWidget(self.tabs)
        self.load_archive_list()

    def setup_trace_view(self, container, trace_data, is_archive=False):
        """Создает интерфейс просмотра шагов с чекбоксами"""
        layout = QVBoxLayout(container)
        
        header = QHBoxLayout()
        lbl = QLabel("Выберите шаги для экспорта:")
        lbl.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        header.addWidget(lbl)
        header.addStretch()
        
        btn_all = QPushButton("Выбрать все")
        btn_all.setStyleSheet("background-color: #333333; font-size: 10px; padding: 2px 8px;")
        btn_all.clicked.connect(lambda: self.toggle_all_checks(container, True))
        header.addWidget(btn_all)
        
        layout.addLayout(header)

        # Список шагов с чекбоксами
        step_list = QListWidget()
        step_list.setStyleSheet("background-color: #252526; border: 1px solid #333; border-radius: 4px;")
        
        # Поле предпросмотра контента
        content_view = QTextBrowser()
        content_view.setStyleSheet("background-color: #1a1a1a; border: 1px solid #333; font-family: Consolas; font-size: 12px;")
        
        step_list.itemClicked.connect(lambda item: content_view.setPlainText(item.data(Qt.ItemDataRole.UserRole)))
        
        # Кнопки действий
        btn_row = QHBoxLayout()
        btn_copy = QPushButton("📋 Скопировать выбранное")
        btn_copy.clicked.connect(lambda: self.export_selected(container, to_file=False))
        
        btn_file = QPushButton("💾 В .txt файл")
        btn_file.clicked.connect(lambda: self.export_selected(container, to_file=True))
        
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_file)
        btn_row.addStretch()
        
        layout.addWidget(step_list, 1)
        layout.addWidget(content_view, 2)
        layout.addLayout(btn_row)
        
        # Сохраняем ссылки для доступа
        container.step_list = step_list
        container.content_view = content_view
        
        self.populate_steps(container, trace_data)

    def populate_steps(self, container, trace_data):
        container.step_list.clear()
        container.content_view.clear()
        for i, step in enumerate(trace_data, 1):
            item = QListWidgetItem(f"Шаг {i}: {step.get('title', 'Без названия')}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, step.get('content', ''))
            container.step_list.addItem(item)
        
        if trace_data:
            container.content_view.setPlainText(trace_data[0].get('content', ''))

    def load_archive_list(self):
        self.list_archive.clear()
        trace_file = os.path.join(self.mw.project_path, ".vibecoder", "agent_traces.json")
        if not os.path.exists(trace_file): return
        
        try:
            with open(trace_file, 'r', encoding='utf-8') as f:
                self.traces_db = json.load(f)
            
            for t in reversed(self.traces_db):
                dt = datetime.fromisoformat(t['timestamp']).strftime("%d.%m %H:%M")
                item = QListWidgetItem(f"[{dt}] {t['title']}")
                item.setData(Qt.ItemDataRole.UserRole, t['id'])
                self.list_archive.addItem(item)
        except: pass

    def on_archive_item_clicked(self, item):
        trace_id = item.data(Qt.ItemDataRole.UserRole)
        self.load_trace_from_archive(trace_id)

    def load_trace_from_archive(self, trace_id):
        trace_data = next((t for t in self.traces_db if t['id'] == trace_id), None)
        if trace_data:
            self.populate_steps(self.archive_detail_container, trace_data['steps'])

    def toggle_all_checks(self, container, state):
        for i in range(container.step_list.count()):
            container.step_list.item(i).setCheckState(Qt.CheckState.Checked if state else Qt.CheckState.Unchecked)

    def export_selected(self, container, to_file=False):
        selected_text = []
        for i in range(container.step_list.count()):
            item = container.step_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_text.append(f"=== {item.text().upper()} ===")
                selected_text.append(item.data(Qt.ItemDataRole.UserRole))
                selected_text.append("\n" + "="*50 + "\n")
        
        final_output = "\n".join(selected_text)
        if not final_output: return

        if to_file:
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить лог", os.path.expanduser("~/Desktop/inspector_export.txt"), "Text Files (*.txt)")
            if path:
                with open(path, 'w', encoding='utf-8') as f: f.write(final_output)
        else:
            QApplication.clipboard().setText(final_output)
            self.mw.log_system("✅ Выбранные шаги скопированы в буфер обмена.")