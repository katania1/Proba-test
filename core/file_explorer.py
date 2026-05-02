import os
import fnmatch
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeView, 
                             QPushButton, QMenu, QInputDialog, QMessageBox, QFileDialog)
from PyQt6.QtCore import Qt, QDir, pyqtSignal, QModelIndex
from PyQt6.QtGui import QFileSystemModel, QColor, QBrush, QAction, QIcon

from core.project_manager import ProjectManagerDialog # Импортируем наш новый менеджер

class GitIgnoreModel(QFileSystemModel):
    def __init__(self, project_path):
        super().__init__()
        self.project_path = project_path
        self.ignore_rules = []
        self.update_rules()

    def update_rules(self):
        self.ignore_rules = []
        gitignore_path = os.path.join(self.project_path, '.gitignore')
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.ignore_rules.append(line.replace('\\', '/'))
        
        self.ignore_rules.extend(['.git/', '.vibecoder/', 'venv/', '__pycache__/'])
        self.layoutChanged.emit()

    def is_ignored(self, file_path):
        if not self.project_path or not file_path.startswith(self.project_path):
            return False
            
        rel_path = os.path.relpath(file_path, self.project_path).replace('\\', '/')
        if rel_path == '.': return False

        is_dir = os.path.isdir(file_path)

        for rule in self.ignore_rules:
            if rule.endswith('/'):
                if is_dir and (rel_path + '/').startswith(rule): return True
                if not is_dir and rel_path.startswith(rule): return True
            elif rule.startswith('*'):
                if fnmatch.fnmatch(rel_path, rule) or fnmatch.fnmatch(os.path.basename(rel_path), rule): return True
            else:
                if rel_path == rule or rel_path.startswith(rule + '/'): return True
                
        return False

    def data(self, index, role):
        if role == Qt.ItemDataRole.ForegroundRole:
            file_path = self.filePath(index)
            if self.is_ignored(file_path):
                return QBrush(QColor("#666666"))
        return super().data(index, role)


