import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter, 
                             QTreeView, QTextEdit, QTextBrowser, QVBoxLayout, 
                             QPushButton, QMessageBox, QDialog, QStatusBar, QSizePolicy)
from PyQt6.QtCore import Qt, QDir, pyqtSignal, QUrl, QSettings, QEvent
from PyQt6.QtGui import QFileSystemModel, QKeyEvent, QWheelEvent

from core.editor import DarkPythonEditor
from core.ai_orchestrator import AIOrchestrator
from core.bridge import VibeBridge
from core.file_ops import FileManager
from core.diff_viewer import DiffDialog
from core.chat_logger import ChatLogger
from core.history_viewer import HistoryDialog

# =======================================================
# КАСТОМНЫЕ ПОЛЯ ТЕКСТА (Зум и горячие клавиши)
# =======================================================
class VibeTextEdit(QTextEdit):
    send_signal = pyqtSignal()
    zoom_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_font_size = 11

    def set_custom_font_size(self, size):
        self.current_font_size = size
        # Жестко прописываем стиль, чтобы глобальные CSS его не перебили
        self.setStyleSheet(f"background-color: #252526; border: 1px solid #3c3c3c; border-radius: 3px; color: #d4d4d4; font-size: {size}pt;")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.send_signal.emit()
                return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0: self.set_custom_font_size(min(30, self.current_font_size + 1))
            else: self.set_custom_font_size(max(8, self.current_font_size - 1))
            self.zoom_changed.emit(self.current_font_size) # Сохраняем в память
            return
        super().wheelEvent(event)


class VibeChatBrowser(QTextBrowser):
    zoom_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_font_size = 11

    def set_custom_font_size(self, size):
        self.current_font_size = size
        self.setStyleSheet(f"background-color: #252526; border: 1px solid #3c3c3c; border-radius: 3px; color: #d4d4d4; font-size: {size}pt;")

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0: self.set_custom_font_size(min(30, self.current_font_size + 1))
            else: self.set_custom_font_size(max(8, self.current_font_size - 1))
            self.zoom_changed.emit(self.current_font_size)
            return
        super().wheelEvent(event)


