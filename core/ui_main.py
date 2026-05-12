import os
import re
import base64
import json
import shutil
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter, 
                             QVBoxLayout, QDialog, QTabWidget, QTextBrowser, 
                             QLabel, QFileDialog, QPushButton, QMessageBox, QSizePolicy, QApplication)
from PyQt6.QtCore import Qt, QDir, QUrl, QSettings, QEvent, QFileSystemWatcher, QTimer, QMimeData
from PyQt6.QtGui import QShortcut, QKeySequence, QAction, QDrag, QPixmap

# Импорты ядра
from core.editor import DarkPythonEditor
from core.ai_controller import AIController
from core.code_applier import CodeApplier
from core.git_workflow import GitWorkflow
from core.file_ops import FileManager
from core.chat_logger import ChatLogger
from core.history_viewer import HistoryDialog
from core.inspector_dialog import InspectorDialog

# Импорты UI-модулей
from core.custom_widgets import TagHighlighter, VibeTextEdit, VibeChatBrowser, AttachmentPanel
from core.file_explorer import FileExplorerWidget
from core.time_machine import TimeMachineDialog
from core.git_manager import GitManager
from core.api_settings_dialog import APISettingsDialog
from core.terminal import TerminalWidget

from core.rag_controller import RagController
from core.status_bar import VibeStatusBar
from core.bottom_panel import BottomPanelWidget

