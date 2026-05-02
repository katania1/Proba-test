import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter, 
                             QVBoxLayout, QDialog, QTabWidget, QTextBrowser, 
                             QLabel, QFileDialog, QPushButton, QMessageBox)
from PyQt6.QtCore import Qt, QDir, QUrl, QSettings, QEvent
from PyQt6.QtGui import QShortcut, QKeySequence

# Импорты ядра
from core.editor import DarkPythonEditor
from core.ai_controller import AIController
from core.code_applier import CodeApplier
from core.git_workflow import GitWorkflow
from core.file_ops import FileManager
from core.chat_logger import ChatLogger
from core.history_viewer import HistoryDialog

# Импорты UI-модулей
from core.custom_widgets import TagHighlighter, VibeTextEdit, VibeChatBrowser, AttachmentPanel
from core.file_explorer import FileExplorerWidget
from core.time_machine import TimeMachineDialog
from core.git_manager import GitManager
from core.api_settings_dialog import APISettingsDialog
from core.terminal import TerminalWidget

# НОВЫЕ ИМПОРТЫ НАШЕЙ ОПТИМИЗАЦИИ
from core.rag_controller import RagController
from core.status_bar import VibeStatusBar
from core.bottom_panel import BottomPanelWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VibeCoder v1.19 — Pro IDE Edition")
        
        self.settings = QSettings("VibeCoder", "Preferences")
        self.api_settings = QSettings("VibeCoder", "API_Config")
        
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
        self.resize(min(1450, screen.width() - 50), min(950, screen.height() - 50))
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.addWidget(self.splitter)
        
        self.project_path = self.settings.value("last_project_path", QDir.currentPath())
        if not os.path.exists(self.project_path):
            self.project_path = QDir.currentPath()
        
        # --- СТАТУС-БАР ---
        self.status_bar = VibeStatusBar(self)
        self.setStatusBar(self.status_bar)
        
        self.tokens_sent = 0
        self.tokens_received = 0
        self.update_status_bar()
        
        self.file_manager = FileManager(self.project_path)
        self.chat_logger = ChatLogger(self.project_path)
        self.git_manager = GitManager(self.project_path)
        
        # --- ЛЕВАЯ ПАНЕЛЬ ---
        self.file_explorer = FileExplorerWidget(self.project_path)
        self.file_explorer.file_opened.connect(self.open_file)
        self.file_explorer.log_message.connect(self.log_system)
        self.file_explorer.show_popup_msg.connect(self.show_popup)
        self.file_explorer.project_changed.connect(self.handle_project_changed)
        self.file_explorer.insert_tags_signal.connect(self.handle_tree_tags)
        self.file_explorer.open_time_machine_signal.connect(self.open_time_machine)
        self.splitter.addWidget(self.file_explorer)
        
        # --- ЦЕНТРАЛЬНАЯ ПАНЕЛЬ: Чат ---
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(5, 5, 5, 5)

        chat_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.chat_history = VibeChatBrowser()
        self.chat_history.setOpenLinks(False)
        self.chat_history.anchorClicked.connect(self.handle_chat_link)
        self.chat_history.setPlaceholderText("Логи системы и ответы ИИ...")
        self.chat_history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_history.customContextMenuRequested.connect(self.show_chat_context_menu)
        
        chat_font = self.settings.value("chat_font_size", 12, type=int)
        self.chat_history.set_custom_font_size(chat_font)
        self.chat_history.zoom_changed.connect(lambda size: self.settings.setValue("chat_font_size", size))
        
        chat_splitter.addWidget(self.chat_history)

        # --- ОБНОВЛЕННЫЙ БЛОК ВВОДА С КНОПКАМИ ---
        input_container = QWidget()
        input_container.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px;")
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(2, 2, 2, 2)
        input_layout.setSpacing(2)
        
        self.prompt_input = VibeTextEdit()
        self.prompt_input.setPlaceholderText("Напишите задание (Отправка: Ctrl+Enter)...")
        self.prompt_input.setStyleSheet("background-color: transparent; border: none; color: #d4d4d4;")
        self.prompt_input.tag_action_signal.connect(self.handle_tag_action)
        self.prompt_input.project_path = self.project_path
        self.prompt_input.highlighter = TagHighlighter(self.prompt_input.document(), self.attached_files)
        
        input_font = self.settings.value("input_font_size", 12, type=int)
        self.prompt_input.set_custom_font_size(input_font)
        self.prompt_input.zoom_changed.connect(lambda size: self.settings.setValue("input_font_size", size))
        
        self.attachment_panel = AttachmentPanel()
        self.prompt_input.media_attached_signal.connect(self.attachment_panel.add_attachment)
        
        input_layout.addWidget(self.prompt_input)
        input_layout.addWidget(self.attachment_panel) 

        # -- БЛОК КНОПОК ДЕЙСТВИЙ (ЦЕЛЕВЫЕ КНОПКИ ВНИЗУ ПОЛЯ ВВОДА) --
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(5, 0, 5, 5)
        
        # ДОБАВЛЯЕМ ПРУЖИНУ СЛЕВА! Теперь кнопки прилипнут к правому краю
        action_layout.addStretch() 
        
        btn_action_style = "color: white; font-weight: bold; border-radius: 3px; padding: 2px 10px; font-size: 11px; margin-left: 5px;"

        self.btn_send = QPushButton("➤ Отправить")
        self.btn_send.setFixedHeight(24)
        self.btn_send.setStyleSheet(f"background-color: #b58900; color: #1e1e1e; {btn_action_style.replace('color: white;', '')}")
        
        self.btn_pause = QPushButton("■ Пауза")
        self.btn_pause.setCheckable(True)
        self.btn_pause.setFixedHeight(24)
        self.btn_pause.setStyleSheet(f"background-color: #d32f2f; {btn_action_style}")
        
        self.btn_approve = QPushButton("✅ Утвердить код")
        self.btn_approve.setFixedHeight(24)
        self.btn_approve.setStyleSheet(f"background-color: #2e7d32; {btn_action_style}")
        
        self.btn_reject_main = QPushButton("❌ Отклонить")
        self.btn_reject_main.setFixedHeight(24)
        self.btn_reject_main.setStyleSheet(f"background-color: #512525; {btn_action_style}")
        self.btn_reject_main.setVisible(False)
        
        action_layout.addWidget(self.btn_send)
        action_layout.addWidget(self.btn_pause)
        action_layout.addWidget(self.btn_approve)
        action_layout.addWidget(self.btn_reject_main)

        input_layout.addLayout(action_layout)
        # ----------------------------------------------------
        
        chat_splitter.addWidget(input_container)
        chat_splitter.setSizes([600, 200])
        chat_layout.addWidget(chat_splitter)
        self.splitter.addWidget(chat_widget)
        
        # --- ПРАВАЯ ПАНЕЛЬ: Редактор и Терминал ---
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(5, 5, 5, 5)
        
        self.editor_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.editor_tabs = QTabWidget()
        self.editor = DarkPythonEditor()
        self.editor_tabs.addTab(self.editor, "Ничего не открыто")
        self.editor_splitter.addWidget(self.editor_tabs)
        
        self.editor_zoom = self.settings.value("editor_zoom", 0, type=int)
        self.editor.zoomTo(self.editor_zoom)
        self.editor.installEventFilter(self)
        
        self.terminal = TerminalWidget(self.project_path)
        self.terminal.setVisible(False) 
        self.editor_splitter.addWidget(self.terminal)
        
        self.editor_splitter.setSizes([700, 300]) 
        editor_layout.addWidget(self.editor_splitter)
        
        # --- ВОЗВРАЩАЕМ ПАНЕЛЬ ПОД РЕДАКТОР ---
        self.bottom_panel = BottomPanelWidget()
        editor_layout.addWidget(self.bottom_panel)

        self.splitter.addWidget(editor_widget)
        self.splitter.setSizes([220, 450, 630])

        # --- СВЯЗЫВАНИЕ АЛИАСОВ ---
        self.btn_attach = self.bottom_panel.btn_attach
        self.btn_history = self.bottom_panel.btn_history
        self.btn_relay = self.bottom_panel.btn_relay
        self.btn_api = self.bottom_panel.btn_api
        self.btn_git = self.bottom_panel.btn_git
        self.btn_rag = self.bottom_panel.btn_rag
        self.btn_terminal = self.status_bar.btn_terminal
        
        # --- RAG КОНТРОЛЛЕР ---
        self.rag_controller = RagController(self)

        self.current_file_path = None
        self.proposed_updates = [] 
        self.retry_count = 0        
        self.memory_old_code = None 

        self.code_applier = CodeApplier(self)
        self.git_workflow = GitWorkflow(self)
        
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self.code_applier.manual_save)
        
        self.shortcut_terminal = QShortcut(QKeySequence("Ctrl+`"), self)
        self.shortcut_terminal.activated.connect(self.btn_terminal.click)
        
        self.btn_approve.clicked.connect(self.code_applier.review_and_approve)
        self.btn_reject_main.clicked.connect(self.code_applier.reject_preview)
        self.btn_git.clicked.connect(self.git_workflow.open_git_dialog)
        
        # --- ПОДКЛЮЧЕНИЕ СИГНАЛОВ КНОПОК ---
        self.btn_attach.clicked.connect(self.open_attachment_dialog)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_history.clicked.connect(self.show_history)
        self.btn_api.clicked.connect(self.open_api_settings)
        self.btn_terminal.clicked.connect(self.toggle_terminal)
        self.btn_rag.clicked.connect(self.rag_controller.start_indexing)
        self.btn_rag.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_rag.customContextMenuRequested.connect(self.rag_controller.show_analytics)

        self.ai_controller = AIController(self)
        self.ai_controller.start()
        
        self.btn_send.clicked.connect(self.ai_controller.send_task)
        self.prompt_input.send_signal.connect(self.ai_controller.send_task)
        self.btn_relay.clicked.connect(self.ai_controller.force_relay)

        self._check_project_environment()
        self._load_recent_chat_history()


    # ==========================================
    # ПРОСТЫЕ МЕТОДЫ (ОСТАВЛЕНЫ В MAIN_WINDOW)
    # ==========================================
    def get_selected_engine_data(self):
        return self.status_bar.get_selected_engine_data()
        
    def get_current_target_id(self):
        return self.status_bar.get_current_target_id()

    def show_chat_context_menu(self, pos):
        menu = self.chat_history.createStandardContextMenu()
        menu.addSeparator()
        action_clear = menu.addAction("🗑️ Очистить окно чата")
        action = menu.exec(self.chat_history.viewport().mapToGlobal(pos))
        if action == action_clear:
            self.chat_history.clear()
            self.log_system("Окно чата очищено (история сохранена в базе данных).")

    def open_api_settings(self):
        dialog = APISettingsDialog(self)
        if dialog.exec():
            self.status_bar.refresh_engine_list()

    def open_attachment_dialog(self):
        from PyQt6.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите картинки", self.project_path, "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)"
        )
        if files:
            for f in files: self.attachment_panel.add_attachment(os.path.normpath(f))

    def toggle_terminal(self):
        if self.btn_terminal.isChecked():
            self.terminal.setVisible(True)
            self.terminal.input_line.setFocus()
        else:
            self.terminal.setVisible(False)

    def is_path_safe(self, file_path):
        return self.code_applier.is_path_safe(file_path)

    def get_file_content_safe(self, rel_path):
        return self.code_applier.get_file_content_safe(rel_path)

    def update_git_status(self):
        self.git_workflow.update_git_status()

    def request_ai_commit_message(self, diff_text):
        self.ai_controller.request_ai_commit_message(diff_text)

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

    def trigger_silent_rag_update(self):
        self.rag_controller.trigger_silent_update()

    def handle_project_changed(self, new_path):
        self.project_path = new_path
        self.settings.setValue("last_project_path", new_path)
        
        self.file_manager = FileManager(new_path)
        self.chat_logger = ChatLogger(new_path)
        self.git_manager = GitManager(new_path)
        self.prompt_input.project_path = new_path
        self.terminal.update_project_path(new_path)
        self.rag_controller.setup_watcher()
        
        self.current_file_path = None
        self.editor.setText("")
        self.editor_tabs.setTabText(0, "Ничего не открыто")
        
        self.memory_old_code = None
        self.proposed_updates = []
        self.btn_reject_main.setVisible(False)
        self.btn_approve.setText("✅ Утвердить код")
        
        self.attached_files.clear()
        self.prompt_input.highlighter.rehighlight()
        self.attachment_panel.clear()
        
        self.chat_history.clear()
        self.log_system(f"Проект успешно загружен: {os.path.basename(new_path)}")
        
        self._check_project_environment()
        self._load_recent_chat_history()

    def _check_project_environment(self):
        self.update_git_status()
        if self.project_path == QDir.currentPath() or len(self.project_path) <= 3: return
            
        if not self.git_manager.is_repo():
            reply = self.show_question("Система контроля версий", "В этом проекте нет Git-репозитория.\nИнициализировать его прямо сейчас?")
            if reply == QMessageBox.StandardButton.Yes:
                success, msg = self.git_manager.init_repo()
                if success:
                    self.log_system("Git репозиторий инициализирован!", color="#31a24c")
                    self.update_git_status()
                else: self.show_popup("Ошибка", f"Не удалось инициализировать Git:\n{msg}", is_error=True)
                    
        venv_path = os.path.join(self.project_path, 'venv')
        req_path = os.path.join(self.project_path, 'requirements.txt')
        if not os.path.exists(venv_path) and os.path.exists(req_path):
            reply = self.show_question("Восстановление среды", "Виртуальное окружение (venv) не найдено, но есть requirements.txt.\nВосстановить среду?")
            if reply == QMessageBox.StandardButton.Yes:
                if not self.btn_terminal.isChecked(): self.btn_terminal.click() 
                self.log_system("Запуск скрипта восстановления среды (Disaster Recovery)...", color="#e6a822")
                if os.name == 'nt':
                    self.terminal.execute_cmd("python -m venv venv")
                    self.terminal.execute_cmd(f'"{os.path.join("venv", "Scripts", "activate.bat")}"')
                else:
                    self.terminal.execute_cmd("python3 -m venv venv")
                    self.terminal.execute_cmd("source venv/bin/activate")
                self.terminal.execute_cmd("pip install -r requirements.txt")

    def _load_recent_chat_history(self):
        logs = self.chat_logger.get_all()
        if logs:
            self.chat_history.append("<br><span style='color: #888888;'><i>--- История предыдущей сессии (последние 20 сообщений) ---</i></span>")
            for log in logs[-20:]:
                role = log.get("role", "")
                content = log.get("content", "")
                safe_content = content.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
                
                if role == "USER": self.chat_history.append(f"<br><span style='color: #569cd6;'><b>ВЫ:</b> {safe_content}</span>")
                elif role == "AI": self.chat_history.append(f"<span style='color: #31a24c;'><b>[МЫСЛИ ИИ]:</b> {safe_content}</span>")
                elif role == "SYSTEM": self.chat_history.append(f"<span style='color: #0e639c;'><b>[СИСТЕМА] {safe_content}</b></span>")
                    
            self.chat_history.append("<br><span style='color: #888888;'><i>--- Текущая сессия ---</i></span><br>")
            self.scroll_chat()

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
        from PyQt6.QtWidgets import QVBoxLayout
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

    def show_question(self, title, message):
        from PyQt6.QtWidgets import QLabel
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(400, 150)
        dlg.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout = QVBoxLayout(dlg)
        
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 13px; margin: 10px;")
        layout.addWidget(lbl)
        
        btn_layout = QHBoxLayout()
        btn_yes = QPushButton("Да")
        btn_yes.setStyleSheet("background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold;")
        btn_yes.clicked.connect(lambda: dlg.done(QMessageBox.StandardButton.Yes))
        
        btn_no = QPushButton("Нет")
        btn_no.setStyleSheet("background-color: #333333; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold;")
        btn_no.clicked.connect(lambda: dlg.done(QMessageBox.StandardButton.No))
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_yes)
        btn_layout.addWidget(btn_no)
        layout.addLayout(btn_layout)
        return dlg.exec()

    def update_status_bar(self):
        total = self.tokens_sent + self.tokens_received
        self.status_bar.showMessage(f"🟢 Текущая сессия: ~{total:,} токенов | ⬆️ Отправлено: ~{self.tokens_sent:,} | ⬇️ Получено: ~{self.tokens_received:,}")

    def toggle_pause(self):
        if self.btn_pause.isChecked():
            self.ai_controller.bridge.is_paused = True
            self.btn_pause.setText("▶ Продолжить")
            self.btn_pause.setStyleSheet("background-color: #31a24c; color: white; font-weight: bold; border-radius: 3px; padding: 2px 10px; font-size: 11px; margin-left: 5px;")
            self.log_system("⏸ РАБОТА ПРИОСТАНОВЛЕНА", color="#ffaa00")
        else:
            self.ai_controller.bridge.is_paused = False
            self.btn_pause.setText("■ Пауза")
            self.btn_pause.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; border-radius: 3px; padding: 2px 10px; font-size: 11px; margin-left: 5px;")
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