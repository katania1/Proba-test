import os
import re
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser, QLineEdit
from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtGui import QTextCursor

class TerminalWidget(QWidget):
    def __init__(self, project_path):
        super().__init__()
        self.project_path = project_path
        self.process = QProcess(self)
        self.command_history = []
        self.history_idx = 0
        
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
        layout.addWidget(self.input_line)

    def init_process(self):
        """Запускает системный процесс cmd.exe и привязывает потоки данных"""
        self.process.setWorkingDirectory(self.project_path)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)
        
        # Запускаем консоль Windows
        if os.name == 'nt':
            self.process.start('cmd.exe')
            
            # АВТОМАТИЗАЦИЯ: Ищем venv и активируем его невидимо для пользователя
            # ИСПОЛЬЗУЕМ normpath, ЧТОБЫ ИЗБЕЖАТЬ СМЕСИ / И \ В ПУТЯХ WINDOWS
            venv_path = os.path.normpath(os.path.join(self.project_path, 'venv', 'Scripts', 'activate.bat'))
            if os.path.exists(venv_path):
                self.execute_cmd(f'"{venv_path}"')
        else:
            # Для Linux/Mac (на будущее)
            self.process.start('/bin/bash')
            venv_path = os.path.join(self.project_path, 'venv', 'bin', 'activate')
            if os.path.exists(venv_path):
                self.execute_cmd(f'source "{venv_path}"')

    def execute_cmd(self, cmd):
        """Отправляет сырую команду в процесс"""
        if self.process.state() == QProcess.ProcessState.Running:
            if os.name == 'nt':
                try:
                    # Windows cmd ожидает кириллицу в CP866, а не в UTF-8
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
            
            # Отображаем саму команду в логах (зеленым), чтобы понимать, что мы ввели
            self.append_text(f'\n<span style="color: #31a24c; font-weight: bold;">> {cmd}</span>\n', is_html=True)
            
            self.execute_cmd(cmd)
            self.input_line.clear()

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
        """Удаляет цветовые ANSI-коды, чтобы не было 'мусора' в тексте"""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def read_output(self):
        """Читает стандартный вывод (успешные команды)"""
        data = self.process.readAllStandardOutput().data()
        try:
            text = data.decode('cp866') # Родная кодировка cmd в русской Windows
        except UnicodeDecodeError:
            text = data.decode('utf-8', errors='replace')
        
        clean_text = self.strip_ansi(text)
        self.append_text(clean_text)

    def read_error(self):
        """Читает вывод ошибок"""
        data = self.process.readAllStandardError().data()
        try:
            text = data.decode('cp866')
        except UnicodeDecodeError:
            text = data.decode('utf-8', errors='replace')
            
        clean_text = self.strip_ansi(text)
        self.append_text(f'<span style="color: #ff4444;">{clean_text}</span>', is_html=True)

    def append_text(self, text, is_html=False):
        """Прокручивает окно вниз и безопасно добавляет текст"""
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