import os
import re
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser, QLineEdit, QPushButton
from PyQt6.QtCore import QProcess, Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QTextCursor

class TerminalWidget(QWidget):
    # Сигнал для передачи собранной ошибки наверх, в главное окно
    ai_fix_requested = pyqtSignal(str)

    def __init__(self, project_path):
        super().__init__()
        self.project_path = project_path
        self.process = QProcess(self)
        self.command_history = []
        self.history_idx = 0
        
        # Переменные для перехвата ошибок (Фаза 23)
        self.error_buffer = ""
        self.error_timer = QTimer()
        self.error_timer.setSingleShot(True)
        self.error_timer.timeout.connect(self._process_collected_error)
        
        self.init_ui()
        self.init_process()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Окно вывода (только чтение)
        self.output_area = QTextBrowser()
        self.output_area.setStyleSheet("""
            background-color: #1e1e1e; 
            color: #d4d4d4; 
            font-family: Consolas, monospace; 
            font-size: 13px; 
            border: 1px solid #3c3c3c;
            border-bottom: none;
        """)
        
        # Кнопка авто-лечения (по умолчанию скрыта)
        self.btn_fix_error = QPushButton("🩺 Поручить ИИ исправить ошибку")
        self.btn_fix_error.setStyleSheet("""
            background-color: #d32f2f;
            color: white;
            font-weight: bold;
            padding: 8px;
            border-radius: 4px;
            margin: 5px;
        """)
        self.btn_fix_error.setVisible(False)
        self.btn_fix_error.clicked.connect(self._trigger_ai_fix)
        
        # Строка ввода команд
        self.input_line = QLineEdit()
        self.input_line.setStyleSheet("""
            background-color: #252526; 
            color: #d4d4d4; 
            font-family: Consolas, monospace; 
            font-size: 14px; 
            border: 1px solid #3c3c3c; 
            padding: 6px;
        """)
        self.input_line.setPlaceholderText("Команда (например: pip install requests) и Enter... (Стрелки ↑↓ для истории)")
        
        self.input_line.returnPressed.connect(self.send_command)
        self.input_line.installEventFilter(self)

        layout.addWidget(self.output_area)
        layout.addWidget(self.btn_fix_error)
        layout.addWidget(self.input_line)

    def init_process(self):
        """Запускает системный процесс cmd.exe и привязывает потоки данных"""
        self.process.setWorkingDirectory(self.project_path)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)
        
        if os.name == 'nt':
            self.process.start('cmd.exe')
            venv_path = os.path.normpath(os.path.join(self.project_path, 'venv', 'Scripts', 'activate.bat'))
            if os.path.exists(venv_path):
                self.execute_cmd(f'"{venv_path}"')
        else:
            self.process.start('/bin/bash')
            venv_path = os.path.join(self.project_path, 'venv', 'bin', 'activate')
            if os.path.exists(venv_path):
                self.execute_cmd(f'source "{venv_path}"')

    def execute_cmd(self, cmd):
        """Отправляет сырую команду в процесс"""
        if self.process.state() == QProcess.ProcessState.Running:
            if os.name == 'nt':
                try:
                    encoded_cmd = (cmd + '\n').encode('cp866')
                except UnicodeEncodeError:
                    encoded_cmd = (cmd + '\n').encode('utf-8')
            else:
                encoded_cmd = (cmd + '\n').encode('utf-8')
                
            self.process.write(encoded_cmd)

    def send_command(self):
        """Обрабатывает ввод пользователя по нажатию Enter"""
        cmd = self.input_line.text().strip()
        if cmd:
            self.command_history.append(cmd)
            self.history_idx = len(self.command_history)
            
            self.append_text(f'\n<span style="color: #31a24c; font-weight: bold;">> {cmd}</span>\n', is_html=True)
            self.execute_cmd(cmd)
            self.input_line.clear()
            
            # При ручном вводе новой команды прячем кнопку лечения
            self.btn_fix_error.setVisible(False)

    def eventFilter(self, obj, event):
        """Перехватывает нажатия кнопок для истории команд (Вверх/Вниз)"""
        if obj == self.input_line and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Up:
                if self.command_history and self.history_idx > 0:
                    self.history_idx -= 1
                    self.input_line.setText(self.command_history[self.history_idx])
                return True
            elif event.key() == Qt.Key.Key_Down:
                if self.command_history and self.history_idx < len(self.command_history) - 1:
                    self.history_idx += 1
                    self.input_line.setText(self.command_history[self.history_idx])
                else:
                    self.history_idx = len(self.command_history)
                    self.input_line.clear()
                return True
        return super().eventFilter(obj, event)

    def strip_ansi(self, text):
        """Удаляет цветовые ANSI-коды"""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def read_output(self):
        """Читает стандартный вывод (успешные команды)"""
        data = self.process.readAllStandardOutput().data()
        try:
            text = data.decode('cp866') 
        except UnicodeDecodeError:
            text = data.decode('utf-8', errors='replace')
        
        clean_text = self.strip_ansi(text)
        self.append_text(clean_text)
        
        # Если таймер активен, значит ошибка могла просочиться в обычный вывод
        if self.error_timer.isActive():
            self.error_buffer += clean_text
            self.error_timer.start(500) # Продлеваем ожидание конца ошибки

    def read_error(self):
        """Читает вывод ошибок и парсит Traceback"""
        data = self.process.readAllStandardError().data()
        try:
            text = data.decode('cp866')
        except UnicodeDecodeError:
            text = data.decode('utf-8', errors='replace')
            
        clean_text = self.strip_ansi(text)
        self.append_text(f'<span style="color: #ff4444;">{clean_text}</span>', is_html=True)
        
        # АГЕНТНЫЙ ПЕРЕХВАТ: Ищем начало падения скрипта
        if "Traceback" in clean_text or "SyntaxError" in clean_text or "Exception" in clean_text:
            if not self.error_timer.isActive():
                self.error_buffer = "" # Начинаем собирать новую ошибку
            self.error_buffer += clean_text
            self.error_timer.start(500) # Ждем 500мс следующих строк
        elif self.error_timer.isActive():
            self.error_buffer += clean_text
            self.error_timer.start(500)

    def _process_collected_error(self):
        """Срабатывает, когда поток красного текста прекратился на 500мс"""
        if "Traceback" in self.error_buffer or "SyntaxError" in self.error_buffer:
            self.btn_fix_error.setVisible(True)

    def _trigger_ai_fix(self):
        """Пользователь нажал кнопку лечения"""
        self.btn_fix_error.setVisible(False)
        self.ai_fix_requested.emit(self.error_buffer)
        self.error_buffer = "" # Очищаем буфер

    def append_text(self, text, is_html=False):
        """Безопасно добавляет текст в конец логов"""
        cursor = self.output_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_area.setTextCursor(cursor)
        
        if is_html:
             self.output_area.insertHtml(text)
        else:
             self.output_area.insertPlainText(text)
        
        self.output_area.moveCursor(QTextCursor.MoveOperation.End)

    def update_project_path(self, new_path):
        """Перезапускает терминал при смене папки проекта"""
        self.project_path = new_path
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()
            self.process.waitForFinished(1000)
        self.output_area.clear()
        self.append_text(f"🔄 Смена директории на {new_path}...\n")
        self.init_process()