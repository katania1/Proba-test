import os
from PyQt6.QtCore import QObject, QFileSystemWatcher, Qt
from PyQt6.QtWidgets import QMessageBox, QDialog
from core.editor import DarkPythonEditor
from core.time_machine import TimeMachineDialog

class EditorManager(QObject):
    """
    Класс-менеджер для управления вкладками редактора и операциями с файлами.
    Инкапсулирует логику открытия, закрытия, сохранения и отслеживания изменений.
    """
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        # Хранилище открытых редакторов {путь: объект_редактора}
        self.opened_editors = {}
        
        # Настройка вотчера для отслеживания изменений файлов другими программами
        self.file_watcher = QFileSystemWatcher(self.mw)
        self.file_watcher.fileChanged.connect(self.handle_external_file_change)

    def open_file(self, path):
        """Открывает файл в новой вкладке или переключается на существующую."""
        if path.startswith("DELETED:"):
            del_path = path.replace("DELETED:", "")
            if self.mw.current_file_path == del_path:
                self.close_tab_by_path(del_path)
            return

        if self.mw.proposed_updates:
            self.mw.show_popup("Внимание", "Сначала утвердите или отклоните текущие изменения кода!")
            return
            
        path = os.path.normpath(path)
        if path in self.opened_editors:
            index = self.mw.editor_tabs.indexOf(self.opened_editors[path])
            self.mw.editor_tabs.setCurrentIndex(index)
            self.mw.current_file_path = path
            return

        if os.path.isfile(path):
            new_editor = DarkPythonEditor()
            zoom = self.mw.settings.value("editor_zoom", 0, type=int)
            new_editor.zoomTo(zoom)
            new_editor.installEventFilter(self.mw)
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    new_editor.setText(f.read())
            except Exception as e:
                self.mw.log_system(f"❌ Ошибка открытия: {e}", color="#ff4444")
                return
            
            # Убираем вкладку-заглушку, если она есть
            if self.mw.editor_tabs.count() == 1 and self.mw.editor_tabs.tabText(0) == "Ничего не открыто":
                 self.mw.editor_tabs.removeTab(0)
                 
            index = self.mw.editor_tabs.addTab(new_editor, f"📄 {os.path.basename(path)}")
            self.mw.editor_tabs.setTabToolTip(index, path)
            self.mw.editor_tabs.setCurrentIndex(index)
            
            self.opened_editors[path] = new_editor
            self.mw.current_file_path = path
            
            # Подключаем сигнал изменения текста для отображения "грязной" вкладки (*)
            new_editor.textChanged.connect(lambda p=path: self.mark_tab_dirty(p))
            
            if path not in self.file_watcher.files():
                self.file_watcher.addPath(path)

    def close_tab(self, index):
        """Закрывает вкладку и удаляет путь из отслеживания watcher'ом."""
        widget = self.mw.editor_tabs.widget(index)
        path_to_remove = next((p for p, ed in self.opened_editors.items() if ed == widget), None)
        
        if path_to_remove:
            if path_to_remove in self.file_watcher.files():
                self.file_watcher.removePath(path_to_remove)
            del self.opened_editors[path_to_remove]
            
        self.mw.editor_tabs.removeTab(index)
        
        if self.mw.editor_tabs.count() == 0:
            self.mw.current_file_path = None
            self.mw.editor_tabs.addTab(DarkPythonEditor(), "Ничего не открыто")

    def close_tab_by_path(self, path):
        if path in self.opened_editors:
            index = self.mw.editor_tabs.indexOf(self.opened_editors[path])
            self.close_tab(index)

    def mark_tab_dirty(self, path):
        """Добавляет символ '*' к названию вкладки при несохраненных изменениях."""
        if path in self.opened_editors:
            index = self.mw.editor_tabs.indexOf(self.opened_editors[path])
            current_text = self.mw.editor_tabs.tabText(index)
            if not current_text.startswith('*'):
                self.mw.editor_tabs.setTabText(index, '*' + current_text)

    def clear_dirty_mark(self, path):
        """Убирает символ '*' после сохранения файла."""
        if path in self.opened_editors:
            index = self.mw.editor_tabs.indexOf(self.opened_editors[path])
            text = self.mw.editor_tabs.tabText(index)
            if text.startswith('*'):
                self.mw.editor_tabs.setTabText(index, text[1:])

    def open_time_machine(self, file_path):
        """Вызывает диалог 'Машины времени' для восстановления версий."""
        dialog = TimeMachineDialog(self.mw, file_path, self.mw.file_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.mw.log_system(f"Файл {os.path.basename(file_path)} успешно откатан!", color="#d32f2f", is_bold=True)
            if self.mw.current_file_path == file_path:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.opened_editors[file_path].setText(f.read())
            self.mw.update_git_status()

    def handle_external_file_change(self, path):
        """Обработка изменения открытого файла другой программой (например, через Git)."""
        if path in self.opened_editors:
            editor = self.opened_editors[path]
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    disk_content = f.read()
                if editor.text() == disk_content:
                    return
            except Exception:
                return

            msg = QMessageBox(self.mw)
            msg.setWindowTitle('⚠️ Файл изменен извне')
            msg.setText(f'Файл <b>{os.path.basename(path)}</b> был изменен другой программой.<br><br>Перезагрузить его?')
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setStyleSheet("""
                QMessageBox { background-color: #252526; color: #d4d4d4; } 
                QLabel { color: #d4d4d4; font-size: 13px; } 
                QPushButton { background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold; } 
            """)
            
            if msg.exec() == QMessageBox.StandardButton.Yes:
                editor.setText(disk_content)
                self.clear_dirty_mark(path)

    def nav_undo(self):
        """Отмена действия в активном редакторе."""
        editor = self.mw.editor
        if editor: editor.undo()

    def nav_redo(self):
        """Повтор действия в активном редакторе."""
        editor = self.mw.editor
        if editor: editor.redo()

    def get_editor_by_path(self, path):
        return self.opened_editors.get(path)

    def get_all_opened_paths(self):
        return list(self.opened_editors.keys())