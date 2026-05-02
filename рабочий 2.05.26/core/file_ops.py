import os
import time
import glob
import hashlib

class FileManager:
    def __init__(self, project_path):
        self.project_path = project_path
        # Создаем директорию .vibecoder для хранения локальных данных проекта
        self.vibe_dir = os.path.join(self.project_path, '.vibecoder')
        self.history_dir = os.path.join(self.vibe_dir, 'local_history')
        os.makedirs(self.history_dir, exist_ok=True)

    def get_file_hash(self, file_path):
        """Создает уникальное имя папки для бэкапов конкретного файла на основе его пути"""
        rel_path = os.path.relpath(file_path, self.project_path)
        return hashlib.md5(rel_path.encode('utf-8')).hexdigest()

    def save_file(self, file_path, new_content):
        # Если файла нет, просто создаем
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return

        # Если файл есть, читаем старый контент
        with open(file_path, 'r', encoding='utf-8') as f:
            old_content = f.read()

        # Если контент изменился, делаем бэкап перед сохранением
        if old_content != new_content:
            self._create_backup(file_path, old_content)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

    def _create_backup(self, file_path, content):
        file_hash = self.get_file_hash(file_path)
        backup_folder = os.path.join(self.history_dir, file_hash)
        os.makedirs(backup_folder, exist_ok=True)

        timestamp = int(time.time())
        backup_file = os.path.join(backup_folder, f"{timestamp}.bak")
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)

        # ЖЕСТКИЙ ЛИМИТ: 10 СТУПЕНЕЙ БЭКАПА
        backups = sorted(glob.glob(os.path.join(backup_folder, "*.bak")))
        if len(backups) > 10:
            for old_backup in backups[:-10]: # Удаляем все, что старше 10 последних
                try: os.remove(old_backup)
                except: pass