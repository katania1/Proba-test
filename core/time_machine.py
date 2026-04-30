import os
import glob
import difflib
import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QSplitter, 
                             QListWidget, QTextBrowser, QPushButton, QListWidgetItem, QMessageBox)
from PyQt6.QtCore import Qt

class TimeMachineDialog(QDialog):
    def __init__(self, parent, file_path, file_manager):
        super().__init__(parent)
        self.file_path = file_path
        self.file_manager = file_manager
        self.setWindowTitle(f"🕒 Машина Времени: {os.path.basename(file_path)}")
        self.resize(1100, 700)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        self.current_content = ""
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.current_content = f.read()

        self.init_ui()
        self.load_backups()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.backup_list = QListWidget()
        self.backup_list.setStyleSheet("QListWidget { background-color: #252526; border: 1px solid #3c3c3c; font-size: 14px; } QListWidget::item { padding: 10px; border-bottom: 1px solid #333; } QListWidget::item:selected { background-color: #0e639c; }")
        self.backup_list.itemSelectionChanged.connect(self.show_diff)
        
        self.diff_view = QTextBrowser()
        self.diff_view.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3c3c3c; font-family: Consolas; font-size: 13px;")
        
        self.splitter.addWidget(self.backup_list)
        self.splitter.addWidget(self.diff_view)
        self.splitter.setSizes([250, 850])
        layout.addWidget(self.splitter)
        
        btn_layout = QHBoxLayout()
        self.btn_restore = QPushButton("⏪ Восстановить эту версию")
        self.btn_restore.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; padding: 8px 20px; border-radius: 4px; font-size: 14px;")
        self.btn_restore.clicked.connect(self.restore_backup)
        self.btn_restore.setEnabled(False)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_restore)
        layout.addLayout(btn_layout)

    def load_backups(self):
        file_hash = self.file_manager.get_file_hash(self.file_path)
        backup_folder = os.path.join(self.file_manager.history_dir, file_hash)
        
        if not os.path.exists(backup_folder):
            self.diff_view.setHtml("<h2 style='color: #888; text-align: center; margin-top: 50px;'>Нет сохраненных копий для этого файла</h2>")
            return
            
        # Сортируем новые бэкапы сверху
        backups = sorted(glob.glob(os.path.join(backup_folder, "*.bak")), reverse=True)
        
        for backup in backups:
            timestamp = int(os.path.basename(backup).replace(".bak", ""))
            dt = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            
            item = QListWidgetItem(f"🕒 {dt}")
            item.setData(Qt.ItemDataRole.UserRole, backup)
            self.backup_list.addItem(item)
            
        if self.backup_list.count() > 0:
            self.backup_list.setCurrentRow(0)
        else:
            self.diff_view.setHtml("<h2 style='color: #888; text-align: center; margin-top: 50px;'>Нет сохраненных копий для этого файла</h2>")

    def show_diff(self):
        selected = self.backup_list.selectedItems()
        if not selected:
            self.btn_restore.setEnabled(False)
            return
            
        self.btn_restore.setEnabled(True)
        backup_path = selected[0].data(Qt.ItemDataRole.UserRole)
        
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                old_content = f.read()
        except Exception as e:
            self.diff_view.setText(f"Ошибка чтения бэкапа: {e}")
            return

        # HTML-Сравнение. Слева бэкап, справа текущий файл
        d = difflib.HtmlDiff()
        html = d.make_file(old_content.splitlines(), self.current_content.splitlines(), 
                           fromdesc="Старая версия (Бэкап)", todesc="Текущая версия в редакторе", context=True, numlines=5)
        
        html = html.replace('<body>', '<body style="background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas;">')
        html = html.replace('<table class="diff"', '<table class="diff" style="width: 100%; border-collapse: collapse; border: none;"')
        html = html.replace('<td nowrap="nowrap">', '<td style="padding: 2px 10px; font-size: 14px;">')
        html = html.replace('class="diff_add"', 'style="background-color: #2e4a2e; color: #d4d4d4;"')
        html = html.replace('class="diff_chg"', 'style="background-color: #4d4d00; color: #d4d4d4;"')
        html = html.replace('class="diff_sub"', 'style="background-color: #4a2e2e; color: #d4d4d4;"')
        html = html.replace('class="diff_header"', 'style="background-color: #2d2d2d; color: #858585; text-align: right; padding-right: 5px;"')
        
        self.diff_view.setHtml(html)

    def restore_backup(self):
        selected = self.backup_list.selectedItems()
        if not selected: return
        
        backup_path = selected[0].data(Qt.ItemDataRole.UserRole)
        
        reply = QMessageBox.question(self, 'Подтверждение', 
                                     "Вы точно хотите переписать текущий файл этой старой версией?\nТекущая версия будет сохранена в бэкап, вы ничего не потеряете.", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
                                     
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with open(backup_path, 'r', encoding='utf-8') as f:
                    old_content = f.read()
                # Мы передаем контент менеджеру - он сам сделает бэкап текущей версии перед перезаписью!
                self.file_manager.save_file(self.file_path, old_content)
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось восстановить файл: {e}")