class FileExplorerWidget(QWidget):
    file_opened = pyqtSignal(str)
    log_message = pyqtSignal(str)
    show_popup_msg = pyqtSignal(str, str, bool)
    project_changed = pyqtSignal(str)
    insert_tags_signal = pyqtSignal(list, bool)
    open_time_machine_signal = pyqtSignal(str)

    def __init__(self, project_path):
        super().__init__()
        self.project_path = project_path
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- НОВАЯ КНОПКА МЕНЕДЖЕРА ПРОЕКТОВ ---
        self.btn_project_manager = QPushButton(f"📂 {os.path.basename(self.project_path)}")
        self.btn_project_manager.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30;
                color: #d4d4d4;
                font-size: 14px;
                font-weight: bold;
                text-align: left;
                padding: 10px;
                border: none;
                border-bottom: 2px solid #0e639c;
            }
            QPushButton:hover { background-color: #3e3e42; }
        """)
        self.btn_project_manager.clicked.connect(self.open_project_manager)
        layout.addWidget(self.btn_project_manager)
        # ----------------------------------------

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(5, 5, 5, 5)

        self.btn_new_file = QPushButton("📄")
        self.btn_new_file.setToolTip("Создать файл")
        self.btn_new_file.setObjectName("FileToolBtn")
        self.btn_new_file.clicked.connect(self.create_file)

        self.btn_new_folder = QPushButton("📁")
        self.btn_new_folder.setToolTip("Создать папку")
        self.btn_new_folder.setObjectName("FileToolBtn")
        self.btn_new_folder.clicked.connect(self.create_folder)

        self.btn_rename = QPushButton("✏️")
        self.btn_rename.setToolTip("Переименовать")
        self.btn_rename.setObjectName("FileToolBtn")
        self.btn_rename.clicked.connect(self.rename_item)

        self.btn_delete = QPushButton("🗑️")
        self.btn_delete.setToolTip("Удалить")
        self.btn_delete.setObjectName("FileToolBtn")
        self.btn_delete.clicked.connect(self.delete_item)

        toolbar.addWidget(self.btn_new_file)
        toolbar.addWidget(self.btn_new_folder)
        toolbar.addWidget(self.btn_rename)
        toolbar.addWidget(self.btn_delete)
        toolbar.addStretch()

        layout.addLayout(toolbar)

        self.tree = QTreeView()
        self.tree.setStyleSheet("""
            QTreeView { background-color: #1e1e1e; color: #d4d4d4; border: none; font-size: 13px; }
            QTreeView::item:selected { background-color: #37373d; }
            QTreeView::item:hover { background-color: #2a2d2e; }
        """)
        
        self.model = GitIgnoreModel(self.project_path)
        self.model.setRootPath(self.project_path)
        
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(self.project_path))
        self.tree.setHeaderHidden(True)
        self.tree.setColumnHidden(1, True)
        self.tree.setColumnHidden(2, True)
        self.tree.setColumnHidden(3, True)
        self.tree.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self.tree.setDragEnabled(True)

        self.tree.doubleClicked.connect(self.on_double_click)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        layout.addWidget(self.tree)

    def open_project_manager(self):
        dialog = ProjectManagerDialog(self)
        if dialog.exec():
            new_path = dialog.selected_project_path
            if new_path and new_path != self.project_path:
                self.project_path = new_path
                self.model.project_path = new_path
                self.model.setRootPath(new_path)
                self.tree.setRootIndex(self.model.index(new_path))
                self.model.update_rules()
                self.btn_project_manager.setText(f"📂 {os.path.basename(new_path)}")
                self.project_changed.emit(new_path)

    def refresh_ignore_rules(self):
        self.model.update_rules()

    def show_context_menu(self, position):
        indexes = self.tree.selectedIndexes()
        if not indexes:
            return

        index = indexes[0]
        file_path = self.model.filePath(index)
        is_dir = self.model.isDir(index)

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #252526; border: 1px solid #3c3c3c; }
            QMenu::item { color: #e0e0e0; padding: 6px 25px; font-size: 13px; }
            QMenu::item:selected { background-color: #0e639c; color: white; }
            QMenu::separator { height: 1px; background: #3c3c3c; margin: 4px 0; }
        """)
        
        action_attach = menu.addAction("📎 Прикрепить код в чат (Теги)")
        action_time_machine = menu.addAction("🕒 Машина Времени (Откат бэкапов)")
        menu.addSeparator()
        
        if self.model.is_ignored(file_path):
            action_ignore = menu.addAction("✅ Убрать из .gitignore")
            is_ignored_now = True
        else:
            action_ignore = menu.addAction("🚫 Добавить в .gitignore")
            is_ignored_now = False

        action = menu.exec(self.tree.viewport().mapToGlobal(position))

        if action == action_attach:
            files = [self.model.filePath(i) for i in indexes if not self.model.isDir(i)]
            rel_files = [os.path.relpath(f, self.project_path).replace('\\', '/') for f in files]
            if rel_files:
                self.insert_tags_signal.emit(rel_files, True)
                
        elif action == action_time_machine:
            if not is_dir:
                self.open_time_machine_signal.emit(file_path)
            else:
                self.show_popup_msg.emit("Ошибка", "Машина времени работает только для отдельных файлов.", True)
                
        elif action == action_ignore:
            if is_ignored_now:
                self.remove_from_gitignore(file_path)
            else:
                self.add_to_gitignore(file_path)

    def add_to_gitignore(self, file_path):
        rel_path = os.path.relpath(file_path, self.project_path).replace('\\', '/')
        if os.path.isdir(file_path):
            rel_path += '/'
            
        gitignore_path = os.path.join(self.project_path, '.gitignore')
        
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.write(f"{rel_path}\n")
        else:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                content = f.read().splitlines()
            
            if rel_path in content:
                self.show_popup_msg.emit("Информация", f"{rel_path} уже находится в игнор-листе.", False)
                return
                
            with open(gitignore_path, 'a', encoding='utf-8') as f:
                if os.path.getsize(gitignore_path) > 0:
                    f.write('\n')
                f.write(f"{rel_path}\n")
                
        self.model.update_rules()
        self.log_message.emit(f"🚫 {rel_path} добавлен в .gitignore")

    def remove_from_gitignore(self, file_path):
        rel_path = os.path.relpath(file_path, self.project_path).replace('\\', '/')
        if os.path.isdir(file_path):
            rel_path += '/'
            
        gitignore_path = os.path.join(self.project_path, '.gitignore')
        
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.strip() != rel_path:
                        f.write(line)
                        
        self.model.update_rules()
        self.log_message.emit(f"✅ {rel_path} удален из .gitignore")

    def on_double_click(self, index):
        if not self.model.isDir(index):
            file_path = self.model.filePath(index)
            self.file_opened.emit(file_path)

    def create_file(self):
        index = self.tree.currentIndex()
        target_dir = self.project_path
        if index.isValid():
            path = self.model.filePath(index)
            target_dir = path if self.model.isDir(index) else os.path.dirname(path)

        name, ok = QInputDialog.getText(self, "Создать файл", "Имя файла:")
        if ok and name:
            new_path = os.path.join(target_dir, name)
            if not os.path.exists(new_path):
                open(new_path, 'w').close()
                self.file_opened.emit(new_path)
            else:
                self.show_popup_msg.emit("Ошибка", "Файл уже существует!", True)

    def create_folder(self):
        index = self.tree.currentIndex()
        target_dir = self.project_path
        if index.isValid():
            path = self.model.filePath(index)
            target_dir = path if self.model.isDir(index) else os.path.dirname(path)

        name, ok = QInputDialog.getText(self, "Создать папку", "Имя папки:")
        if ok and name:
            new_path = os.path.join(target_dir, name)
            if not os.path.exists(new_path):
                os.makedirs(new_path)
            else:
                self.show_popup_msg.emit("Ошибка", "Папка уже существует!", True)

    def rename_item(self):
        index = self.tree.currentIndex()
        if not index.isValid(): return
        old_path = self.model.filePath(index)
        old_name = os.path.basename(old_path)
        
        new_name, ok = QInputDialog.getText(self, "Переименовать", "Новое имя:", text=old_name)
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            try:
                os.rename(old_path, new_path)
                if not os.path.isdir(new_path):
                    self.file_opened.emit(f"DELETED:{old_path}") 
                    self.file_opened.emit(new_path) 
            except Exception as e:
                self.show_popup_msg.emit("Ошибка", f"Не удалось переименовать:\n{str(e)}", True)

    def delete_item(self):
        index = self.tree.currentIndex()
        if not index.isValid(): return
        path = self.model.filePath(index)
        name = os.path.basename(path)
        
        reply = QMessageBox.question(self, 'Удаление', f"Вы уверены, что хотите удалить '{name}'?\nЭто действие нельзя отменить.", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                import shutil
                if os.path.isdir(path): shutil.rmtree(path)
                else: 
                    os.remove(path)
                    self.file_opened.emit(f"DELETED:{path}")
            except Exception as e:
                self.show_popup_msg.emit("Ошибка", f"Не удалось удалить:\n{str(e)}", True)