# =======================================================
# ГЛАВНОЕ ОКНО
# =======================================================
class MainWindow(QMainWindow):
    ai_response_signal = pyqtSignal(str)
    limit_reached_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VibeCoder v1.7 — Pro Edition")
        
        # --- БАЗА ДАННЫХ НАСТРОЕК (Сохранение сессий) ---
        self.settings = QSettings("VibeCoder", "Preferences")
        
        self.setStyleSheet("""
            QToolTip { background-color: #252526; color: #d4d4d4; border: 1px solid #569cd6; border-radius: 4px; padding: 5px; font-size: 13px; }
            QSplitter::handle { background-color: #3c3c3c; }
            QSplitter::handle:horizontal { width: 3px; }
            QSplitter::handle:vertical { height: 3px; }
            QSplitter::handle:hover { background-color: #0e639c; }
        """)
        
        screen = self.screen().availableGeometry()
        self.resize(min(1300, screen.width() - 50), min(850, screen.height() - 50))
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.addWidget(self.splitter)
        
        self.project_path = QDir.currentPath() 
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.tokens_sent = 0
        self.tokens_received = 0
        self.update_status_bar()
        
        self.orchestrator = AIOrchestrator()
        self.file_manager = FileManager(self.project_path)
        self.chat_logger = ChatLogger(self.project_path)
        
        self.bridge = VibeBridge()
        self.bridge.on_result_received = self.receive_from_bridge
        self.bridge.on_limit_reached = lambda: self.limit_reached_signal.emit()
        self.bridge.start_server()
        
        self.ai_response_signal.connect(self.process_ai_response)
        self.limit_reached_signal.connect(self.process_limit_reached)
        
        # --- ПАНЕЛЬ 1: Дерево файлов ---
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(self.project_path)
        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_model)
        self.file_tree.setRootIndex(self.file_model.index(self.project_path))
        for i in range(1, 4): self.file_tree.hideColumn(i)
        
        self.file_tree.setHeaderHidden(True)
        self.file_tree.doubleClicked.connect(self.open_file)
        self.splitter.addWidget(self.file_tree)
        
        # --- ПАНЕЛЬ 2: Чат (Логи и ввод) ---
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(5, 5, 5, 5)

        chat_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Интегрируем кастомный браузер чата
        self.chat_history = VibeChatBrowser()
        self.chat_history.setOpenLinks(False)
        self.chat_history.anchorClicked.connect(self.handle_chat_link)
        self.chat_history.setPlaceholderText("Логи системы и ответы ИИ...")
        
        # Загружаем сохраненный шрифт чата
        chat_font = self.settings.value("chat_font_size", 12, type=int)
        self.chat_history.set_custom_font_size(chat_font)
        self.chat_history.zoom_changed.connect(lambda size: self.settings.setValue("chat_font_size", size))
        
        chat_splitter.addWidget(self.chat_history)

        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 5, 0, 0)
        
        # Интегрируем кастомное поле ввода
        self.prompt_input = VibeTextEdit()
        self.prompt_input.setPlaceholderText("Напишите задание...\n(Отправка: Ctrl+Enter, Перенос: Enter, Зум: Ctrl+Колесо мыши)")
        self.prompt_input.send_signal.connect(self.send_task)
        
        # Загружаем сохраненный шрифт ввода
        input_font = self.settings.value("input_font_size", 12, type=int)
        self.prompt_input.set_custom_font_size(input_font)
        self.prompt_input.zoom_changed.connect(lambda size: self.settings.setValue("input_font_size", size))
        
        input_layout.addWidget(self.prompt_input)

        chat_splitter.addWidget(input_container)
        chat_splitter.setSizes([600, 200])
        chat_layout.addWidget(chat_splitter)

        self.splitter.addWidget(chat_widget)
        
        # --- ПАНЕЛЬ 3: Редактор кода + Кнопки управления ---
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(5, 5, 5, 5)
        
        self.editor = DarkPythonEditor()
        editor_layout.addWidget(self.editor)
        
        # НАСТРОЙКА ЗУМА РЕДАКТОРА (QScintilla имеет встроенный зум)
        self.editor_zoom = self.settings.value("editor_zoom", 0, type=int)
        self.editor.zoomTo(self.editor_zoom)
        self.editor.installEventFilter(self) # Перехватываем колесико для сохранения
        
        # ЕДИНАЯ ПАНЕЛЬ КНОПОК
        bottom_btn_layout = QHBoxLayout()
        bottom_btn_layout.setSpacing(5)
        
        self.btn_send = QPushButton("➤ Отправить")
        self.btn_send.setToolTip("Отправить ИИ (Ctrl+Enter)")
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
        self.btn_history.setToolTip("История переписок")
        self.btn_history.setFixedHeight(35)
        self.btn_history.setStyleSheet("background-color: #333333; color: white; font-size: 16px; border-radius: 4px;")
        self.btn_history.clicked.connect(self.show_history)
        
        self.btn_relay = QPushButton("🔄")
        self.btn_relay.setToolTip("Сформировать эстафету")
        self.btn_relay.setFixedHeight(35)
        self.btn_relay.setStyleSheet("background-color: #005f73; color: white; font-size: 16px; border-radius: 4px;")
        self.btn_relay.clicked.connect(self.force_relay)
        
        self.btn_reject_main = QPushButton("❌ Отклонить")
        self.btn_reject_main.setFixedHeight(35)
        self.btn_reject_main.setStyleSheet("background-color: #512525; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_reject_main.setVisible(False)
        self.btn_reject_main.clicked.connect(self.reject_preview)
        
        self.btn_approve = QPushButton("✅ Утвердить код")
        self.btn_approve.setFixedHeight(35)
        self.btn_approve.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; border-radius: 4px;") 
        self.btn_approve.clicked.connect(self.review_and_approve)
        
        bottom_btn_layout.addWidget(self.btn_send, 2)
        bottom_btn_layout.addWidget(self.btn_pause, 2)
        bottom_btn_layout.addWidget(self.btn_history, 1)
        bottom_btn_layout.addWidget(self.btn_relay, 1)
        bottom_btn_layout.addWidget(self.btn_reject_main, 2)
        bottom_btn_layout.addWidget(self.btn_approve, 2)
        
        editor_layout.addLayout(bottom_btn_layout)
        self.splitter.addWidget(editor_widget)
        self.splitter.setSizes([200, 450, 650])
        
        self.current_file_path = None
        self.proposed_updates = [] 
        self.retry_count = 0        
        self.last_sent_prompt = ""  
        self.memory_old_code = None 

    # --- ПЕРЕХВАТ КОЛЕСИКА ДЛЯ РЕДАКТОРА КОДА ---
    def eventFilter(self, obj, event):
        if obj == self.editor and event.type() == QEvent.Type.Wheel:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self.editor_zoom = min(20, self.editor_zoom + 1)
                else:
                    self.editor_zoom = max(-10, self.editor_zoom - 1)
                self.editor.zoomTo(self.editor_zoom)
                self.settings.setValue("editor_zoom", self.editor_zoom) # Сохраняем в память
                return True 
        return super().eventFilter(obj, event)

    # --- ЛОГИКА ---
    def show_popup(self, title, message, is_error=False):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        if is_error: msg.setIcon(QMessageBox.Icon.Critical)
        else: msg.setIcon(QMessageBox.Icon.Information)
        msg.setStyleSheet("QMessageBox { background-color: #252526; color: #d4d4d4; } QLabel { color: #d4d4d4; font-size: 13px; } QPushButton { background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold; }")
        msg.exec()

    def process_limit_reached(self):
        if not self.btn_pause.isChecked():
            self.btn_pause.setChecked(True)
            self.toggle_pause()
        self.log_system("🚨 ЛИМИТЫ GEMINI ИСЧЕРПАНЫ!", color="#ff4444")
        self.show_popup("Лимиты исчерпаны", "Gemini сообщает об исчерпании лимитов.\n\nОткройте другой аккаунт Google или браузер, затем нажмите '▶ Продолжить'.", is_error=True)

    def estimate_tokens(self, text):
        return int(len(text) / 2.5)

    def update_status_bar(self):
        total = self.tokens_sent + self.tokens_received
        self.status_bar.showMessage(f"🟢 Текущая сессия: ~{total:,} токенов | ⬆️ Отправлено: ~{self.tokens_sent:,} | ⬇️ Получено: ~{self.tokens_received:,}")

    def open_file(self, index):
        if self.proposed_updates:
            self.show_popup("Внимание", "Сначала утвердите или отклоните текущие изменения кода!")
            return
        path = self.file_model.filePath(index)
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                self.editor.setText(f.read())
            self.current_file_path = path

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

    def handle_chat_link(self, url: QUrl):
        if url.scheme() == "relay":
            log_id = url.path()
            entry = self.chat_logger.get_by_id(log_id)
            if entry and entry.get("hidden_data"):
                dlg = QDialog(self)
                dlg.setWindowTitle("Текст Эстафеты")
                dlg.resize(600, 400)
                dlg.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
                layout = QVBoxLayout(dlg)
                txt = QTextBrowser()
                txt.setStyleSheet("background-color: #252526; border: none; font-family: Consolas;")
                txt.setPlainText(entry["hidden_data"])
                layout.addWidget(txt)
                dlg.exec()

    def force_relay(self):
        file_content = self.editor.text() if self.current_file_path else ""
        relay_prompt = self.orchestrator.format_request(
            user_prompt="Продолжаем работу. Ожидай следующих указаний.",
            project_path=self.project_path,
            current_file_path=self.current_file_path,
            file_content=file_content
        )
        tokens = self.estimate_tokens(relay_prompt)
        self.tokens_sent += tokens
        self.update_status_bar()
        log_id = self.chat_logger.log("RELAY", "Контекст сформирован для нового чата.", hidden_data=relay_prompt)
        self.chat_history.append(f"<br><div style='background-color: #1a3320; padding: 5px;'><b>[СМЕНА СЕССИИ]</b> Сформирован пакет эстафеты (~{tokens:,} токенов). <a href='relay:{log_id}' style='color: #569cd6;'><b>[Показать текст]</b></a></div>")
        self.scroll_chat()
        self.bridge.add_task(relay_prompt, is_relay=True)
        self.tokens_sent = 0
        self.tokens_received = 0
        self.update_status_bar()

    def log_system(self, text, color="#0e639c"):
        self.chat_logger.log("SYSTEM", text)
        self.chat_history.append(f"<span style='color: {color};'><b>[СИСТЕМА] {text}</b></span>")
        self.scroll_chat()

    def send_task(self):
        user_text = self.prompt_input.toPlainText().strip()
        if not user_text: return
        self.chat_logger.log("USER", user_text)
        self.chat_history.append(f"<br><span style='color: #569cd6;'><b>ВЫ:</b> {user_text}</span>")
        file_content = self.editor.text() if self.current_file_path else ""
        full_prompt = self.orchestrator.format_request(user_prompt=user_text, project_path=self.project_path, current_file_path=self.current_file_path, file_content=file_content)
        self.tokens_sent += self.estimate_tokens(full_prompt)
        self.update_status_bar()
        self.last_sent_prompt = full_prompt
        self.retry_count = 0 
        self.bridge.add_task(full_prompt)
        self.log_system("Задача отправлена. Ожидание ответа...")
        self.prompt_input.clear()
        
    def receive_from_bridge(self, raw_text):
        self.ai_response_signal.emit(raw_text)
        
    def process_ai_response(self, raw_text):
        self.tokens_received += self.estimate_tokens(raw_text)
        self.update_status_bar()
        self.chat_history.append("<span style='color: #bb86fc;'><b>[GEMINI] Ответ получен. Проверка...</b></span>")
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
            fix_prompt = (f"Твой предыдущий ответ вызвал фатальную ошибку: {result['error_message']}\nКАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать извинения вне JSON.\nВот исходная задача. Пришли чистый JSON для неё:\n{self.last_sent_prompt}\n")
            self.bridge.add_task(fix_prompt)
        else:
            self.retry_count = 0 
            data = result["data"]
            thoughts = data.get('thoughts', '')
            self.chat_logger.log("AI", thoughts)
            if thoughts: self.chat_history.append(f"<span style='color: #31a24c;'><b>[МЫСЛИ ИИ]:</b> {thoughts}</span>")
            self.proposed_updates = data.get("updates", [])
            if self.proposed_updates:
                update = self.proposed_updates[0]
                new_code = update.get("code", "")
                rel_path = update.get("file_path", "")
                abs_path = os.path.join(self.project_path, rel_path)
                if self.current_file_path == abs_path:
                    self.memory_old_code = self.editor.text()
                    self.editor.setText(new_code)
                    self.chat_history.append("<span style='color: #ffaa00;'><b>👀 Предпросмотр загружен!</b></span>")
                self.btn_reject_main.setVisible(True)
                self.btn_approve.setText("✅ Ревью (Diff)")
        self.scroll_chat()

    def reject_preview(self):
        if self.memory_old_code is not None:
            self.editor.setText(self.memory_old_code)
            self.memory_old_code = None
        self.proposed_updates = []
        self.btn_reject_main.setVisible(False)
        self.btn_approve.setText("✅ Утвердить код")
        self.log_system("Предпросмотр отклонен.", color="#ff4444")

    def review_and_approve(self):
        if not self.proposed_updates:
            self.show_popup("Пусто", "Нет изменений для утверждения.")
            return
        update = self.proposed_updates[0] 
        rel_path = update.get("file_path", "")
        new_code = update.get("code", "")
        abs_path = os.path.join(self.project_path, rel_path)
        old_code = self.memory_old_code if self.memory_old_code is not None else ""
        if not old_code and os.path.exists(abs_path):
            with open(abs_path, 'r', encoding='utf-8') as f:
                old_code = f.read()
        dialog = DiffDialog(self, old_code, new_code, rel_path)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.file_manager.save_file(abs_path, new_code)
            if self.current_file_path == abs_path: self.editor.setText(new_code)
            self.memory_old_code = None
            self.log_system(f"Изменения в {rel_path} сохранены!", color="#2e7d32")
            self.proposed_updates = []
            self.btn_reject_main.setVisible(False)
            self.btn_approve.setText("✅ Утвердить код")
        else:
            self.reject_preview()

    def scroll_chat(self):
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())