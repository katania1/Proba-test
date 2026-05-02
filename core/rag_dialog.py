from datetime import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QProgressBar, QCheckBox, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QPushButton)
from PyQt6.QtCore import Qt

class RAGAnalyticsDialog(QDialog):
    def __init__(self, parent=None, vector_db=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("🧠 Управление базой знаний проекта (RAG)")
        self.resize(850, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        self.db = vector_db
        self.settings = settings
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # --- БЛОК А: ЛИМИТЫ ---
        lbl_limits = QLabel("📊 Лимиты Gemini API (Сегодня)")
        lbl_limits.setStyleSheet("font-size: 14px; font-weight: bold; color: #569cd6;")
        layout.addWidget(lbl_limits)

        # Читаем счетчик за сегодня
        today = datetime.now().strftime("%Y-%m-%d")
        saved_date = self.settings.value("rag_usage_date", "")
        if saved_date != today:
            self.settings.setValue("rag_usage_today", 0)
            self.settings.setValue("rag_usage_date", today)
            usage_today = 0
        else:
            usage_today = self.settings.value("rag_usage_today", 0, type=int)

        max_requests = 1500
        
        self.progress = QProgressBar()
        self.progress.setMaximum(max_requests)
        self.progress.setValue(usage_today)
        self.progress.setFormat(f" {usage_today} / {max_requests} запросов ")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Меняем цвет в зависимости от расхода
        color = "#31a24c" # Зеленый
        if usage_today > 1000: color = "#e6a822" # Желтый
        if usage_today > 1400: color = "#d32f2f" # Красный
        
        self.progress.setStyleSheet(f"""
            QProgressBar {{ border: 1px solid #3c3c3c; border-radius: 4px; background-color: #252526; text-align: center; color: white; font-weight: bold; }}
            QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}
        """)
        layout.addWidget(self.progress)
        layout.addSpacing(15)

        # --- БЛОК Б: АВТОМАТИЗАЦИЯ ---
        self.cb_auto = QCheckBox("Автоматически обновлять индекс измененных файлов при сохранении (Ctrl+S / Утверждение кода)")
        self.cb_auto.setStyleSheet("""
            QCheckBox { color: #d4d4d4; font-size: 13px; font-weight: bold; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #888; border-radius: 3px; background-color: #252526; }
            QCheckBox::indicator:checked { background-color: #0e639c; border: 1px solid #0e639c; }
        """)
        # ИСПРАВЛЕНИЕ: Теперь включено по умолчанию!
        self.cb_auto.setChecked(self.settings.value("auto_rag_update", True, type=bool))
        self.cb_auto.stateChanged.connect(lambda state: self.settings.setValue("auto_rag_update", bool(state)))
        layout.addWidget(self.cb_auto)
        layout.addSpacing(15)

        # --- БЛОК В: АУДИТ ФАЙЛОВ ---
        lbl_audit = QLabel("📂 Содержимое векторной базы данных")
        lbl_audit.setStyleSheet("font-size: 14px; font-weight: bold; color: #e6a822;")
        layout.addWidget(lbl_audit)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Файл", "MD5 Хэш", "Векторов (Чанков)", "Дата индексации"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget { background-color: #252526; color: #d4d4d4; gridline-color: #3c3c3c; border: 1px solid #3c3c3c; font-size: 13px; }
            QHeaderView::section { background-color: #1e1e1e; color: #aaaaaa; padding: 6px; border: 1px solid #3c3c3c; font-weight: bold; }
            QTableWidget::item { padding: 4px; }
        """)
        layout.addWidget(self.table)

        self.populate_table()

        btn_close = QPushButton("Закрыть")
        btn_close.setStyleSheet("background-color: #333333; padding: 8px 20px; border-radius: 4px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def populate_table(self):
        if not self.db: return
        stats = self.db.get_all_files_stats()
        self.table.setRowCount(len(stats))
        
        row = 0
        for path, info in sorted(stats.items()):
            item_path = QTableWidgetItem(f"📄 {path}")
            item_path.setFlags(item_path.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            item_hash = QTableWidgetItem(info["md5_hash"])
            item_hash.setFlags(item_hash.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_hash.setForeground(Qt.GlobalColor.darkGray)
            
            item_chunks = QTableWidgetItem(str(info["chunk_count"]))
            item_chunks.setFlags(item_chunks.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_chunks.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            item_date = QTableWidgetItem(info["last_indexed"])
            item_date.setFlags(item_date.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            self.table.setItem(row, 0, item_path)
            self.table.setItem(row, 1, item_hash)
            self.table.setItem(row, 2, item_chunks)
            self.table.setItem(row, 3, item_date)
            row += 1