class VibeDragButton(QPushButton):
    """
    Гибридная кнопка отправки v3.0 (Умный Drag).
    """
    def __init__(self, text, main_window):
        super().__init__(text)
        self.mw = main_window
        self.drag_start_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Клик — Обычная отправка\nПеретаскивание — Мгновенный Drop файлов + Ctrl+V текста")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self.drag_start_pos:
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        self.drag_start_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.start_vibe_drag()

    def start_vibe_drag(self):
        user_text = self.mw.prompt_input.toPlainText().strip()
        if not user_text:
            self.mw.log_system("⚠️ Введите запрос перед перетягиванием!", color="#ffaa00")
            return

        payload = self.mw.ai_controller.context_builder.build_payload(user_text, is_coding_mode=True, is_browser=True)
        full_prompt = payload["text"]
        image_paths = payload.get("image_paths", [])

        # ОТОБРАЖЕНИЕ В ЧАТЕ И ЛОГАХ
        mode_notice = "⚡ Кодинг (Hybrid Drag)"
        self.mw.chat_logger.log("USER", user_text)
        self.mw.chat_history.append(f"<br><span style='color: #569cd6;'><b>ВЫ</b> [{mode_notice}]: {user_text}</span>")
        self.mw.scroll_chat()
        
        self.mw.tokens_sent += self.mw.ai_controller.estimate_tokens(full_prompt)
        self.mw.update_status_bar()

        # Всегда копируем огромный текст в системный буфер обмена для мгновенного Ctrl+V
        QApplication.clipboard().setText(full_prompt)

        # ЕСЛИ ЕСТЬ КАРТИНКИ: инициируем физическое перетаскивание
        if image_paths:
            self.mw.log_system("🚀 Сборка пакета с картинками...", color="#bb86fc")
            self.mw.log_system("📋 Текст в буфере. Бросьте файлы в чат -> нажмите Ctrl+V -> Enter.", color="#31a24c", is_bold=True)
            
            transit_dir = Path(self.mw.project_path) / ".vibecoder" / "transit"
            transit_dir.mkdir(parents=True, exist_ok=True)
            
            urls = []
            for img_path in image_paths:
                if os.path.exists(img_path):
                    urls.append(QUrl.fromLocalFile(os.path.realpath(img_path)))

            drag = QDrag(self)
            mime = QMimeData()
            if urls:
                mime.setUrls(urls)
            
            drag.setMimeData(mime)
            drag.setPixmap(self.grab().scaled(120, 45, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            
            result = drag.exec(Qt.DropAction.CopyAction)
            
            QTimer.singleShot(20000, lambda: self.cleanup_transit(transit_dir))
            
            if result != Qt.DropAction.IgnoreAction:
                self.mw.prompt_input.clear()
                self.mw.attachment_panel.clear()
                self.mw.ai_controller.register_drag_task(full_prompt)
        
        # ЕСЛИ КАРТИНОК НЕТ: просто очищаем поле и ждем ответа, без визуального "пустого" перетаскивания
        else:
            self.mw.log_system("📋 Картинки не прикреплены. Текст скопирован в буфер!", color="#bb86fc")
            self.mw.log_system("👉 Перейдите в чат -> нажмите Ctrl+V -> Enter.", color="#31a24c", is_bold=True)
            self.mw.prompt_input.clear()
            self.mw.attachment_panel.clear()
            self.mw.ai_controller.register_drag_task(full_prompt)

    def cleanup_transit(self, transit_dir):
        try:
            if transit_dir.exists():
                shutil.rmtree(transit_dir)
        except:
            pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VibeCoder v1.27 — Pro IDE Edition")
        
        self.settings = QSettings("VibeCoder", "Preferences")
        self.api_settings = QSettings("VibeCoder", "API_Config")
        
        self.attached_files = set()
        self.last_full_prompt = ""
        self.current_git_dialog = None
        
        self.opened_editors = {}
        
        # Защита от внешних изменений
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.fileChanged.connect(self.handle_external_file_change)
        
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
        
        self.status_bar = VibeStatusBar(self)
        self.setStatusBar(self.status_bar)
        
        self.tokens_sent = 0
        self.tokens_received = 0
        self.update_status_bar()
        
        self.file_manager = FileManager(self.project_path)
        self.chat_logger = ChatLogger(self.project_path)
        self.git_manager = GitManager(self.project_path)
        
        self.file_explorer = FileExplorerWidget(self.project_path)
        self.file_explorer.file_opened.connect(self.open_file)
        self.file_explorer.log_message.connect(self.log_system)
        self.file_explorer.show_popup_msg.connect(self.show_popup)
        self.file_explorer.project_changed.connect(self.handle_project_changed)
        self.file_explorer.insert_tags_signal.connect(self.handle_tree_tags)
        self.file_explorer.open_time_machine_signal.connect(self.open_time_machine)
        self.splitter.addWidget(self.file_explorer)
        
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

        input_container = QWidget()
        input_container.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px;")
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(2, 2, 2, 2)
        input_layout.setSpacing(2)
        
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

        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(5, 0, 5, 5)
        
        def get_btn_style(bg, hover, pressed, color="white", border="none"):
            return f"""
                QPushButton {{ background-color: {bg}; color: {color}; border: {border}; font-weight: bold; border-radius: 3px; padding: 4px 12px; font-size: 11px; margin-left: 5px; }}
                QPushButton:hover {{ background-color: {hover}; }}
                QPushButton:pressed {{ background-color: {pressed}; }}
            """

        self.btn_inspector = QPushButton("🐞 Инспектор")
        self.btn_inspector.setFixedHeight(26)
        self.btn_inspector.setMinimumWidth(80)
        self.btn_inspector.setStyleSheet(get_btn_style("#005f73", "#007891", "#00404d"))
        self.btn_inspector.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.btn_inspector.clicked.connect(self.open_inspector)

        self.btn_approve = QPushButton("✅ Утвердить код")
        self.btn_approve.setFixedHeight(26)
        self.btn_approve.setMinimumWidth(100)
        self.btn_approve.setStyleSheet(get_btn_style("#2e7d32", "#388e3c", "#1b5e20"))
        self.btn_approve.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        
        self.btn_reject_main = QPushButton("❌ Отклонить")
        self.btn_reject_main.setFixedHeight(26)
        self.btn_reject_main.setMinimumWidth(80)
        self.btn_reject_main.setStyleSheet(get_btn_style("#512525", "#6b2f2f", "#3a1919"))
        self.btn_reject_main.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.btn_reject_main.setVisible(False)

        self.btn_pause = QPushButton("■ Пауза")
        self.btn_pause.setCheckable(True)
        self.btn_pause.setFixedHeight(26)
        self.btn_pause.setMinimumWidth(70)
        self.btn_pause.setStyleSheet("""
            QPushButton { background-color: #d32f2f; color: white; border: none; font-weight: bold; border-radius: 3px; padding: 4px 12px; font-size: 11px; margin-left: 5px; }
            QPushButton:hover { background-color: #e53935; }
            QPushButton:pressed { background-color: #b71c1c; }
            QPushButton:checked { background-color: #31a24c; }
            QPushButton:checked:hover { background-color: #38b056; }
            QPushButton:checked:pressed { background-color: #247a38; }
        """)
        self.btn_pause.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)

        self.btn_chat = QPushButton("💬 Спросить")
        self.btn_chat.setFixedHeight(26)
        self.btn_chat.setMinimumWidth(80)
        self.btn_chat.setStyleSheet(get_btn_style("transparent", "rgba(86, 156, 214, 0.1)", "rgba(86, 156, 214, 0.25)", color="#569cd6", border="1px solid #569cd6"))
        self.btn_chat.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)

        self.btn_code = VibeDragButton("⚡ Кодить", self)
        self.btn_code.setFixedHeight(26)
        self.btn_code.setMinimumWidth(80)
        self.btn_code.setStyleSheet(get_btn_style("#0e639c", "#1177bb", "#094771"))
        self.btn_code.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)

        action_layout.addWidget(self.btn_inspector)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_approve)
        action_layout.addWidget(self.btn_reject_main)
        action_layout.addWidget(self.btn_pause)
        action_layout.addWidget(self.btn_chat)
        action_layout.addWidget(self.btn_code)

        input_layout.addLayout(action_layout)
        
        chat_splitter.addWidget(input_container)
        chat_splitter.setSizes([600, 200])
        chat_layout.addWidget(chat_splitter)
        self.splitter.addWidget(chat_widget)
        
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(5, 5, 5, 5)
        
        self.editor_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.setMovable(True)
        self.editor_tabs.tabCloseRequested.connect(self.close_tab)
        
        # --- Угловой виджет управления вкладками ---
        self.corner_widget = QWidget()
        self.corner_layout = QHBoxLayout(self.corner_widget)
        self.corner_layout.setContentsMargins(0, 0, 5, 0)
        self.corner_layout.setSpacing(2)

        self.btn_nav_back = QPushButton("◀")
        self.btn_nav_forward = QPushButton("▶")
        self.btn_tab_search = QPushButton("🔍")
        self.btn_tab_save = QPushButton("💾")
        
        btn_corner_style = """
            QPushButton { 
                background-color: #252526; 
                color: #d4d4d4; 
                border: 1px solid #3c3c3c; 
                border-radius: 4px; 
                font-size: 14px; 
                font-weight: bold;
                width: 28px;
                height: 28px;
            }
            QPushButton:hover { 
                background-color: #3c3c3c; 
                border-color: #0e639c; 
            }
            QPushButton:pressed {
                background-color: #0e639c;
                color: white;
            }
        """
        for btn in [self.btn_nav_back, self.btn_nav_forward, self.btn_tab_search, self.btn_tab_save]:
            btn.setStyleSheet(btn_corner_style)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.corner_layout.addWidget(btn)

        self.btn_nav_back.setToolTip("Отменить изменение (Undo)")
        self.btn_nav_forward.setToolTip("Вернуть изменение (Redo)")
        self.btn_tab_search.setToolTip("Поиск по коду (Ctrl+F)")
        self.btn_tab_save.setToolTip("Сохранить файл (Ctrl+S)")

        self.btn_nav_back.clicked.connect(self.nav_go_back)
        self.btn_nav_forward.clicked.connect(self.nav_go_forward)
        self.btn_tab_search.clicked.connect(self.toggle_active_search)
        self.btn_tab_save.clicked.connect(self._manual_save_wrapper) 
        
        self.editor_tabs.setCornerWidget(self.corner_widget, Qt.Corner.TopRightCorner)

        QShortcut(QKeySequence('Alt+Left'), self).activated.connect(self.nav_go_back)
        QShortcut(QKeySequence('Alt+Right'), self).activated.connect(self.nav_go_forward)
        
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

        self.btn_attach = self.bottom_panel.btn_attach
        self.btn_history = self.bottom_panel.btn_history
        self.btn_relay = self.bottom_panel.btn_relay
        self.btn_api = self.bottom_panel.btn_api
        self.btn_git = self.bottom_panel.btn_git
        self.btn_rag = self.bottom_panel.btn_rag
        self.btn_terminal = self.status_bar.btn_terminal
        
        self.rag_controller = RagController(self)

        self.current_file_path = None
        self.proposed_updates = [] 
        self.retry_count = 0        
        self.memory_old_code = None 

        self.code_applier = CodeApplier(self)
        self.git_workflow = GitWorkflow(self)
        
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self._manual_save_wrapper)
        
        self.shortcut_terminal = QShortcut(QKeySequence("Ctrl+`"), self)
        self.shortcut_terminal.activated.connect(self.btn_terminal.click)
        
        self.btn_approve.clicked.connect(self.code_applier.review_and_approve)
        self.btn_reject_main.clicked.connect(self.code_applier.reject_preview)
        self.btn_git.clicked.connect(self.git_workflow.open_git_dialog)
        
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
        
        self.terminal.ai_fix_requested.connect(self.ai_controller.handle_terminal_error)
        
        self.bottom_panel.update_mcp_status(
            self.ai_controller.mcp_manager.status, 
            self.ai_controller.mcp_manager.error_message
        )
        
        self.btn_chat.clicked.connect(lambda: self.ai_controller.send_task(is_coding_mode=False))
        self.btn_code.clicked.connect(lambda: self.ai_controller.send_task(is_coding_mode=True))
        self.prompt_input.send_signal.connect(lambda: self.ai_controller.send_task(is_coding_mode=True))
        self.btn_relay.clicked.connect(self.ai_controller.force_relay)

        self._check_project_environment()
        self._load_recent_chat_history()

    @property
    def editor(self):
        widget = self.editor_tabs.currentWidget()
        return widget if isinstance(widget, DarkPythonEditor) else None

    def toggle_active_search(self):
        if self.editor:
            self.editor.search_panel.toggle_panel()

    def get_selected_engine_data(self):
        return self.status_bar.get_selected_engine_data()
        
    def get_current_target_id(self):
        return self.status_bar.get_current_target_id()

    # =========================================================
    # ЛОГИКА ЭКСПОРТА DEBUG-ЛОГОВ И КЛИКОВ
    # =========================================================
    def show_chat_context_menu(self, pos):
        menu = self.chat_history.createStandardContextMenu()
        
        # Проверяем, есть ли ссылка trace:// под курсором
        anchor = self.chat_history.anchorAt(pos)
        if anchor.startswith("trace://"):
            trace_id = anchor.replace("trace://", "")
            menu.addSeparator()
            
            act_copy = QAction("📋 Скопировать Debug-пакет для анализа", self)
            act_copy.triggered.connect(lambda: self.export_debug_log(trace_id, to_file=False))
            
            act_save = QAction("💾 Сохранить Debug-пакет как .txt", self)
            act_save.triggered.connect(lambda: self.export_debug_log(trace_id, to_file=True))
            
            menu.addAction(act_copy)
            menu.addAction(act_save)
            
        menu.addSeparator()
        action_clear = menu.addAction("🗑️ Очистить окно чата")
        action = menu.exec(self.chat_history.viewport().mapToGlobal(pos))
        if action == action_clear:
            self.chat_history.clear()
            self.log_system("Окно чата очищено (история сохранена в базе данных).")

    def export_debug_log(self, trace_id, to_file=True):
        """Собирает Чат + Систему + Трейс в один ультимативный отчет"""
        trace_file = os.path.join(self.project_path, ".vibecoder", "agent_traces.json")
        if not os.path.exists(trace_file):
            self.show_popup("Ошибка экспорта", "Файл с логами агента не найден.", is_error=True)
            return

        try:
            with open(trace_file, 'r', encoding='utf-8') as f:
                traces = json.load(f)
            
            # Ищем нужный лог
            trace_data = next((t for t in traces if t["id"] == trace_id), None)
            if not trace_data:
                self.log_system("❌ Ошибка: Лог сессии не найден в архиве.", color="#ff4444")
                return

            # Формируем документ
            lines = [
                f"=== VIBECODER DEBUG REPORT ===",
                f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Project: {self.project_path}",
                f"Trace ID: {trace_id}",
                f"Engine: {self.get_selected_engine_data().get('model', 'Unknown')}",
                "-" * 40,
                "\n[БЛОК А: КОНТЕКСТ ЧАТА (Последние сообщения)]"
            ]
            
            # Берем последние 10 сообщений из логгера для понимания нити беседы
            chat_logs = self.chat_logger.get_all()[-10:]
            for log in chat_logs:
                lines.append(f"[{log['role']}]: {log['content'][:500]}{'...' if len(log['content']) > 500 else ''}")

            lines.append("\n" + "="*40)
            lines.append("[БЛОК Б: СКРЫТЫЙ СЛЕД АГЕНТА (TRACE)]")
            
            for i, step in enumerate(trace_data["steps"], 1):
                lines.append(f"\n--- ШАГ {i}: {step.get('title', 'Unknown')} ---")
                lines.append(step.get("content", ""))

            final_text = "\n".join(lines)

            if to_file:
                file_name, _ = QFileDialog.getSaveFileName(
                    self, "Сохранить лог для анализа", 
                    os.path.expanduser(f"~/Desktop/VibeDebug_{trace_id}.txt"), 
                    "Text Files (*.txt)"
                )
                if file_name:
                    with open(file_name, 'w', encoding='utf-8') as f:
                        f.write(final_text)
                    self.log_system(f"✅ Отладочный лог сохранен: {os.path.basename(file_name)}", color="#31a24c")
            else:
                QApplication.clipboard().setText(final_text)
                self.log_system("📋 Debug-пакет скопирован в буфер обмена.", color="#31a24c")

        except Exception as e:
            self.show_popup("Ошибка экспорта", f"Не удалось собрать пакет: {e}", is_error=True)

    def handle_chat_link(self, url: QUrl):
        url_str = url.toString()
        
        # --- Перехват кликов по скрытым логам инспектора ---
        if url_str.startswith("trace://"):
            trace_id = url.host() if url.host() else url_str.replace("trace://", "")
            self.open_inspector(trace_id=trace_id)
            return
            
        if url_str.startswith("copycode://"):
            try:
                block_id = url_str.split("copycode://")[1]
                raw_code = self.ai_controller.orchestrator.code_blocks_memory.get(block_id, "")
                if raw_code:
                    QApplication.clipboard().setText(raw_code)
                    self.log_system("📋 Код успешно скопирован в буфер обмена!", color="#31a24c", is_bold=True)
                else:
                    self.log_system("❌ Ошибка: Код устарел или не найден в памяти сессии.", color="#d32f2f", is_bold=True)
            except Exception as e:
                self.log_system(f"❌ Ошибка копирования кода: {e}", color="#d32f2f", is_bold=True)
            return
        
        if "relay" in url_str:
            entry_id = url.path() if url.scheme() == "relay" else url_str.split(":")[-1]
            entry = self.chat_logger.get_by_id(entry_id)
            if entry and entry.get("hidden_data"):
                self.show_raw_text_dialog("Текст Эстафеты", entry["hidden_data"])

    def open_api_settings(self):
        dialog = APISettingsDialog(self)
        if dialog.exec():
            self.status_bar.refresh_engine_list()

    def open_attachment_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите картинки", self.project_path, "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)"
        )
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
        
        # Обновляем базовые менеджеры
        self.file_manager = FileManager(new_path)
        self.chat_logger = ChatLogger(new_path)
        self.git_manager = GitManager(new_path)
        self.prompt_input.project_path = new_path
        self.terminal.update_project_path(new_path)
        
        if hasattr(self.ai_controller, 'mcp_manager'):
            self.ai_controller.mcp_manager.update_project_path(new_path)

        if hasattr(self, 'rag_controller') and self.rag_controller:
            self.rag_controller.cleanup()
            try:
                self.btn_rag.customContextMenuRequested.disconnect()
            except:
                pass
            
        self.rag_controller = RagController(self)
        self.rag_controller.setup_watcher()
        self.btn_rag.customContextMenuRequested.connect(self.rag_controller.show_analytics)
        
        for p in self.file_watcher.files():
            self.file_watcher.removePath(p)
            
        self.opened_editors.clear()
        self.editor_tabs.clear()
        self.current_file_path = None
        
        project_hash = os.path.basename(new_path)
        saved_tabs = self.settings.value(f"session_tabs_{project_hash}", [])
        
        if not saved_tabs:
            self.editor_tabs.addTab(DarkPythonEditor(), "Ничего не открыто")
        else:
            for path in saved_tabs:
                if isinstance(path, str) and os.path.exists(path):
                    self.open_file(path)
        
        self.memory_old_code = None
        self.proposed_updates = []
        self.btn_reject_main.setVisible(False)
        self.btn_approve.setText("✅ Утвердить код")
        
        self.attached_files.clear()
        self.prompt_input.highlighter.rehighlight()
        self.attachment_panel.clear()
        
        self.chat_history.clear()
        self.log_system(f"📁 Проект успешно загружен: {os.path.basename(new_path)}", color="#31a24c", is_bold=True)
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
                    self.log_system("Git репозиторий инициализирован!", color="#31a24c", is_bold=True)
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
                
                if role == "USER":
                    safe_content = content.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
                    self.chat_history.append(f"<br><span style='color: #569cd6;'><b>ВЫ:</b> {safe_content}</span>")
                elif role == "AI":
                    formatted = self.ai_controller.orchestrator.markdown_to_html(content)
                    self.chat_history.append(f"<span style='color: #31a24c;'><b>[МЫСЛИ ИИ]:</b></span>{formatted}")
                elif role == "SYSTEM":
                    self.chat_history.append(f"<div style='color: #858585; font-size: 13px; margin-left: 10px;'>[СИСТЕМА] {content}</div>")
            
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
                self.close_tab_by_path(del_path)
            return
        if self.proposed_updates:
            self.show_popup("Внимание", "Сначала утвердите или отклоните текущие изменения кода!")
            return
            
        path = os.path.normpath(path)
        if path in self.opened_editors:
            index = self.editor_tabs.indexOf(self.opened_editors[path])
            self.editor_tabs.setCurrentIndex(index)
            self.current_file_path = path
            return

        if os.path.isfile(path):
            new_editor = DarkPythonEditor()
            zoom = self.settings.value("editor_zoom", 0, type=int)
            new_editor.zoomTo(zoom)
            new_editor.installEventFilter(self)
            
            with open(path, 'r', encoding='utf-8') as f:
                new_editor.setText(f.read())
            
            if self.editor_tabs.count() == 1 and self.editor_tabs.tabText(0) == "Ничего не открыто":
                 self.editor_tabs.removeTab(0)
                 
            index = self.editor_tabs.addTab(new_editor, f"📄 {os.path.basename(path)}")
            self.editor_tabs.setTabToolTip(index, path)
            self.editor_tabs.setCurrentIndex(index)
            
            self.opened_editors[path] = new_editor
            self.current_file_path = path
            
            new_editor.textChanged.connect(lambda p=path: self.mark_tab_dirty(p))
            
            if path not in self.file_watcher.files():
                self.file_watcher.addPath(path)

    def open_time_machine(self, file_path):
        dialog = TimeMachineDialog(self, file_path, self.file_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.log_system(f"Файл {os.path.basename(file_path)} успешно восстановлен из бэкапа!", color="#d32f2f", is_bold=True)
            if self.current_file_path == file_path:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.editor.setText(f.read())
            self.update_git_status()

    def handle_tag_action(self, filename, is_attach):
        if is_attach: self.attached_files.add(filename)
        else: self.attached_files.discard(filename)
        self.prompt_input.highlighter.rehighlight()

    def open_inspector(self, trace_id=None):
        trace = getattr(self.ai_controller, 'agent_trace', [])
        if not trace and not trace_id:
            self.show_raw_text_dialog("Сырой запрос к ИИ", self.last_full_prompt or "Пока нет данных. Отправьте запрос.")
        else:
            dlg = InspectorDialog(self, trace, trace_id=trace_id)
            dlg.exec()

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

    def toggle_terminal(self):
        if self.btn_terminal.isChecked():
            self.terminal.setVisible(True)
            self.terminal.input_line.setFocus()
        else:
            self.terminal.setVisible(False)

    def toggle_pause(self):
        if self.btn_pause.isChecked():
            self.ai_controller.bridge.is_paused = True
            self.btn_pause.setText("▶ Продолжить")
            self.btn_pause.setStyleSheet("background-color: #31a24c; color: white; font-weight: bold; border-radius: 3px; padding: 4px 12px; font-size: 11px; margin-left: 5px;")
            self.log_system("⏸ РАБОТА ПРИОСТАНОВЛЕНА", color="#ffaa00", is_bold=True)
        else:
            self.ai_controller.bridge.is_paused = False
            self.btn_pause.setText("■ Пауза")
            self.btn_pause.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; border-radius: 3px; padding: 4px 12px; font-size: 11px; margin-left: 5px;")
            self.log_system("▶ РАБОТА ВОЗОБНОВЛЕНА", color="#31a24c", is_bold=True)

    def show_history(self):
        dlg = HistoryDialog(self, self.chat_logger)
        dlg.exec()

    def log_system(self, text, color="#858585", is_bold=False):
        self.chat_logger.log("SYSTEM", text)
        weight = "bold" if is_bold else "normal"
        html_msg = f"<div style='color: {color}; font-weight: {weight}; font-size: 13px; margin-left: 10px;'>[СИСТЕМА] {text}</div>"
        self.chat_history.append(html_msg)
        self.scroll_chat()

    def scroll_chat(self):
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def close_tab(self, index):
        widget = self.editor_tabs.widget(index)
        path_to_remove = next((p for p, ed in self.opened_editors.items() if ed == widget), None)
        if path_to_remove:
            if path_to_remove in self.file_watcher.files():
                self.file_watcher.removePath(path_to_remove)
            del self.opened_editors[path_to_remove]
        self.editor_tabs.removeTab(index)
        
        if self.editor_tabs.count() == 0:
            self.current_file_path = None
            self.editor_tabs.addTab(DarkPythonEditor(), "Ничего не открыто")

    def close_tab_by_path(self, path):
        if path in self.opened_editors:
            index = self.editor_tabs.indexOf(self.opened_editors[path])
            self.close_tab(index)

    def mark_tab_dirty(self, path):
        if path in self.opened_editors:
            index = self.editor_tabs.indexOf(self.opened_editors[path])
            current_text = self.editor_tabs.tabText(index)
            if not current_text.startswith('*'):
                self.editor_tabs.setTabText(index, '*' + current_text)

    def _manual_save_wrapper(self):
        self.code_applier.manual_save()
        if self.current_file_path and self.current_file_path in self.opened_editors:
            index = self.editor_tabs.indexOf(self.opened_editors[self.current_file_path])
            text = self.editor_tabs.tabText(index)
            if text.startswith('*'):
                self.editor_tabs.setTabText(index, text[1:])

    def nav_go_back(self):
        if self.editor:
            self.editor.undo()

    def nav_go_forward(self):
        if self.editor:
            self.editor.redo()

    def handle_external_file_change(self, path):
        if path in self.opened_editors:
            editor = self.opened_editors[path]
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    disk_content = f.read()
                if editor.text() == disk_content:
                    return
            except Exception:
                pass

            msg = QMessageBox(self)
            msg.setWindowTitle('⚠️ Файл изменен извне')
            msg.setText(f'Файл <b>{os.path.basename(path)}</b> был изменен другой программой.<br><br>Перезагрузить его?')
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setStyleSheet("""
                QMessageBox { background-color: #252526; color: #d4d4d4; } 
                QLabel { color: #d4d4d4; font-size: 13px; } 
                QPushButton { background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold; } 
                QPushButton:hover { background-color: #1177bb; }
            """)
            
            if msg.exec() == QMessageBox.StandardButton.Yes:
                editor.setText(disk_content)
                index = self.editor_tabs.indexOf(editor)
                text = self.editor_tabs.tabText(index)
                if text.startswith('*'):
                    self.editor_tabs.setTabText(index, text[1:])

    def closeEvent(self, event):
        if self.project_path:
            project_hash = os.path.basename(self.project_path)
            opened_paths = list(self.opened_editors.keys())
            self.settings.setValue(f"session_tabs_{project_hash}", opened_paths)
        super().closeEvent(event)