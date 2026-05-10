import os
import json
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QProgressBar, QCheckBox, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QPushButton, QMessageBox, QTabWidget, QWidget)
from PyQt6.QtCore import Qt, QSettings

class RAGAnalyticsDialog(QDialog):
    def __init__(self, parent=None, vector_db=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("🧠 Дашборд базы знаний (RAG) и Биллинг")
        self.resize(900, 650)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        self.db = vector_db
        self.settings = settings
        self.init_ui()

    def _get_logical_day(self):
        """Возвращает логические сутки (обновление в 10:00 утра)"""
        now = datetime.now()
        if now.hour < 10:
            return (now - timedelta(days=1)).strftime("%Y-%m-%d")
        return now.strftime("%Y-%m-%d")

    def _force_reset_quotas(self):
        self.settings.setValue("rag_logical_date", "")
        self.settings.setValue("rag_usage_dict", "{}")
        self.settings.setValue("rag_exhausted_keys", "[]")
        QMessageBox.information(self, "Сброс кэша", "Локальный кэш лимитов успешно сброшен!\n\nПожалуйста, переоткройте это окно для обновления данных.")
        self.accept()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # ==========================================
        # БЛОК А: ДИНАМИЧЕСКИЕ ЛИМИТЫ (АКТИВНЫЙ ПУЛ)
        # ==========================================
        header_limits_layout = QHBoxLayout()
        lbl_limits = QLabel("📊 Текущий расход API (Логические сутки Google)")
        lbl_limits.setStyleSheet("font-size: 14px; font-weight: bold; color: #569cd6;")
        header_limits_layout.addWidget(lbl_limits)
        
        btn_reset_cache = QPushButton("🔄 Сбросить кэш лимитов")
        btn_reset_cache.setStyleSheet("background-color: #333333; color: #d4d4d4; padding: 4px 10px; border-radius: 3px; font-size: 11px;")
        btn_reset_cache.setToolTip("Используйте, если график завис или показывает неверные данные после ошибок")
        btn_reset_cache.clicked.connect(self._force_reset_quotas)
        header_limits_layout.addStretch()
        header_limits_layout.addWidget(btn_reset_cache)
        
        layout.addLayout(header_limits_layout)

        api_settings = QSettings("VibeCoder", "API_Config")
        emb_keys_str = api_settings.value("gemini_embedding_key", "").strip()
        main_key_str = api_settings.value("gemini_api_key", "").strip()
        
        active_keys = []
        
        if emb_keys_str:
            try:
                keys_data = json.loads(emb_keys_str)
                if isinstance(keys_data, list):
                    for item in keys_data:
                        if item.get("enabled", True): 
                            k = item.get("key", "").strip()
                            if k:
                                active_keys.append({"key": k, "comment": item.get("comment", "")})
            except:
                for k in emb_keys_str.split(','):
                    if k.strip():
                        active_keys.append({"key": k.strip(), "comment": ""})
                        
        if not active_keys and main_key_str:
            active_keys.append({"key": main_key_str, "comment": "Основной ключ (Фоллбэк)"})
                        
        if not active_keys:
            lbl_no_keys = QLabel("⚠️ Активные ключи Gemini API не найдены. Включите их в настройках.")
            lbl_no_keys.setStyleSheet("color: #ff4444; font-weight: bold;")
            layout.addWidget(lbl_no_keys)
        else:
            logical_today = self._get_logical_day()
            
            # Используем новое имя переменной для жесткого сброса призраков прошлого
            if self.settings.value("rag_logical_date", "") != logical_today:
                self.settings.setValue("rag_logical_date", logical_today)
                self.settings.setValue("rag_usage_dict", "{}")
                self.settings.setValue("rag_exhausted_keys", "[]")

            usage_dict = json.loads(str(self.settings.value("rag_usage_dict", "{}")))
            exhausted_keys = json.loads(str(self.settings.value("rag_exhausted_keys", "[]")))
            max_requests = 1500

            for idx, item in enumerate(active_keys):
                key = item["key"]
                comment = item["comment"]
                masked_key = f"...{key[-4:]}" if len(key) > 4 else "***"
                usage = usage_dict.get(key, 0)
                is_exhausted = key in exhausted_keys
                
                comment_text = f" [{comment}]" if comment else ""
                lbl_key = QLabel(f"🔑 {idx + 1}. Ключ {masked_key}{comment_text}:")
                if comment == "Основной ключ (Фоллбэк)":
                    lbl_key.setStyleSheet("color: #e6a822; font-size: 12px; margin-top: 5px;")
                else:
                    lbl_key.setStyleSheet("color: #d4d4d4; font-size: 12px; margin-top: 5px;")
                layout.addWidget(lbl_key)
                
                progress = QProgressBar()
                progress.setMaximum(max_requests)
                progress.setValue(usage) # Теперь всегда показываем реальное значение
                
                if is_exhausted:
                    progress.setFormat(f" 🚨 ЛИМИТ ИСЧЕРПАН (Отправлено: {usage} из ~1500) ")
                    color = "#d32f2f"
                else:
                    progress.setFormat(f" Отправлено запросов: {usage} (Ограничение: ~{max_requests}/сутки) ")
                    color = "#31a24c"
                    if usage > 1000: color = "#e6a822"
                    if usage > 1400: color = "#d32f2f"
                    
                progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
                progress.setStyleSheet(f"""
                    QProgressBar {{ border: 1px solid #3c3c3c; border-radius: 4px; background-color: #252526; text-align: center; color: white; font-weight: bold; height: 18px; }}
                    QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}
                """)
                layout.addWidget(progress)
                
        lbl_hint = QLabel("ℹ️ Квоты Google сбрасываются в 10:00 (00:00 PT). Счетчик показывает только локальные запросы IDE.")
        lbl_hint.setStyleSheet("color: #888888; font-size: 11px; margin-top: 2px;")
        layout.addWidget(lbl_hint)
        layout.addSpacing(15)

        # ==========================================
        # БЛОК Б: ВКЛАДКИ (DB и Статистика)
        # ==========================================
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3c3c3c; background: #1e1e1e; }
            QTabBar::tab { background: #252526; color: #888888; padding: 8px 15px; border: 1px solid #3c3c3c; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #1e1e1e; color: #d4d4d4; font-weight: bold; border-top: 2px solid #0e639c; border-bottom: 1px solid #1e1e1e; }
        """)
        layout.addWidget(self.tabs)

        # --- Вкладка 1: Векторная база ---
        tab_db = QWidget()
        tab_db_layout = QVBoxLayout(tab_db)
        
        self.cb_auto = QCheckBox("Автоматически обновлять индекс измененных файлов при сохранении (Ctrl+S)")
        self.cb_auto.setStyleSheet("""
            QCheckBox { color: #d4d4d4; font-size: 13px; font-weight: bold; margin-bottom: 5px; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #888; border-radius: 3px; background-color: #252526; }
            QCheckBox::indicator:checked { background-color: #0e639c; border: 1px solid #0e639c; }
        """)
        self.cb_auto.setChecked(self.settings.value("auto_rag_update", True, type=bool))
        self.cb_auto.stateChanged.connect(lambda state: self.settings.setValue("auto_rag_update", bool(state)))
        tab_db_layout.addWidget(self.cb_auto)

        self.table_db = QTableWidget()
        self.table_db.setColumnCount(4)
        self.table_db.setHorizontalHeaderLabels(["Файл", "MD5 Хэш", "Векторов (Чанков)", "Дата индексации"])
        self.table_db.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_db.horizontalHeader().setStretchLastSection(True)
        self.table_db.verticalHeader().setVisible(False)
        self.table_db.setStyleSheet("""
            QTableWidget { background-color: #252526; color: #d4d4d4; gridline-color: #3c3c3c; border: 1px solid #3c3c3c; font-size: 13px; outline: none;}
            QHeaderView::section { background-color: #1e1e1e; color: #aaaaaa; padding: 6px; border: 1px solid #3c3c3c; font-weight: bold; }
            QTableWidget::item { padding: 4px; }
            QTableWidget::item:selected { background-color: #37373d; }
        """)
        tab_db_layout.addWidget(self.table_db)
        self.tabs.addTab(tab_db, "📂 Аудит Базы Данных")

        # --- Вкладка 2: Статистика Биллинга ---
        tab_stats = QWidget()
        tab_stats_layout = QVBoxLayout(tab_stats)
        
        lbl_stats_info = QLabel("История всех RAG-запросов. Помогает отслеживать нагрузку на ключи по дням.")
        lbl_stats_info.setStyleSheet("color: #aaaaaa; font-size: 12px; margin-bottom: 5px;")
        tab_stats_layout.addWidget(lbl_stats_info)
        
        self.table_stats = QTableWidget()
        self.table_stats.setColumnCount(3)
        self.table_stats.setHorizontalHeaderLabels(["Дата (Логические сутки)", "Всего запросов", "Детализация по ключам"])
        self.table_stats.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_stats.horizontalHeader().setStretchLastSection(True)
        self.table_stats.verticalHeader().setVisible(False)
        self.table_stats.setStyleSheet(self.table_db.styleSheet())
        self.table_stats.verticalHeader().setDefaultSectionSize(60) 
        tab_stats_layout.addWidget(self.table_stats)
        self.tabs.addTab(tab_stats, "📈 Статистика API (Биллинг)")

        self.populate_db_table()
        self.populate_stats_table()

        state = self.settings.value("rag_table_state")
        if state:
            self.table_db.horizontalHeader().restoreState(state)
        else:
            self.table_db.setColumnWidth(0, 350)
            self.table_db.setColumnWidth(1, 100)
            self.table_db.setColumnWidth(2, 130)
            
        self.table_stats.setColumnWidth(0, 150)
        self.table_stats.setColumnWidth(1, 120)

        # ==========================================
        # БЛОК В: КНОПКИ УПРАВЛЕНИЯ
        # ==========================================
        btn_layout = QHBoxLayout()

        self.btn_clear = QPushButton("🗑️ Очистить базу (Hard Reset)")
        self.btn_clear.setStyleSheet("""
            QPushButton { background-color: #512525; color: #ff4444; padding: 8px 15px; border: 1px solid #ff4444; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #d32f2f; color: white; }
        """)
        self.btn_clear.clicked.connect(self.on_clear_clicked)

        btn_close = QPushButton("Закрыть")
        btn_close.setStyleSheet("background-color: #333333; padding: 8px 20px; border-radius: 4px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.btn_clear)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def populate_db_table(self):
        if not self.db: return
        self.table_db.setSortingEnabled(False)
        stats = self.db.get_all_files_stats()
        self.table_db.setRowCount(len(stats))
        row = 0
        for path, info in sorted(stats.items()):
            item_path = QTableWidgetItem(f"📄 {path}")
            item_path.setFlags(item_path.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            item_hash = QTableWidgetItem(info["md5_hash"])
            item_hash.setFlags(item_hash.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_hash.setForeground(Qt.GlobalColor.darkGray)
            
            item_chunks = QTableWidgetItem()
            item_chunks.setData(Qt.ItemDataRole.DisplayRole, info["chunk_count"])
            item_chunks.setFlags(item_chunks.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_chunks.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            item_date = QTableWidgetItem(info["last_indexed"])
            item_date.setFlags(item_date.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            self.table_db.setItem(row, 0, item_path)
            self.table_db.setItem(row, 1, item_hash)
            self.table_db.setItem(row, 2, item_chunks)
            self.table_db.setItem(row, 3, item_date)
            row += 1
        self.table_db.setSortingEnabled(True)
        self.table_db.sortItems(3, Qt.SortOrder.DescendingOrder)

    def populate_stats_table(self):
        core_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(os.path.dirname(core_dir), "config", "VibeCoder")
        history_file = os.path.join(config_dir, "rag_usage_history.json")
        
        self.table_stats.setRowCount(0)
        
        if not os.path.exists(history_file):
            return
            
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                h_data = json.load(f)
        except:
            return
            
        sorted_dates = sorted(h_data.keys(), reverse=True)
        self.table_stats.setRowCount(len(sorted_dates))
        
        for row, date_str in enumerate(sorted_dates):
            day_info = h_data[date_str]
            
            item_date = QTableWidgetItem(f"📅 {date_str}")
            item_date.setFlags(item_date.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            if isinstance(day_info, int):
                item_total = QTableWidgetItem()
                item_total.setData(Qt.ItemDataRole.DisplayRole, day_info)
                item_total.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_details = QTableWidgetItem("Нет детализации (Старый формат)")
                item_details.setForeground(Qt.GlobalColor.darkGray)
            else:
                total = day_info.get("total", 0)
                keys_dict = day_info.get("keys", {})
                
                item_total = QTableWidgetItem()
                item_total.setData(Qt.ItemDataRole.DisplayRole, total)
                item_total.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if total > 1400: item_total.setForeground(Qt.GlobalColor.red)
                elif total > 1000: item_total.setForeground(Qt.GlobalColor.yellow)
                else: item_total.setForeground(Qt.GlobalColor.green)
                
                details_text = ""
                for k_name, k_usage in keys_dict.items():
                    details_text += f"🔑 {k_name}: {k_usage} запросов\n"
                details_text = details_text.strip()
                
                item_details = QTableWidgetItem(details_text)
            
            item_total.setFlags(item_total.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_details.setFlags(item_details.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            self.table_stats.setItem(row, 0, item_date)
            self.table_stats.setItem(row, 1, item_total)
            self.table_stats.setItem(row, 2, item_details)
            
        self.table_stats.resizeRowsToContents()

    def on_clear_clicked(self):
        if not self.db: return
        reply = QMessageBox.question(self, 'Подтверждение очистки',
            "Вы уверены, что хотите полностью ОЧИСТИТЬ векторную базу данных этого проекта?\n\nЭто удалит все проиндексированные фрагменты кода.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.db.clear_database()
            self.populate_db_table()
            QMessageBox.information(self, 'Очистка', 'База данных проекта успешно очищена.')

    def closeEvent(self, event):
        if self.settings:
            self.settings.setValue("rag_table_state", self.table_db.horizontalHeader().saveState())
        super().closeEvent(event)