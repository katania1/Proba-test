import os
import re
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter, 
                             QVBoxLayout, QPushButton, QMessageBox, QDialog, 
                             QStatusBar, QTabWidget, QTextBrowser, QComboBox, QLabel, QApplication)
from PyQt6.QtCore import Qt, QDir, pyqtSignal, QUrl, QSettings, QEvent, QTimer
from PyQt6.QtGui import QFileSystemModel, QShortcut, QKeySequence

from core.editor import DarkPythonEditor
from core.ai_orchestrator import AIOrchestrator
from core.bridge import VibeBridge
from core.file_ops import FileManager
from core.diff_viewer import DiffDialog
from core.chat_logger import ChatLogger
from core.history_viewer import HistoryDialog

# Импорт кастомных виджетов и окон
from core.custom_widgets import TagHighlighter, VibeTextEdit, VibeChatBrowser
from core.file_explorer import FileExplorerWidget
from core.time_machine import TimeMachineDialog
from core.git_manager import GitManager
from core.git_dialog import GitDialog
from core.api_settings_dialog import APISettingsDialog

class MainWindow(QMainWindow):
    ai_response_signal = pyqtSignal(str)
    limit_reached_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VibeCoder v1.15 — Pro Edition (Smart Git & API)")
        
        self.settings = QSettings("VibeCoder", "Preferences")
        self.attached_files = set()
        self.last_full_prompt = ""
        self.current_git_dialog = None
        
        # Флаги состояния для перехвата ответов ИИ
        self.is_waiting_for_commit_msg = False
        self.is_waiting_for_relay_msg = False
        
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
        self.combo_tabs.setStyleSheet("""
            QComboBox { background-color: #252526; color: white; border: 1px solid #3c3c3c; padding: 2px 10px; border-radius: 3px; font-weight: normal; }
            QComboBox::drop-down { border: none; }
        """)
        self.combo_tabs.setMinimumWidth(120)
        
        status_layout.addWidget(lbl_browser)
        status_layout.addWidget(self.combo_tabs)
        self.status_bar.addPermanentWidget(status_container)
        
        self.tab_timer = QTimer(self)
        self.tab_timer.timeout.connect(self.update_tabs_ui)
        self.tab_timer.start(2000)
        
        self.tokens_sent = 0
        self.tokens_received = 0
        self.update_status_bar()
        
        self.orchestrator = AIOrchestrator()
        self.file_manager = FileManager(self.project_path)
        self.chat_logger = ChatLogger(self.project_path)
        self.git_manager = GitManager(self.project_path)
        
        self.bridge = VibeBridge()
        self.bridge.on_result_received = self.receive_from_bridge
        self.bridge.on_limit_reached = lambda: self.limit_reached_signal.emit()
        self.bridge.start_server()
        
        self.ai_response_signal.connect(self.process_ai_response)
        self.limit_reached_signal.connect(self.process_limit_reached)
        
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
        self.prompt_input.send_signal.connect(self.send_task)
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
        self.btn_send.clicked.connect(self.send_task)
        
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
        self.btn_relay.clicked.connect(self.force_relay)
        
        self.btn_git = QPushButton("📦 Git")
        self.btn_git.setToolTip("Управление версиями (Git)")
        self.btn_git.setFixedHeight(35)
        self.btn_git.setStyleSheet("background-color: #4a148c; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_git.clicked.connect(self.open_git_dialog)

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
        self.btn_reject_main.clicked.connect(self.reject_preview)
        
        self.btn_approve = QPushButton("✅ Утвердить код")
        self.btn_approve.setToolTip("Открыть окно ревью (Diff)")
        self.btn_approve.setFixedHeight(35)
        self.btn_approve.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; border-radius: 4px;") 
        self.btn_approve.clicked.connect(self.review_and_approve)
        
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

        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self.manual_save)
        
        self.update_git_status()

    # --- НОВЫЙ ЖЕСТКИЙ ЯКОРЬ ДЛЯ ВКЛАДОК ---
    def get_current_target_id(self):
        """Возвращает ID текущей выбранной вкладки для жесткой маршрутизации."""
        selected_tab = self.combo_tabs.currentText()
        if "[" in selected_tab and "]" in selected_tab:
            return selected_tab.split("[")[-1].split("]")[0]
        return None
    # ----------------------------------------

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

    # =======================================================
    # ОБРАБОТЧИКИ СОБЫТИЙ ИЗ ДЕРЕВА
    # =======================================================
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

    # =======================================================
    # ЛОГИКА БЕЗОПАСНОСТИ И ТЕГОВ
    # =======================================================
    def is_path_safe(self, file_path):
        abs_project = os.path.abspath(self.project_path)
        abs_file = os.path.abspath(os.path.join(self.project_path, file_path))
        return os.path.commonpath([abs_project]) == os.path.commonpath([abs_project, abs_file])

    def get_file_content_safe(self, rel_path):
        if not self.is_path_safe(rel_path): 
            return None
            
        abs_path = os.path.abspath(os.path.join(self.project_path, rel_path))
        if os.path.isfile(abs_path):
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass
        return None

    def handle_tag_action(self, filename, is_attach):
        if is_attach: self.attached_files.add(filename)
        else: self.attached_files.discard(filename)
        self.prompt_input.highlighter.rehighlight()

    # =======================================================
    # СЕТЬ, ИИ И УПРАВЛЕНИЕ ЗАДАЧАМИ
    # =======================================================
    def receive_from_bridge(self, raw_text):
        self.ai_response_signal.emit(raw_text)

    def send_task(self):
        user_text = self.prompt_input.toPlainText().strip()
        if not user_text: return
        
        target_id = self.get_current_target_id()
        selected_tab = self.combo_tabs.currentText()
        
        if "🔴" in selected_tab:
            self.show_popup("Ошибка связи", "Нет активных вкладок браузера!\nОткройте Gemini и обновите страницу.", is_error=True)
            return

        attached_blocks = []
        tags_in_text = re.findall(r'@\[.*?\]|@[\w\.\-\/\\]+', user_text)
        for tag in tags_in_text:
            fname = tag[1:].strip("[]")
            if fname in self.attached_files:
                content = self.get_file_content_safe(fname)
                if content: 
                    attached_blocks.append(f"### ФАЙЛ: {fname} ###\n```\n{content}\n```")
        
        final_prompt_text = user_text + ("\n\n[СИСТЕМНЫЙ БЛОК: ПРИКРЕПЛЕННЫЙ КОД]\n" + "\n\n".join(attached_blocks) + "\n[КОНЕЦ СИСТЕМНОГО БЛОКА]" if attached_blocks else "")
        
        self.chat_logger.log("USER", user_text)
        
        tab_display_name = selected_tab.split(" [")[0].replace("🟢 ", "")
        self.chat_history.append(f"<br><span style='color: #569cd6;'><b>ВЫ</b> (в <i>{tab_display_name}</i>)<b>:</b> {user_text}</span>")
        self.chat_history.append(f"<a href='view_prompt:last' style='color: #65676b; font-size: 10px;'>[Показать сырой промпт]</a>")
            
        file_content = "" 
        
        self.last_full_prompt = self.orchestrator.format_request(
            user_prompt=final_prompt_text, 
            project_path=self.project_path, 
            current_file_path=self.current_file_path, 
            file_content=file_content
        )
        
        self.tokens_sent += self.estimate_tokens(self.last_full_prompt)
        self.update_status_bar()
        self.retry_count = 0 
        
        # Отправляем с жестким якорем вкладки
        self.bridge.add_task(self.last_full_prompt, is_relay=False, target_id=target_id)
        
        self.log_system(f"Задача отправлена в {tab_display_name}. Ожидание ответа...")
        self.prompt_input.clear()

    def process_ai_response(self, raw_text):
        # --- ПЕРЕХВАТ ТРАНЗИТНОГО ПАКЕТА (ЭСТАФЕТЫ) ---
        if getattr(self, 'is_waiting_for_relay_msg', False):
            self.is_waiting_for_relay_msg = False
            self.retry_count = 0
            self.tokens_received += self.estimate_tokens(raw_text)
            self.update_status_bar()
            
            result = self.orchestrator.parse_and_validate_response(raw_text)
            if result["status"] == "error":
                self.show_popup("Ошибка Эстафеты", "ИИ не смог собрать пакет.\nПридется переносить историю вручную.", is_error=True)
            else:
                ai_summary = result["data"].get("thoughts", "")
                
                # Формируем финальный мега-промпт
                mega_prompt = (
                    "Привет! Это транзитный пакет (эстафета) из предыдущего чата. Мы продолжаем работу над нашим проектом.\n\n"
                    "=== БРИФ ОТ ПРЕДЫДУЩЕГО ИИ (СТАТУС И ПЛАН) ===\n"
                    f"{ai_summary}\n\n"
                    "Пожалуйста, внимательно прочитай бриф и вникай в архитектуру.\n"
                    "Для ответа используй СТРОГИЙ ФОРМАТ JSON согласно нашим правилам Оркестратора.\n"
                    "В поле 'thoughts' напиши 'Контекст принял, план ясен, готов к работе', а массивы 'updates' и 'create_files' оставь пустыми []."
                )
                
                # Копируем в буфер обмена
                clipboard = QApplication.clipboard()
                clipboard.setText(mega_prompt)
                
                self.chat_history.append("<span style='color: #31a24c;'><b>[СИСТЕМА] Транзитный пакет успешно скопирован в буфер обмена!</b></span>")
                self.scroll_chat()
                
                self.show_popup("Эстафета готова!", 
                                "Мега-промпт (бриф + контекст) успешно скопирован в буфер обмена!\n\n"
                                "1. Откройте новый чат Gemini (в другом браузере или аккаунте).\n"
                                "2. Выберите эту новую вкладку в VibeCoder.\n"
                                "3. Нажмите Ctrl+V прямо на сайте Gemini и отправьте.\n\n"
                                "Работа будет бесшовно продолжена!")
            return
            
        # --- ПЕРЕХВАТ ИИ-КОММИТА ---
        if getattr(self, 'is_waiting_for_commit_msg', False):
            self.is_waiting_for_commit_msg = False
            self.retry_count = 0
            self.tokens_received += self.estimate_tokens(raw_text)
            self.update_status_bar()
            
            result = self.orchestrator.parse_and_validate_response(raw_text)
            if result["status"] == "error":
                self.show_popup("Ошибка", "ИИ не смог сгенерировать коммит.", is_error=True)
                if hasattr(self, 'current_git_dialog') and self.current_git_dialog:
                    self.current_git_dialog.btn_ai.setText("✨ Сгенерировать ИИ-описание")
                    self.current_git_dialog.btn_ai.setEnabled(True)
            else:
                commit_msg = result["data"].get("thoughts", "Автоматический коммит")
                
                if hasattr(self, 'current_git_dialog') and self.current_git_dialog and self.current_git_dialog.isVisible():
                    self.current_git_dialog.text_input.setPlainText(commit_msg)
                    self.current_git_dialog.btn_ai.setText("✨ Сгенерировать ИИ-описание")
                    self.current_git_dialog.btn_ai.setEnabled(True)
                else:
                    self.open_git_dialog(prefill_msg=commit_msg)
            return
        
        # --- СТАНДАРТНАЯ ОБРАБОТКА КОДА ---
        self.tokens_received += self.estimate_tokens(raw_text)
        self.update_status_bar()
        self.chat_history.append("<span style='color: #bb86fc;'><b>[GEMINI] Ответ получен. Проверка и патчинг...</b></span>")
        result = self.orchestrator.parse_and_validate_response(raw_text)
        
        if result["status"] == "error":
            self.retry_count += 1
            if self.retry_count > 2:
                self.log_system("ИИ не смог выдать код. Включена АВТО-ПАУЗА.", color="#ff4444")
                if not self.btn_pause.isChecked():
                    self.btn_pause.setChecked(True)
                    self.toggle_pause()
                return

            self.log_system(f"ОШИБКА ИИ: {result['error_message']}", color="#ff4444")
            self.log_system(f"Авто-исправление (Попытка {self.retry_count} из 2)...", color="#ffaa00")
            fix_prompt = (f"Твой предыдущий ответ вызвал фатальную ошибку: {result['error_message']}\nКАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать извинения вне JSON.\nВот исходная задача. Пришли чистый JSON для неё:\n{self.last_full_prompt}\n")
            # Отправка с жестким якорем
            self.bridge.add_task(fix_prompt, target_id=self.get_current_target_id())
        else:
            self.retry_count = 0 
            data = result["data"]
            thoughts = data.get('thoughts', '')
            self.chat_logger.log("AI", thoughts)
            if thoughts: self.chat_history.append(f"<span style='color: #31a24c;'><b>[МЫСЛИ ИИ]:</b> {thoughts}</span>")
            
            # 1. ЗАПРОС ФАЙЛОВ
            requested_files = data.get("request_files", [])
            if requested_files:
                self.chat_history.append(f"<span style='color: #e6a822;'><b>[ИИ ЗАПРАШИВАЕТ ФАЙЛЫ]:</b> {', '.join(requested_files)}</span>")
                self.scroll_chat()
                
                msg = QMessageBox(self)
                msg.setWindowTitle("🤖 Запрос контекста")
                msg.setText(f"ИИ просит предоставить код следующих файлов для работы:\n\n" + "\n".join(requested_files) + "\n\nОтправить их сейчас автоматически?")
                msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg.setStyleSheet("QMessageBox { background-color: #252526; color: #d4d4d4; } QLabel { color: #d4d4d4; font-size: 13px; } QPushButton { background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #1177bb; }")
                
                if msg.exec() == QMessageBox.StandardButton.Yes:
                    self.send_requested_files(requested_files)
                    return

            # 2. СОЗДАНИЕ ФАЙЛОВ И ПАПОК
            create_files = data.get("create_files", [])
            if create_files:
                from core.creation_dialog import FileCreationDialog
                dlg = FileCreationDialog(self, create_files)
                if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_files:
                    for path in dlg.selected_files:
                        if not self.is_path_safe(path):
                            self.log_system(f"⚠️ Блокировка: ИИ попытался создать файл вне проекта ({path})", color="#ffaa00")
                            continue
                            
                        abs_path = os.path.abspath(os.path.join(self.project_path, path))
                        dir_name = os.path.dirname(abs_path)
                        
                        if path.endswith('/') or path.endswith('\\'):
                            os.makedirs(abs_path, exist_ok=True)
                            self.log_system(f"📁 Создана папка: {path}", color="#31a24c")
                        else:
                            if dir_name: 
                                os.makedirs(dir_name, exist_ok=True)
                            if not os.path.exists(abs_path):
                                open(abs_path, 'w', encoding='utf-8').close()
                                self.log_system(f"📄 Создан файл: {path}", color="#31a24c")
                    
                    self.update_git_status()
            
            # 3. ОБНОВЛЕНИЕ КОДА (DIFF)
            self.proposed_updates = data.get("updates", [])
            if self.proposed_updates:
                valid_updates = []
                for update in self.proposed_updates:
                    rel_path = update.get("file_path", "")
                    action = update.get("action", "modify")
                    
                    if not self.is_path_safe(rel_path):
                        continue

                    abs_path = os.path.abspath(os.path.join(self.project_path, rel_path))
                    
                    if action == "modify":
                        if not os.path.exists(abs_path):
                            open(abs_path, 'w', encoding='utf-8').close()
                        
                        with open(abs_path, 'r', encoding='utf-8') as f:
                            patched_code = f.read()
                            
                        changes = update.get("changes", [])
                        patch_failed = False
                        failed_search_block = ""
                        
                        for change in changes:
                            search_block = change.get("search", "").replace('\r\n', '\n')
                            replace_block = change.get("replace", "").replace('\r\n', '\n')
                            
                            if search_block == "":
                                patched_code = replace_block
                            elif search_block in patched_code:
                                patched_code = patched_code.replace(search_block, replace_block)
                            else:
                                patch_failed = True
                                failed_search_block = search_block
                                break 
                                
                        if patch_failed:
                            self.log_system(f"ИИ ОШИБСЯ С КОНТЕКСТОМ! Блок не найден в {rel_path}. Запрос переделки...", color="#ffaa00")
                            self.retry_count += 1
                            error_prompt = f"Твой ответ отклонен системой (Smart Diff Error).\nЯ не нашел следующий блок 'search' в файле {rel_path}:\n```python\n{failed_search_block}\n```\nПожалуйста, скопируй ТОЧНЫЕ строки из моего исходного файла в поле 'search'. Или оставь 'search' пустым, если пишешь файл с нуля. Повтори JSON."
                            self.bridge.add_task(error_prompt, target_id=self.get_current_target_id())
                            return
                        
                        update["code"] = patched_code
                    
                    valid_updates.append(update)
                
                self.proposed_updates = valid_updates
                
                if self.proposed_updates:
                    self.btn_reject_main.setVisible(True)
                    self.btn_approve.setText(f"✅ Ревью (Файлов: {len(self.proposed_updates)})")
                    self.log_system(f"ИИ предлагает изменить {len(self.proposed_updates)} файл(а). Жмите Ревью.", color="#31a24c")
                    
        self.scroll_chat()

    def send_requested_files(self, file_paths):
        attached_blocks = []
        for path in file_paths:
            fname = os.path.basename(path)
            content = self.get_file_content_safe(path)
            if content: 
                attached_blocks.append(f"### ФАЙЛ: {path} ###\n```\n{content}\n```")
            else:
                attached_blocks.append(f"### ФАЙЛ: {path} ###\n[ФАЙЛ НЕ НАЙДЕН ИЛИ ПУСТ]")
        
        system_text = "[СИСТЕМНОЕ СООБЩЕНИЕ: ПОЛЬЗОВАТЕЛЬ ПРЕДОСТАВИЛ ЗАПРОШЕННЫЕ ФАЙЛЫ]\n\n" + "\n\n".join(attached_blocks) + "\n\nПроанализируй их и выполни предыдущую задачу."
        
        self.chat_logger.log("SYSTEM", f"Авто-отправка файлов: {', '.join(file_paths)}")
        self.chat_history.append(f"<br><span style='color: #0e639c;'><b>[СИСТЕМА] Автоматически отправлены:</b> {', '.join(file_paths)}</span>")
        self.scroll_chat()
        
        self.last_full_prompt = self.orchestrator.format_request(
            user_prompt=system_text, 
            project_path=self.project_path, 
            current_file_path=self.current_file_path, 
            file_content=""
        )
        
        self.tokens_sent += self.estimate_tokens(self.last_full_prompt)
        self.update_status_bar()
        self.retry_count = 0 
        
        # Жесткий якорь
        self.bridge.add_task(self.last_full_prompt, target_id=self.get_current_target_id())
        self.log_system("Файлы отправлены. Ожидание ответа...")

    def manual_save(self):
        if not self.current_file_path: return
        current_text = self.editor.text()
        
        with open(self.current_file_path, 'r', encoding='utf-8') as f:
            old_text = f.read()
            
        if current_text.replace('\r\n', '\n') != old_text.replace('\r\n', '\n'):
            self.file_manager.save_file(self.current_file_path, current_text) 
            self.log_system(f"Ручное сохранение: {os.path.basename(self.current_file_path)}", color="#31a24c")
            self.show_popup("Сохранено", f"Файл сохранен.\nСоздан бэкап в Машине Времени.")
            self.update_git_status()

    def review_and_approve(self):
        if self.proposed_updates:
            update = self.proposed_updates[0] 
            rel_path = update.get("file_path", "")
            new_code = update.get("code", "")
            abs_path = os.path.abspath(os.path.join(self.project_path, rel_path))
            
            old_code = ""
            if os.path.exists(abs_path):
                with open(abs_path, 'r', encoding='utf-8') as f:
                    old_code = f.read()
                    
            dialog = DiffDialog(self, old_code, new_code, f"{rel_path} (Файл 1 из {len(self.proposed_updates)})")
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.file_manager.save_file(abs_path, new_code)
                
                if self.current_file_path and os.path.normpath(self.current_file_path) == os.path.normpath(abs_path):
                    self.editor.setText(new_code)
                    
                self.log_system(f"Изменения от ИИ в {rel_path} сохранены!", color="#2e7d32")
                self.update_git_status()
                
                self.proposed_updates.pop(0)
                
                if self.proposed_updates:
                    self.btn_approve.setText(f"✅ Ревью (Осталось: {len(self.proposed_updates)})")
                else:
                    self.btn_reject_main.setVisible(False)
                    self.btn_approve.setText("✅ Утвердить код")
            else:
                self.reject_preview()
            return
            
        if self.current_file_path:
            current_text = self.editor.text()
            with open(self.current_file_path, 'r', encoding='utf-8') as f:
                old_text = f.read()
                
            if current_text.replace('\r\n', '\n') != old_text.replace('\r\n', '\n'):
                rel_path = os.path.basename(self.current_file_path)
                dialog = DiffDialog(self, old_text, current_text, rel_path + " (Ручные правки)")
                
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    self.file_manager.save_file(self.current_file_path, current_text)
                    self.log_system(f"Ручные правки в {rel_path} утверждены и сохранены!", color="#2e7d32")
                    self.update_git_status()
                return

        self.show_popup("Пусто", "Нет изменений для утверждения.")

    def reject_preview(self):
        if self.memory_old_code is not None:
            self.editor.setText(self.memory_old_code)
            self.memory_old_code = None
        self.proposed_updates = []
        self.btn_reject_main.setVisible(False)
        self.btn_approve.setText("✅ Утвердить код")
        self.log_system("Предпросмотр отклонен.", color="#ff4444")

    # =======================================================
    # ЛОГИКА GIT
    # =======================================================
    def update_git_status(self):
        if not self.git_manager.is_repo():
            self.btn_git.setText("📦 Git (Инициализировать)")
            self.btn_git.setStyleSheet("background-color: #4a148c; color: white; font-weight: bold; border-radius: 4px;")
            return

        status_count = self.git_manager.get_status()
        if status_count == -1:
            self.btn_git.setText("📦 Git (Ошибка)")
        elif status_count == 0:
            self.btn_git.setText("📦 Git (Чисто)")
            self.btn_git.setStyleSheet("background-color: #252526; color: #888888; font-weight: bold; border-radius: 4px;")
        else:
            self.btn_git.setText(f"📦 Git (Изменено: {status_count})")
            self.btn_git.setStyleSheet("background-color: #e65100; color: white; font-weight: bold; border-radius: 4px;")

    def open_git_dialog(self, prefill_msg=""):
        if not self.git_manager.is_repo():
            reply = QMessageBox.question(self, "Git", "В этой папке нет Git-репозитория. Инициализировать сейчас?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                success, msg = self.git_manager.init_repo()
                if success:
                    self.log_system("Git репозиторий инициализирован!", color="#31a24c")
                    self.update_git_status()
                else:
                    self.show_popup("Ошибка", f"Не удалось инициализировать Git:\n{msg}", is_error=True)
            return

        self.current_git_dialog = GitDialog(self, self.git_manager)
        if prefill_msg:
            self.current_git_dialog.text_input.setPlainText(prefill_msg)
        self.current_git_dialog.exec()
        self.current_git_dialog = None

    def request_ai_commit_message(self, diff_text):
        self.is_waiting_for_commit_msg = True 
        
        if len(diff_text) > 10000:
            diff_text = diff_text[:10000] + "\n...[DIFF СЛИШКОМ БОЛЬШОЙ, ОБРЕЗАН]..."

        prompt = (f"Сгенерируй короткое, профессиональное сообщение для Git коммита на основе этого Diff кода:\n\n"
                  f"```diff\n{diff_text}\n```\n\n"
                  f"Напиши текст коммита в поле 'thoughts', а массив 'updates' оставь пустым []. "
                  f"Пиши на русском языке, используй общепринятые префиксы (feat:, fix:, refactor:). "
                  f"ВАЖНО: КАТЕГОРИЧЕСКИ ЗАПРЕЩАЕТСЯ использовать двойные кавычки (\") внутри текста коммита. "
                  f"Используй только одинарные (') или елочки («»), чтобы не сломать формат JSON!")

        self.chat_logger.log("SYSTEM", "Запрос ИИ-коммита...")
        self.chat_history.append(f"<br><span style='color: #673ab7;'><b>[СИСТЕМА] Отправка diff для генерации ИИ-коммита...</b></span>")
        self.scroll_chat()

        self.last_full_prompt = self.orchestrator.format_request(
            user_prompt=prompt,
            project_path=self.project_path,
            current_file_path=None,
            file_content=""
        )

        self.tokens_sent += self.estimate_tokens(self.last_full_prompt)
        self.update_status_bar()
        self.retry_count = 0

        # Жесткий якорь
        self.bridge.add_task(self.last_full_prompt, target_id=self.get_current_target_id())

    # =======================================================
    # ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ОБРАБОТЧИКИ
    # =======================================================
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

    def process_limit_reached(self):
        if not self.btn_pause.isChecked():
            self.btn_pause.setChecked(True)
            self.toggle_pause()
        self.log_system("🚨 ЛИМИТЫ GEMINI ИСЧЕРПАНЫ! Запускаю авто-сборку Транзитного Пакета...", color="#ff4444")
        self.force_relay()

    def estimate_tokens(self, text):
        return int(len(text) / 2.5)

    def update_status_bar(self):
        total = self.tokens_sent + self.tokens_received
        self.status_bar.showMessage(f"🟢 Текущая сессия: ~{total:,} токенов | ⬆️ Отправлено: ~{self.tokens_sent:,} | ⬇️ Получено: ~{self.tokens_received:,}")

    def toggle_pause(self):
        if self.btn_pause.isChecked():
            self.bridge.is_paused = True
            self.btn_pause.setText("▶ Продолжить")
            self.btn_pause.setStyleSheet("background-color: #31a24c; color: white; font-weight: bold; border-radius: 4px;")
            self.log_system("⏸ РАБОТА ПРИОСТАНОВЛЕНА", color="#ffaa00")
        else:
            self.bridge.is_paused = False
            self.btn_pause.setText("■ Пауза")
            self.btn_pause.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; border-radius: 4px;")
            self.log_system("▶ РАБОТА ВОЗОБНОВЛЕНА", color="#31a24c")

    def show_history(self):
        dlg = HistoryDialog(self, self.chat_logger)
        dlg.exec()

    # --- НОВАЯ СМАРТ-ЭСТАФЕТА (ТРАНЗИТНЫЙ ПАКЕТ) ---
    def force_relay(self):
        self.is_waiting_for_relay_msg = True
        
        prompt = (
            "[СИСТЕМНАЯ КОМАНДА: ФОРМИРОВАНИЕ ТРАНЗИТНОГО ПАКЕТА]\n"
            "Наша сессия подходит к концу из-за исчерпания контекста/лимитов. Твоя задача — передать дела своему 'сменщику' (следующей модели, которая откроет новый чат).\n"
            "Проанализируй всю нашу текущую переписку и составь максимально подробный бриф для продолжения работы.\n\n"
            "Напиши текст в поле 'thoughts' (массив 'updates' оставь пустым), строго следуя этой структуре:\n"
            "1. Глобальная цель: Кратко, что за проект мы пишем.\n"
            "2. Архитектурные правила: Какие технологии используем.\n"
            "3. Текущий прогресс: Что уже успешно реализовано и работает.\n"
            "4. Точка прерывания: На чем конкретно мы остановились прямо сейчас?\n"
            "5. План действий (Next Steps): Четкие инструкции для следующего ИИ.\n\n"
            "ВАЖНО: КАТЕГОРИЧЕСКИ ЗАПРЕЩАЕТСЯ использовать двойные кавычки (\") внутри текста! Используй только одинарные (') или елочки («»)."
        )
        
        self.chat_logger.log("SYSTEM", "Запрос транзитного пакета у ИИ...")
        self.chat_history.append("<br><span style='color: #005f73;'><b>[СИСТЕМА] Сбор Транзитного Пакета (эстафеты)...</b></span>")
        self.scroll_chat()

        self.last_full_prompt = self.orchestrator.format_request(
            user_prompt=prompt,
            project_path=self.project_path,
            current_file_path=self.current_file_path,
            file_content=""
        )
        
        self.tokens_sent += self.estimate_tokens(self.last_full_prompt)
        self.update_status_bar()
        self.retry_count = 0
        
        # Запрашиваем в текущем чате (жесткий якорь)
        self.bridge.add_task(self.last_full_prompt, target_id=self.get_current_target_id())
    # -----------------------------------------------

    def log_system(self, text, color="#0e639c"):
        self.chat_logger.log("SYSTEM", text)
        self.chat_history.append(f"<span style='color: {color};'><b>[СИСТЕМА] {text}</b></span>")
        self.scroll_chat()

    def scroll_chat(self):
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def update_tabs_ui(self):
        if not hasattr(self, 'bridge') or not hasattr(self.bridge, 'get_active_tabs'):
            return
            
        tabs = self.bridge.get_active_tabs()
        current_selection = self.combo_tabs.currentText()

        self.combo_tabs.clear()
        
        if not tabs:
            self.combo_tabs.addItem("🔴 Нет связи")
            self.combo_tabs.setEnabled(False)
        else:
            self.combo_tabs.setEnabled(True)
            for t in tabs:
                self.combo_tabs.addItem(f"🟢 {t}")
                
            index = self.combo_tabs.findText(current_selection)
            if index >= 0:
                self.combo_tabs.setCurrentIndex(index)