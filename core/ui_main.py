import os
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter, 
                             QVBoxLayout, QDialog, QTabWidget, QTextBrowser, 
                             QLabel, QFileDialog, QPushButton, QMessageBox, QSizePolicy, QApplication)
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
from core.inspector_dialog import InspectorDialog

# --- НАШИ НОВЫЕ МЕНЕДЖЕРЫ ---
from core.vibe_drag_button import VibeDragButton
from core.editor_manager import EditorManager
from core.chat_handler import ChatHandler

# Импорты UI-модулей
from core.custom_widgets import TagHighlighter, VibeTextEdit, VibeChatBrowser, AttachmentPanel
from core.file_explorer import FileExplorerWidget
from core.git_manager import GitManager
from core.api_settings_dialog import APISettingsDialog
from core.terminal import TerminalWidget
from core.rag_controller import RagController
from core.status_bar import VibeStatusBar
from core.bottom_panel import BottomPanelWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VibeCoder v1.28 — Pro IDE Edition")
        
        # Включение отображения подсказок Tooltips без обязательного фокуса на окне
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        
        self.settings = QSettings("VibeCoder", "Preferences")
        self.api_settings = QSettings("VibeCoder", "API_Config")
        
        self.attached_files = set()
        self.last_full_prompt = ""
        self.current_git_dialog = None
        self.current_file_path = None
        self.proposed_updates = [] 
        
        # --- ИНИЦИАЛИЗАЦИЯ МЕНЕДЖЕРОВ (ФАСАД) ---
        self.editor_manager = EditorManager(self)
        self.chat_handler = ChatHandler(self)
        
        self.setStyleSheet("""
            QToolTip { background-color: #252526; color: #d4d4d4; border: 1px solid #569cd6; border-radius: 4px; padding: 5px; font-size: 13px; }
            QSplitter::handle { background-color: #3c3c3c; }
            QSplitter::handle:horizontal { width: 3px; }
            QSplitter::handle:vertical { height: 3px; }
            QSplitter::handle:hover { background-color: #0e639c; }
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
        
        self.status_bar = VibeStatusBar(self)
        self.setStatusBar(self.status_bar)
        
        self.tokens_sent = 0
        self.tokens_received = 0
        self.update_status_bar()
        
        self.file_manager = FileManager(self.project_path)
        self.chat_logger = ChatLogger(self.project_path)
        self.git_manager = GitManager(self.project_path)
        
        # --- ФАЙЛОВЫЙ ПРОВОДНИК ---
        self.file_explorer = FileExplorerWidget(self.project_path)
        self.file_explorer.file_opened.connect(self.editor_manager.open_file)
        self.file_explorer.log_message.connect(self.chat_handler.log_system)
        self.file_explorer.show_popup_msg.connect(self.show_popup)
        self.file_explorer.project_changed.connect(self.handle_project_changed)
        self.file_explorer.insert_tags_signal.connect(self.handle_tree_tags)
        self.file_explorer.open_time_machine_signal.connect(self.editor_manager.open_time_machine)
        self.splitter.addWidget(self.file_explorer)
        
        # --- ЧАТ ---
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(5, 5, 5, 5)

        chat_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.chat_history = VibeChatBrowser()
        self.chat_history.setOpenLinks(False)
        self.chat_history.anchorClicked.connect(self.chat_handler.handle_chat_link)
        self.chat_history.setPlaceholderText("Логи системы и ответы ИИ...")
        self.chat_history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_history.customContextMenuRequested.connect(self.chat_handler.show_chat_context_menu)
        
        # Глобальный сброс отступов для абзацев и дивов (Фикс пустых строк)
        self.chat_history.document().setDefaultStyleSheet("p, div, li { margin-top: 2px; margin-bottom: 2px; }")
        
        chat_font = self.settings.value("chat_font_size", 12, type=int)
        self.chat_history.set_custom_font_size(chat_font)
        self.chat_history.zoom_changed.connect(lambda size: self.settings.setValue("chat_font_size", size))
        chat_splitter.addWidget(self.chat_history)

        # --- ПОЛЕ ВВОДА ---
        input_container = QWidget()
        input_container.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px;")
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(2, 2, 2, 2)
        
        self.prompt_input = VibeTextEdit()
        self.prompt_input.setPlaceholderText("Напишите задание (Enter - Спросить, Ctrl+Enter - Кодить)...")
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

        # --- КНОПКИ ДЕЙСТВИЙ (Новый защищенный контейнер) ---
        action_container = QWidget()
        action_container.setMinimumWidth(100)  # Разрешаем сплиттеру сжимать панель
        action_layout = QHBoxLayout(action_container)
        action_layout.setContentsMargins(5, 0, 5, 5)
        
        # Уменьшен внутренний отступ кнопок (padding) до 6px
        def get_btn_style(bg, hover, pressed, color="white", border="none"):
            return f"""
                QPushButton {{ background-color: {bg}; color: {color}; border: {border}; font-weight: bold; border-radius: 3px; padding: 4px 6px; font-size: 11px; margin-left: 5px; }}
                QPushButton:hover {{ background-color: {hover}; }}
                QPushButton:pressed {{ background-color: {pressed}; }}
            """

        self.btn_inspector = QPushButton("🐞")
        self.btn_inspector.setFixedHeight(26)
        self.btn_inspector.setFixedWidth(32)
        self.btn_inspector.setStyleSheet(get_btn_style("#005f73", "#007891", "#00404d"))
        self.btn_inspector.setToolTip("Инспектор логов и трассировки")
        self.btn_inspector.clicked.connect(self.open_inspector)

        self.btn_approve = QPushButton("✅ Утвердить")
        self.btn_approve.setFixedHeight(26)
        self.btn_approve.setStyleSheet(get_btn_style("#2e7d32", "#388e3c", "#1b5e20"))
        self.btn_approve.setToolTip("Применить предложенные изменения (ревью кода)")
        
        self.btn_reject_main = QPushButton("❌ Отклонить")
        self.btn_reject_main.setFixedHeight(26)
        self.btn_reject_main.setStyleSheet(get_btn_style("#512525", "#6b2f2f", "#3a1919"))
        self.btn_reject_main.setToolTip("Отклонить изменения файлов и отменить патч")
        self.btn_reject_main.setVisible(False)

        # Компактная кнопка ручного перехвата по схеме кнопки инспектора
        self.btn_force_fetch = QPushButton("⏬")
        self.btn_force_fetch.setFixedWidth(32)
        self.btn_force_fetch.setFixedHeight(26)
        self.btn_force_fetch.setStyleSheet(get_btn_style("#4527a0", "#512da8", "#311b92"))
        self.btn_force_fetch.setToolTip("Принудительно считать текущий ответ от ИИ в браузере")
        self.btn_force_fetch.clicked.connect(self.force_fetch_answer)

        self.btn_pause = QPushButton('⏸ Пауза')
        self.btn_pause.setCheckable(True)
        self.btn_pause.setFixedHeight(26)
        self.btn_pause.setStyleSheet('''
            QPushButton { background-color: #333333; color: #d4d4d4; border: 1px solid #555555; font-weight: bold; border-radius: 3px; padding: 4px 6px; font-size: 11px; margin-left: 5px; }
            QPushButton:hover { background-color: #444444; }
            QPushButton:checked { background-color: #d32f2f; color: white; border: none; }
        ''')
        self.btn_pause.setToolTip("Приостановить связь с браузером и сбросить очередь задач")

        self.btn_chat = QPushButton("💬 Спросить")
        self.btn_chat.setFixedHeight(26)
        self.btn_chat.setStyleSheet(get_btn_style("transparent", "rgba(86, 156, 214, 0.1)", "rgba(86, 156, 214, 0.25)", color="#569cd6", border="1px solid #569cd6"))
        self.btn_chat.setToolTip("Легкий режим чата без RAG и JSON-парсинга")

        self.btn_code = VibeDragButton("⚡ Кодить", self)
        self.btn_code.setFixedHeight(26)
        self.btn_code.setStyleSheet(get_btn_style("#0e639c", "#1177bb", "#094771"))
        self.btn_code.setToolTip("Тяжелый режим: отправка контекста (RAG) и применение кода (Smart Diff)")

        action_layout.addWidget(self.btn_inspector)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_approve)
        action_layout.addWidget(self.btn_reject_main)
        action_layout.addWidget(self.btn_force_fetch)
        action_layout.addWidget(self.btn_pause)
        action_layout.addWidget(self.btn_chat)
        action_layout.addWidget(self.btn_code)

        input_layout.addWidget(action_container)
        chat_splitter.addWidget(input_container)
        chat_splitter.setSizes([600, 200])
        chat_layout.addWidget(chat_splitter)
        self.splitter.addWidget(chat_widget)
        
        # --- РЕДАКТОР КОДА ---
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(5, 5, 5, 5)
        
        self.editor_splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.setMovable(True)
        self.editor_tabs.tabCloseRequested.connect(self.editor_manager.close_tab)
        
        self.corner_widget = QWidget()
        self.corner_layout = QHBoxLayout(self.corner_widget)
        self.corner_layout.setContentsMargins(0, 0, 5, 0)
        
        self.btn_nav_back = QPushButton("◀")
        self.btn_nav_forward = QPushButton("▶")
        self.btn_tab_search = QPushButton("🔍")
        self.btn_tab_save = QPushButton("💾")
        
        for btn in [self.btn_nav_back, self.btn_nav_forward, self.btn_tab_search, self.btn_tab_save]:
            btn.setStyleSheet("QPushButton { background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; border-radius: 4px; font-weight: bold; width: 28px; height: 28px; } QPushButton:hover { background-color: #3c3c3c; border-color: #0e639c; }")
            self.corner_layout.addWidget(btn)

        self.btn_nav_back.clicked.connect(self.editor_manager.nav_undo)
        self.btn_nav_forward.clicked.connect(self.editor_manager.nav_redo)
        self.btn_tab_search.clicked.connect(self.toggle_active_search)
        self.btn_tab_save.clicked.connect(self._manual_save_wrapper) 
        self.editor_tabs.setCornerWidget(self.corner_widget, Qt.Corner.TopRightCorner)

        QShortcut(QKeySequence('Alt+Left'), self).activated.connect(self.editor_manager.nav_undo)
        QShortcut(QKeySequence('Alt+Right'), self).activated.connect(self.editor_manager.nav_redo)
        
        self.editor_splitter.addWidget(self.editor_tabs)
        
        self.terminal = TerminalWidget(self.project_path)
        self.terminal.setVisible(False) 
        self.editor_splitter.addWidget(self.terminal)
        self.editor_splitter.setSizes([700, 300]) 
        editor_layout.addWidget(self.editor_splitter)
        
        self.bottom_panel = BottomPanelWidget()
        editor_layout.addWidget(self.bottom_panel)
        self.splitter.addWidget(editor_widget)
        self.splitter.setSizes([220, 450, 630])

        # --- ИНИЦИАЛИЗАЦИЯ ЯДРА ---
        self.rag_controller = RagController(self)
        self.code_applier = CodeApplier(self)
        self.git_workflow = GitWorkflow(self)
        
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self._manual_save_wrapper)
        self.shortcut_terminal = QShortcut(QKeySequence("Ctrl+`"), self)
        self.shortcut_terminal.activated.connect(self.status_bar.btn_terminal.click)
        
        self.btn_approve.clicked.connect(self.code_applier.review_and_approve)
        self.btn_reject_main.clicked.connect(self.code_applier.reject_preview)
        
        self.btn_git = self.bottom_panel.btn_git
        self.btn_git.clicked.connect(self.git_workflow.open_git_dialog)
        
        # --- ПРОБРОС КНОПКИ RAG ДЛЯ КОНТРОЛЛЕРА ---
        self.btn_rag = self.bottom_panel.btn_rag
        
        self.bottom_panel.btn_attach.clicked.connect(self.open_attachment_dialog)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.bottom_panel.btn_history.clicked.connect(self.show_history)
        self.bottom_panel.btn_api.clicked.connect(self.open_api_settings)
        self.status_bar.btn_terminal.clicked.connect(self.toggle_terminal)
        self.bottom_panel.btn_rag.clicked.connect(self.rag_controller.start_indexing)
        self.bottom_panel.btn_rag.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.bottom_panel.btn_rag.customContextMenuRequested.connect(self.rag_controller.show_analytics)

        self.ai_controller = AIController(self)
        self.ai_controller.start()
        
        self.terminal.ai_fix_requested.connect(self.ai_controller.handle_terminal_error)
        self.bottom_panel.btn_relay.clicked.connect(self.ai_controller.force_relay)
        
        self.btn_chat.clicked.connect(lambda: self.ai_controller.send_task(is_coding_mode=False))
        self.btn_code.clicked.connect(lambda: self.ai_controller.send_task(is_coding_mode=True))
        self.prompt_input.send_signal.connect(lambda: self.ai_controller.send_task(is_coding_mode=True))

        self._check_project_environment()
        self.chat_handler.load_recent_chat_history()

    @property
    def editor(self):
        widget = self.editor_tabs.currentWidget()
        return widget if isinstance(widget, DarkPythonEditor) else None

    def toggle_active_search(self):
        if self.editor: self.editor.search_panel.toggle_panel()

    def get_selected_engine_data(self):
        return self.status_bar.get_selected_engine_data()
        
    def get_current_target_id(self):
        return self.status_bar.get_current_target_id()

    def open_api_settings(self):
        if APISettingsDialog(self).exec():
            self.status_bar.refresh_engine_list()

    def open_attachment_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите картинки", self.project_path, "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)")
        if files:
            for f in files: self.attachment_panel.add_attachment(os.path.normpath(f))

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
                zoom = self.settings.value("editor_zoom", 0, type=int)
                new_zoom = min(20, zoom + 1) if delta > 0 else max(-10, zoom - 1)
                self.editor.zoomTo(new_zoom)
                self.settings.setValue("editor_zoom", new_zoom)
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
        
        if hasattr(self.ai_controller, 'mcp_manager'):
            self.ai_controller.mcp_manager.update_project_path(new_path)

        self.rag_controller.cleanup()
        self.rag_controller = RagController(self)
        self.rag_controller.setup_watcher()
        self.bottom_panel.btn_rag.customContextMenuRequested.connect(self.rag_controller.show_analytics)
        
        for p in self.editor_manager.file_watcher.files():
            self.editor_manager.file_watcher.removePath(p)
            
        self.editor_manager.opened_editors.clear()
        self.editor_tabs.clear()
        self.current_file_path = None
        
        project_hash = os.path.basename(new_path)
        saved_tabs = self.settings.value(f"session_tabs_{project_hash}", [])
        if not saved_tabs:
            self.editor_tabs.addTab(DarkPythonEditor(), "Ничего не открыто")
        else:
            for path in saved_tabs:
                if isinstance(path, str) and os.path.exists(path):
                    self.editor_manager.open_file(path)
        
        self.proposed_updates = []
        self.btn_reject_main.setVisible(False)
        self.btn_approve.setText("✅ Утвердить")
        self.attached_files.clear()
        self.prompt_input.highlighter.rehighlight()
        self.attachment_panel.clear()
        self.chat_history.clear()
        self.log_system(f"📁 Проект успешно загружен: {os.path.basename(new_path)}", color="#31a24c", is_bold=True)
        self._check_project_environment()
        self.chat_handler.load_recent_chat_history()

    def _check_project_environment(self):
        self.update_git_status()
        if self.project_path == QDir.currentPath() or len(self.project_path) <= 3: return
        if not self.git_manager.is_repo():
            if self.show_question("Git", "Инициализировать Git-репозиторий?") == QMessageBox.StandardButton.Yes:
                self.git_manager.init_repo()
                self.update_git_status()

    def handle_tree_tags(self, files, is_attach):
        formatted_files = [f"@[{f}]" for f in files]
        self.prompt_input.insertPlainText(" ".join(formatted_files) + " ")
        if is_attach:
            for f in files: self.attached_files.add(f)
        self.prompt_input.highlighter.rehighlight()
        self.prompt_input.setFocus()

    def handle_tag_action(self, filename, is_attach):
        if is_attach: self.attached_files.add(filename)
        else: self.attached_files.discard(filename)
        self.prompt_input.highlighter.rehighlight()

    def open_inspector(self, trace_id=None):
        trace = getattr(self.ai_controller, 'agent_trace', [])
        if trace or trace_id:
            InspectorDialog(self, trace, trace_id=trace_id).exec()

    def show_raw_text_dialog(self, title, text):
        dlg = QDialog(self); dlg.setWindowTitle(title); dlg.resize(800, 600)
        layout = QVBoxLayout(dlg); txt = QTextBrowser(); txt.setPlainText(text)
        txt.setStyleSheet("background-color: #252526; border: none; font-family: Consolas;")
        layout.addWidget(txt); dlg.exec()

    def show_popup(self, title, message, is_error=False):
        msg = QMessageBox(self); msg.setWindowTitle(title); msg.setText(message)
        msg.setIcon(QMessageBox.Icon.Critical if is_error else QMessageBox.Icon.Information)
        msg.setStyleSheet("QMessageBox { background-color: #252526; color: #d4d4d4; } QPushButton { background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold; }")
        msg.exec()

    def show_question(self, title, message):
        dlg = QDialog(self); dlg.setWindowTitle(title); layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(message)); btn_layout = QHBoxLayout()
        btn_yes = QPushButton("Да"); btn_no = QPushButton("Нет")
        btn_yes.setStyleSheet("background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold;")
        btn_no.setStyleSheet("background-color: #333333; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold;")
        btn_yes.clicked.connect(lambda: dlg.done(QMessageBox.StandardButton.Yes))
        btn_no.clicked.connect(lambda: dlg.done(QMessageBox.StandardButton.No))
        btn_layout.addStretch(); btn_layout.addWidget(btn_yes); btn_layout.addWidget(btn_no)
        layout.addLayout(btn_layout); return dlg.exec()

    def update_status_bar(self):
        total = self.tokens_sent + self.tokens_received
        self.status_bar.showMessage(f"🟢 Сессия: ~{total:,} | ⬆️: ~{self.tokens_sent:,} | ⬇️: ~{self.tokens_received:,}")

    def toggle_terminal(self):
        self.terminal.setVisible(self.status_bar.btn_terminal.isChecked())
        if self.terminal.isVisible(): self.terminal.input_line.setFocus()

    def toggle_pause(self):
        is_paused = self.btn_pause.isChecked()
        self.ai_controller.bridge.is_paused = is_paused
        if is_paused:
            self.btn_pause.setText('▶ Продолжить')
            self.log_system('Система на паузе. Очередь задач очищена.', color='#ffaa00', is_bold=False)
            
            if hasattr(self.ai_controller.bridge, 'clear_queue'):
                self.ai_controller.bridge.clear_queue()
        else:
            self.btn_pause.setText('⏸ Пауза')
            self.log_system('Работа возобновлена', color='#858585', is_bold=False)

    def show_history(self):
        HistoryDialog(self, self.chat_logger).exec()

    def force_fetch_answer(self):
        self.log_system("📥 Инициирован ручной перехват ответа...", color="#bb86fc", is_bold=True)
        target = self.get_current_target_id()
        self.ai_controller.bridge.add_task("___FORCE_FETCH___", target_id=target, images=[])

    # --- WRAPPERS FOR MANAGERS ---
    def log_system(self, text, color="#858585", is_bold=False):
        self.chat_handler.log_system(text, color, is_bold)

    def scroll_chat(self):
        self.chat_handler.scroll_chat()

    def _manual_save_wrapper(self):
        self.code_applier.manual_save()
        self.editor_manager.clear_dirty_mark(self.current_file_path)

    def closeEvent(self, event):
        if self.project_path:
            project_hash = os.path.basename(self.project_path)
            self.settings.setValue(f"session_tabs_{project_hash}", self.editor_manager.get_all_opened_paths())
        super().closeEvent(event)