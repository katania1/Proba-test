import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter, 
                             QVBoxLayout, QPushButton, QMessageBox, QDialog, 
                             QStatusBar, QTabWidget, QTextBrowser, QComboBox, QLabel)
from PyQt6.QtCore import Qt, QDir, QUrl, QSettings, QEvent, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence

from core.editor import DarkPythonEditor
from core.ai_controller import AIController
from core.code_applier import CodeApplier
from core.git_workflow import GitWorkflow
from core.file_ops import FileManager
from core.chat_logger import ChatLogger
from core.history_viewer import HistoryDialog

from core.custom_widgets import TagHighlighter, VibeTextEdit, VibeChatBrowser
from core.file_explorer import FileExplorerWidget
from core.time_machine import TimeMachineDialog
from core.git_manager import GitManager
from core.api_settings_dialog import APISettingsDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VibeCoder v1.18 — Ultimate MVC Edition (No Jumps)")
        
        self.settings = QSettings("VibeCoder", "Preferences")
        self.attached_files = set()
        self.last_full_prompt = ""
        self.current_git_dialog = None
        
        self.setStyleSheet("""
            QToolTip { background-color: #252526; color: #d4d4d4; border: 1px solid #569cd6; border-radius: 4px; padding: 5px; font-size: 13px; }
            QSplitter::handle { background-color: #3c3c3c; }
            QSplitter::handle:horizontal { width: 3px; }
            QSplitter::handle:vertical { height: 3px; }
            QSplitter::handle:hover { background-color: #0e639c; }
            QPushButton#FileToolBtn { background-color: transparent; border: none; font-size: 16px; padding: 4px; border-radius: 4px; }
            QPushButton#FileToolBtn:hover { background-color: #3c3c3c; }
            QInputDialog { background-color: #252526; color: #d4d4d4; }
            QLineEdit { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #3c3c3c; padding: 4px; }
            QTabWidget::pane { border: 1px solid #3c3c3c; background: #1e1e1e; }
            QTabBar::tab { background: #2d2d2d; color: #858585; padding: 8px 15px; border: 1px solid #3c3c3c; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #1e1e1e; color: #d4d4d4; border-top: 2px solid #0e639c; }
            QMenu { background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; }
            QMenu::item:selected { background-color: #0e639c; }
        """)
        
        screen = self.screen().availableGeometry()
        self.resize(min(1350, screen.width() - 50), min(900, screen.height() - 50))
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.addWidget(self.splitter)
        
        self.project_path = self.settings.value("last_project_path", QDir.currentPath())
        if not os.path.exists(self.project_path):
            self.project_path = QDir.currentPath()
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Индикатор вкладок
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(5, 0, 10, 0)
        
        lbl_browser = QLabel("Браузер: ")
        lbl_browser.setStyleSheet("color: #d4d4d4; font-weight: bold;")
        
        self.combo_tabs = QComboBox()
        # ИСПРАВЛЕНО: Стили для невидимого шрифта вкладок (QAbstractItemView)
        self.combo_tabs.setStyleSheet("""
            QComboBox { 
                background-color: #252526; 
                color: white; 
                border: 1px solid #3c3c3c; 
                padding: 2px 10px; 
                border-radius: 3px; 
                font-weight: normal; 
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1e1e1e;
                color: #d4d4d4;
                selection-background-color: #0e639c;
                selection-color: white;
                border: 1px solid #3c3c3c;
            }
        """)
        self.combo_tabs.setMinimumWidth(120)
        
        status_layout.addWidget(lbl_browser)
        status_layout.addWidget(self.combo_tabs)
        self.status_bar.addPermanentWidget(status_container)
        
        # ИСПРАВЛЕНО: Жесткая память выбранной вкладки (Anti-Jump)
        self.locked_tab_id = None
        self.combo_tabs.currentIndexChanged.connect(self.on_tab_manually_changed)
        
        self.tab_timer = QTimer(self)
        self.tab_timer.timeout.connect(self.update_tabs_ui)
        self.tab_timer.start(2000)
        
        self.tokens_sent = 0
        self.tokens_received = 0
        self.update_status_bar()
        
        self.file_manager = FileManager(self.project_path)
        self.chat_logger = ChatLogger(self.project_path)
        self.git_manager = GitManager(self.project_path)
        
        # --- ПАНЕЛЬ 1: Левое дерево ---
        self.file_explorer = FileExplorerWidget(self.project_path)
        self.file_explorer.file_opened.connect(self.open_file)
        self.file_explorer.log_message.connect(self.log_system)
        self.file_explorer.show_popup_msg.connect(self.show_popup)
        self.file_explorer.project_changed.connect(self.handle_project_changed)
        self.file_explorer.insert_tags_signal.connect(self.handle_tree_tags)
        self.file_explorer.open_time_machine_signal.connect(self.open_time_machine)
        self.splitter.addWidget(self.file_explorer)
        
        # --- ПАНЕЛЬ 2: Чат ---
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(5, 5, 5, 5)

        chat_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.chat_history = VibeChatBrowser()
        self.chat_history.setOpenLinks(False)
        self.chat_history.anchorClicked.connect(self.handle_chat_link)
        self.chat_history.setPlaceholderText("Логи системы и ответы ИИ...")
        
        chat_font = self.settings.value("chat_font_size", 12, type=int)
        self.chat_history.set_custom_font_size(chat_font)
        self.chat_history.zoom_changed.connect(lambda size: self.settings.setValue("chat_font_size", size))
        
        chat_splitter.addWidget(self.chat_history)

        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 5, 0, 0)
        
        self.prompt_input = VibeTextEdit()
        self.prompt_input.setPlaceholderText("Напишите задание...\n(Отправка: Ctrl+Enter, Перенос: Enter, Зум: Ctrl+Колесо мыши)")
        self.prompt_input.tag_action_signal.connect(self.handle_tag_action)
        
        self.prompt_input.project_path = self.project_path
        self.prompt_input.highlighter = TagHighlighter(self.prompt_input.document(), self.attached_files)
        
        input_font = self.settings.value("input_font_size", 12, type=int)
        self.prompt_input.set_custom_font_size(input_font)
        self.prompt_input.zoom_changed.connect(lambda size: self.settings.setValue("input_font_size", size))
        
        input_layout.addWidget(self.prompt_input)
        chat_splitter.addWidget(input_container)
        chat_splitter.setSizes([600, 200])
        chat_layout.addWidget(chat_splitter)
        self.splitter.addWidget(chat_widget)
        
        # --- ПАНЕЛЬ 3: Редактор кода + Кнопки ---
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(5, 5, 5, 5)
        
        self.editor_tabs = QTabWidget()
        self.editor = DarkPythonEditor()
        self.editor_tabs.addTab(self.editor, "Ничего не открыто")
        editor_layout.addWidget(self.editor_tabs)
        
        self.editor_zoom = self.settings.value("editor_zoom", 0, type=int)
        self.editor.zoomTo(self.editor_zoom)
        self.editor.installEventFilter(self)
        
        bottom_btn_layout = QHBoxLayout()
        bottom_btn_layout.setSpacing(5)
        
        self.btn_send = QPushButton("➤ Отправить")
        self.btn_send.setToolTip("Отправить ИИ (Горячая клавиша: Ctrl + Enter)")
        self.btn_send.setFixedHeight(35)
        self.btn_send.setStyleSheet("background-color: #b58900; color: #1e1e1e; font-weight: bold; border-radius: 4px;")
        
        self.btn_pause = QPushButton("■ Пауза")
        self.btn_pause.setToolTip("Пауза / Стоп")
        self.btn_pause.setCheckable(True)
        self.btn_pause.setFixedHeight(35)
        self.btn_pause.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_pause.clicked.connect(self.toggle_pause)
        
        self.btn_history = QPushButton("📜")
        self.btn_history.setToolTip("Умная история проекта")
        self.btn_history.setFixedHeight(35)
        self.btn_history.setStyleSheet("background-color: #333333; color: white; font-size: 16px; border-radius: 4px;")
        self.btn_history.clicked.connect(self.show_history)
        
        self.btn_relay = QPushButton("🔄")
        self.btn_relay.setToolTip("Сформировать ИИ-Эстафету (Транзитный пакет)")
        self.btn_relay.setFixedHeight(35)
        self.btn_relay.setStyleSheet("background-color: #005f73; color: white; font-size: 16px; border-radius: 4px;")
        
        self.btn_git = QPushButton("📦 Git")
        self.btn_git.setToolTip("Управление версиями (Git)")
        self.btn_git.setFixedHeight(35)
        self.btn_git.setStyleSheet("background-color: #4a148c; color: white; font-weight: bold; border-radius: 4px;")

        self.btn_api = QPushButton("⚙️ API")
        self.btn_api.setToolTip("Настройки API (Ключи и Провайдеры)")
        self.btn_api.setFixedHeight(35)
        self.btn_api.setStyleSheet("background-color: #333333; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_api.clicked.connect(self.open_api_settings)
        
        self.btn_reject_main = QPushButton("❌ Отклонить")
        self.btn_reject_main.setToolTip("Отклонить предложенный код")
        self.btn_reject_main.setFixedHeight(35)
        self.btn_reject_main.setStyleSheet("background-color: #512525; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_reject_main.setVisible(False)
        
        self.btn_approve = QPushButton("✅ Утвердить код")
        self.btn_approve.setToolTip("Открыть окно ревью (Diff)")
        self.btn_approve.setFixedHeight(35)
        self.btn_approve.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; border-radius: 4px;") 
        
        bottom_btn_layout.addWidget(self.btn_send, 2)
        bottom_btn_layout.addWidget(self.btn_pause, 2)
        bottom_btn_layout.addWidget(self.btn_history, 1)
        bottom_btn_layout.addWidget(self.btn_relay, 1)
        bottom_btn_layout.addWidget(self.btn_git, 2)
        bottom_btn_layout.addWidget(self.btn_api, 1)
        bottom_btn_layout.addWidget(self.btn_reject_main, 2)
        bottom_btn_layout.addWidget(self.btn_approve, 2)
        
        editor_layout.addLayout(bottom_btn_layout)
        self.splitter.addWidget(editor_widget)
        self.splitter.setSizes([220, 450, 630])
        
        self.current_file_path = None
        self.proposed_updates = [] 
        self.retry_count = 0        
        self.memory_old_code = None 

        # --- ИНИЦИАЛИЗАЦИЯ НОВЫХ МОДУЛЕЙ АРХИТЕКТУРЫ ---
        self.code_applier = CodeApplier(self)
        self.git_workflow = GitWorkflow(self)
        
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self.code_applier.manual_save)
        self.btn_approve.clicked.connect(self.code_applier.review_and_approve)
        self.btn_reject_main.clicked.connect(self.code_applier.reject_preview)
        
        self.btn_git.clicked.connect(self.git_workflow.open_git_dialog)
        
        self.ai_controller = AIController(self)
        self.ai_controller.start()
        
        self.btn_send.clicked.connect(self.ai_controller.send_task)
        self.prompt_input.send_signal.connect(self.ai_controller.send_task)
        self.btn_relay.clicked.connect(self.ai_controller.force_relay)
        # -----------------------------------------------

        self.update_git_status()

    # --- СТРОГАЯ БЛОКИРОВКА ВКЛАДКИ ---
    def on_tab_manually_changed(self, index):
        if index >= 0:
            text = self.combo_tabs.itemText(index)
            if "[" in text and "]" in text:
                self.locked_tab_id = text.split("[")[-1].split("]")[0]

    def get_current_target_id(self):
        return self.locked_tab_id
    # ----------------------------------

    # --- ПРОКСИ-МЕТОДЫ (Связки для других компонентов) ---
    def is_path_safe(self, file_path):
        return self.code_applier.is_path_safe(file_path)

    def get_file_content_safe(self, rel_path):
        return self.code_applier.get_file_content_safe(rel_path)

    def update_git_status(self):
        self.git_workflow.update_git_status()

    def open_git_dialog(self, prefill_msg=""):
        self.git_workflow.open_git_dialog(prefill_msg)
        
    def request_ai_commit_message(self, diff_text):
        self.ai_controller.request_ai_commit_message(diff_text)
    # -----------------------------------------------------

    def open_api_settings(self):
        dialog = APISettingsDialog(self)
        dialog.exec()

    def eventFilter(self, obj, event):
        if obj == self.editor and event.type() == QEvent.Type.Wheel:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0: self.editor_zoom = min(20, self.editor_zoom + 1)
                else: self.editor_zoom = max(-10, self.editor_zoom - 1)
                self.editor.zoomTo(self.editor_zoom)
                self.settings.setValue("editor_zoom", self.editor_zoom)
                return True 
        return super().eventFilter(obj, event)

    def handle_project_changed(self, new_path):
        self.project_path = new_path
        self.settings.setValue("last_project_path", new_path)
        self.file_manager = FileManager(new_path)
        self.chat_logger = ChatLogger(new_path)
        self.git_manager = GitManager(new_path)
        self.prompt_input.project_path = new_path
        self.update_git_status()

    def handle_tree_tags(self, files, is_attach):
        formatted_files = [f"@[{f}]" for f in files]
        text = " ".join(formatted_files) + " "
        self.prompt_input.insertPlainText(text)
        if is_attach:
            for f in files: self.attached_files.add(f)
        self.prompt_input.highlighter.rehighlight()
        self.prompt_input.setFocus()

    def open_file(self, path):
        if path.startswith("DELETED:"):
            del_path = path.replace("DELETED:", "")
            if self.current_file_path == del_path:
                self.editor.setText("")
                self.current_file_path = None
                self.editor_tabs.setTabText(0, "Ничего не открыто")
            return
        if self.proposed_updates:
            self.show_popup("Внимание", "Сначала утвердите или отклоните текущие изменения кода!")
            return
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                self.editor.setText(f.read())
            self.current_file_path = path
            self.editor_tabs.setTabText(0, f"📄 {os.path.basename(path)}")

    def open_time_machine(self, file_path):
        dialog = TimeMachineDialog(self, file_path, self.file_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.log_system(f"Файл {os.path.basename(file_path)} успешно восстановлен из бэкапа!", color="#d32f2f")
            if self.current_file_path == file_path:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.editor.setText(f.read())
            self.update_git_status()

    def handle_tag_action(self, filename, is_attach):
        if is_attach: self.attached_files.add(filename)
        else: self.attached_files.discard(filename)
        self.prompt_input.highlighter.rehighlight()

    def handle_chat_link(self, url: QUrl):
        if url.scheme() == "relay":
            entry = self.chat_logger.get_by_id(url.path())
            if entry and entry.get("hidden_data"):
                self.show_raw_text_dialog("Текст Эстафеты", entry["hidden_data"])
        elif url.scheme() == "view_prompt":
            self.show_raw_text_dialog("Сырой запрос к ИИ", self.last_full_prompt)

    def show_raw_text_dialog(self, title, text):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(800, 600)
        dlg.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout = QVBoxLayout(dlg)
        txt = QTextBrowser()
        txt.setStyleSheet("background-color: #252526; border: none; font-family: Consolas;")
        txt.setPlainText(text)
        layout.addWidget(txt)
        dlg.exec()

    def show_popup(self, title, message, is_error=False):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        if is_error: msg.setIcon(QMessageBox.Icon.Critical)
        else: msg.setIcon(QMessageBox.Icon.Information)
        msg.setStyleSheet("QMessageBox { background-color: #252526; color: #d4d4d4; } QLabel { color: #d4d4d4; font-size: 13px; } QPushButton { background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #1177bb; }")
        msg.exec()

    def update_status_bar(self):
        total = self.tokens_sent + self.tokens_received
        self.status_bar.showMessage(f"🟢 Текущая сессия: ~{total:,} токенов | ⬆️ Отправлено: ~{self.tokens_sent:,} | ⬇️ Получено: ~{self.tokens_received:,}")

    def toggle_pause(self):
        if self.btn_pause.isChecked():
            self.ai_controller.bridge.is_paused = True
            self.btn_pause.setText("▶ Продолжить")
            self.btn_pause.setStyleSheet("background-color: #31a24c; color: white; font-weight: bold; border-radius: 4px;")
            self.log_system("⏸ РАБОТА ПРИОСТАНОВЛЕНА", color="#ffaa00")
        else:
            self.ai_controller.bridge.is_paused = False
            self.btn_pause.setText("■ Пауза")
            self.btn_pause.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; border-radius: 4px;")
            self.log_system("▶ РАБОТА ВОЗОБНОВЛЕНА", color="#31a24c")

    def show_history(self):
        dlg = HistoryDialog(self, self.chat_logger)
        dlg.exec()

    def log_system(self, text, color="#0e639c"):
        self.chat_logger.log("SYSTEM", text)
        self.chat_history.append(f"<span style='color: {color};'><b>[СИСТЕМА] {text}</b></span>")
        self.scroll_chat()

    def scroll_chat(self):
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # --- ИСПРАВЛЕНИЕ: Жесткая привязка вкладок (Anti-Jump) ---
    def update_tabs_ui(self):
        if not hasattr(self, 'ai_controller') or not hasattr(self.ai_controller.bridge, 'get_active_tabs'):
            return
            
        tabs = self.ai_controller.bridge.get_active_tabs()
        
        new_items = ["🔴 Нет связи"] if not tabs else [f"🟢 {t}" for t in tabs]
        current_items = [self.combo_tabs.itemText(i) for i in range(self.combo_tabs.count())]
        
        if new_items == current_items:
            return 
            
        self.combo_tabs.blockSignals(True)
        self.combo_tabs.clear()
        
        self.combo_tabs.setEnabled(bool(tabs))
        self.combo_tabs.addItems(new_items)
            
        # Строго восстанавливаем заблокированный ID из памяти
        if self.locked_tab_id:
            for i in range(self.combo_tabs.count()):
                if f"[{self.locked_tab_id}]" in self.combo_tabs.itemText(i):
                    self.combo_tabs.setCurrentIndex(i)
                    break
        else:
            # Если блокировки еще нет, берем первую вкладку как дефолт
            if self.combo_tabs.count() > 0:
                text = self.combo_tabs.itemText(0)
                if "[" in text and "]" in text:
                    self.locked_tab_id = text.split("[")[-1].split("]")[0]
                    
        self.combo_tabs.blockSignals(False)