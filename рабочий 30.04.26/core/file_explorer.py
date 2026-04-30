import os
import shutil
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTreeView, QMenu, QInputDialog, QMessageBox, QFileDialog)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFileSystemModel

class FileExplorerWidget(QWidget):
    # Сигналы для общения с главным окном
    file_opened = pyqtSignal(str)
    log_message = pyqtSignal(str, str) # text, color
    show_popup_msg = pyqtSignal(str, str, bool) # title, msg, is_error
    project_changed = pyqtSignal(str)
    insert_tags_signal = pyqtSignal(list, bool) # files_list, is_attach

    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # Тулбар файлового менеджера
        file_toolbar = QHBoxLayout()
        file_toolbar.setContentsMargins(0, 0, 0, 0)
        
        self.btn_open_project = QPushButton("📂")
        self.btn_open_project.setObjectName("FileToolBtn")
        self.btn_open_project.setToolTip("Открыть другой проект")
        self.btn_open_project.clicked.connect(self.select_project)
        
        self.btn_new_file = QPushButton("📄")
        self.btn_new_file.setObjectName("FileToolBtn")
        self.btn_new_file.setToolTip("Создать файл")
        self.btn_new_file.clicked.connect(self.create_new_file)
        
        self.btn_new_folder = QPushButton("📁")
        self.btn_new_folder.setObjectName("FileToolBtn")
        self.btn_new_folder.setToolTip("Создать папку")
        self.btn_new_folder.clicked.connect(self.create_new_folder)
        
        self.btn_rename = QPushButton("✏️")
        self.btn_rename.setObjectName("FileToolBtn")
        self.btn_rename.setToolTip("Переименовать")
        self.btn_rename.clicked.connect(self.rename_item)
        
        self.btn_delete = QPushButton("🗑️")
        self.btn_delete.setObjectName("FileToolBtn")
        self.btn_delete.setToolTip("Удалить")
        self.btn_delete.clicked.connect(self.delete_item)

        file_toolbar.addWidget(self.btn_open_project)
        file_toolbar.addSpacing(10)
        file_toolbar.addWidget(self.btn_new_file)
        file_toolbar.addWidget(self.btn_new_folder)
        file_toolbar.addWidget(self.btn_rename)
        file_toolbar.addWidget(self.btn_delete)
        file_toolbar.addStretch()

        layout.addLayout(file_toolbar)

        # Дерево файлов
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(self.project_path)
        
        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_model)
        self.file_tree.setRootIndex(self.file_model.index(self.project_path))
        for i in range(1, 4): self.file_tree.hideColumn(i)
        
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self.file_tree.setDragEnabled(True)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self.tree_context_menu)
        self.file_tree.doubleClicked.connect(self.on_double_click)
        
        layout.addWidget(self.file_tree)

    def select_project(self):
        path = QFileDialog.getExistingDirectory(self, "Выберите папку проекта", self.project_path)
        if path:
            self.project_path = path
            self.file_model.setRootPath(path)
            self.file_tree.setRootIndex(self.file_model.index(path))
            self.project_changed.emit(path)
            self.log_message.emit(f"Проект изменен на: {path}", "#569cd6")

    def tree_context_menu(self, pos):
        indexes = self.file_tree.selectionModel().selectedRows()
        files = [os.path.basename(self.file_model.filePath(i)) for i in indexes if os.path.isfile(self.file_model.filePath(i))]
        if not files: return
        
        menu = QMenu(self)
        act_mention = menu.addAction("💬 Упомянуть файлы в чате")
        act_attach = menu.addAction("📎 Отправить код файлов в чат")
        
        action = menu.exec(self.file_tree.viewport().mapToGlobal(pos))
        if action == act_mention:
            self.insert_tags_signal.emit(files, False)
        elif action == act_attach:
            self.insert_tags_signal.emit(files, True)

    def get_selected_directory(self):
        index = self.file_tree.currentIndex()
        if not index.isValid(): return self.project_path
        path = self.file_model.filePath(index)
        return os.path.dirname(path) if os.path.isfile(path) else path

    def create_new_file(self):
        target_dir = self.get_selected_directory()
        text, ok = QInputDialog.getText(self, "Новый файл", "Имя файла:")
        if ok and text:
            new_file_path = os.path.join(target_dir, text)
            if not os.path.exists(new_file_path):
                open(new_file_path, 'w', encoding='utf-8').close()
                self.log_message.emit(f"Файл создан: {text}", "#31a24c")
                self.file_opened.emit(new_file_path)
            else:
                self.show_popup_msg.emit("Внимание", "Файл уже существует!", True)

    def create_new_folder(self):
        target_dir = self.get_selected_directory()
        text, ok = QInputDialog.getText(self, "Новая папка", "Имя папки:")
        if ok and text:
            new_folder_path = os.path.join(target_dir, text)
            if not os.path.exists(new_folder_path):
                os.makedirs(new_folder_path)
                self.log_message.emit(f"Папка создана: {text}", "#31a24c")
            else:
                self.show_popup_msg.emit("Внимание", "Папка уже существует!", True)

    def rename_item(self):
        index = self.file_tree.currentIndex()
        if not index.isValid(): return
        old_path = self.file_model.filePath(index)
        old_name = os.path.basename(old_path)
        text, ok = QInputDialog.getText(self, "Переименовать", "Новое имя:", text=old_name)
        if ok and text and text != old_name:
            new_path = os.path.join(os.path.dirname(old_path), text)
            os.rename(old_path, new_path)
            self.log_message.emit(f"Переименовано: {old_name} -> {text}", "#0e639c")
            if os.path.isfile(new_path):
                self.file_opened.emit(new_path)

    def delete_item(self):
        index = self.file_tree.currentIndex()
        if not index.isValid(): return
        path = self.file_model.filePath(index)
        name = os.path.basename(path)
        reply = QMessageBox.question(self, 'Удаление', f"Безвозвратно удалить {name}?", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if os.path.isdir(path): shutil.rmtree(path)
            else: os.remove(path)
            self.log_message.emit(f"Удалено: {name}", "#ff4444")
            self.file_opened.emit(f"DELETED:{path}") # Сигнал для очистки редактора

    def on_double_click(self, index):
        path = self.file_model.filePath(index)
        if os.path.isfile(path):
            self.file_opened.emit(path)