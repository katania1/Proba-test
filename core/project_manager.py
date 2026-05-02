import os
import json
from datetime import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QListWidget, QLabel, QFileDialog, QInputDialog, 
                             QMessageBox, QListWidgetItem)
from PyQt6.QtCore import Qt, QSettings

class ProjectManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📂 Менеджер Проектов VibeCoder")
        self.resize(600, 450)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        # --- 100% БРОНЕБОЙНЫЙ ПУТЬ ---
        # Вычисляем путь к папке config относительно этого файла (core/project_manager.py)
        core_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.dirname(core_dir)
        config_dir = os.path.join(app_dir, "config", "VibeCoder")
        os.makedirs(config_dir, exist_ok=True)
        
        self.ini_path = os.path.join(config_dir, "Projects.ini")
        # Жестко заставляем PyQt читать/писать только в этот файл
        self.settings = QSettings(self.ini_path, QSettings.Format.IniFormat)
        
        self.selected_project_path = None
        self.init_ui()
        self.load_projects()

    def init_ui(self):
        layout = QVBoxLayout(self)

        lbl = QLabel("Недавние проекты:")
        lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #569cd6;")
        layout.addWidget(lbl)

        self.project_list = QListWidget()
        self.project_list.setStyleSheet("""
            QListWidget { background-color: #252526; border: 1px solid #3c3c3c; font-size: 14px; outline: none; }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #333333; }
            QListWidget::item:selected { background-color: #0e639c; color: white; border-radius: 4px;}
            QListWidget::item:hover:!selected { background-color: #2a2d2e; }
        """)
        self.project_list.itemDoubleClicked.connect(self.open_selected_project)
        layout.addWidget(self.project_list)

        btn_layout = QHBoxLayout()
        
        self.btn_new = QPushButton("✨ Новый проект")
        self.btn_new.setStyleSheet("background-color: #2e7d32; color: white; padding: 10px; font-weight: bold; border-radius: 4px;")
        self.btn_new.clicked.connect(self.create_new_project)
        
        self.btn_open_exist = QPushButton("📁 Открыть папку")
        self.btn_open_exist.setStyleSheet("background-color: #005f73; color: white; padding: 10px; font-weight: bold; border-radius: 4px;")
        self.btn_open_exist.clicked.connect(self.open_existing_folder)
        
        self.btn_remove = QPushButton("🗑️ Убрать из списка")
        self.btn_remove.setStyleSheet("background-color: #512525; color: white; padding: 10px; font-weight: bold; border-radius: 4px;")
        self.btn_remove.clicked.connect(self.remove_from_list)

        btn_layout.addWidget(self.btn_new)
        btn_layout.addWidget(self.btn_open_exist)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_remove)
        
        layout.addLayout(btn_layout)

    def load_projects(self):
        self.project_list.clear()
        data = self.settings.value("projects", "[]")
        try:
            self.projects = json.loads(data)
        except:
            self.projects = []

        # Сортируем по времени последнего открытия (новые сверху)
        self.projects.sort(key=lambda x: x.get("last_opened", 0), reverse=True)

        for p in self.projects:
            name = p.get("name", "Unknown")
            path = p.get("path", "")
            
            item = QListWidgetItem(f"📂 {name}\n   {path}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.project_list.addItem(item)

    def save_projects(self):
        self.settings.setValue("projects", json.dumps(self.projects))
        self.settings.sync()

    def add_to_history(self, name, path):
        # Проверяем, есть ли уже такой проект в списке
        for p in self.projects:
            if os.path.normpath(p["path"]) == os.path.normpath(path):
                p["last_opened"] = datetime.now().timestamp()
                p["name"] = name # Обновляем имя, если оно поменялось
                self.save_projects()
                return

        # Если нет - добавляем новый
        self.projects.append({
            "name": name,
            "path": os.path.normpath(path),
            "last_opened": datetime.now().timestamp()
        })
        self.save_projects()

    def create_new_project(self):
        name, ok = QInputDialog.getText(self, "Новый проект", "Введите название проекта (оно же имя папки):")
        if not ok or not name.strip(): return
        
        name = name.strip()
        parent_dir = QFileDialog.getExistingDirectory(self, "Выберите директорию, ГДЕ будет создана папка проекта")
        if not parent_dir: return
        
        project_path = os.path.normpath(os.path.join(parent_dir, name))
        
        if os.path.exists(project_path):
            QMessageBox.warning(self, "Ошибка", f"Папка '{name}' уже существует в этой директории!")
            return
            
        try:
            os.makedirs(project_path, exist_ok=True)
            self.add_to_history(name, project_path)
            self.selected_project_path = project_path
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать папку:\n{e}")

    def open_existing_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку проекта")
        if folder:
            folder = os.path.normpath(folder)
            name = os.path.basename(folder)
            self.add_to_history(name, folder)
            self.selected_project_path = folder
            self.accept()

    def open_selected_project(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if not os.path.exists(path):
            QMessageBox.warning(self, "Ошибка", "Папка проекта не найдена. Возможно, она была перемещена или удалена.")
            return
        
        name = os.path.basename(path)
        self.add_to_history(name, path) # Обновляем timestamp
        self.selected_project_path = path
        self.accept()

    def remove_from_list(self):
        selected = self.project_list.selectedItems()
        if not selected: return
        
        path = selected[0].data(Qt.ItemDataRole.UserRole)
        
        reply = QMessageBox.question(self, "Удаление", "Убрать этот проект из недавних?\n(Физически файлы на диске удалены НЕ будут).", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.projects = [p for p in self.projects if os.path.normpath(p["path"]) != os.path.normpath(path)]
            self.save_projects()
            self.load_projects()