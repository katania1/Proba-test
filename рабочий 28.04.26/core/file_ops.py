import os
import shutil
from datetime import datetime

class FileManager:
    def __init__(self, project_path):
        self.project_path = project_path
        self.backup_dir = os.path.join(project_path, '.vibe_backups')
        
        # Создаем скрытую папку для бэкапов, если её нет
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

    def create_backup(self, file_path):
        """Создает копию файла перед его изменением"""
        if not os.path.exists(file_path):
            return # Если файла еще нет (ИИ создает новый), бекапить нечего
            
        # Формируем имя бекапа: папка__файл_дата_время.bak
        rel_path = os.path.relpath(file_path, self.project_path)
        safe_name = rel_path.replace(os.sep, '__')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"{safe_name}_{timestamp}.bak"
        
        backup_path = os.path.join(self.backup_dir, backup_filename)
        
        try:
            shutil.copy2(file_path, backup_path)
            print(f"[Backup] Сохранен: {backup_filename}")
        except Exception as e:
            print(f"[Backup Error] Ошибка создания бэкапа: {e}")

    def save_file(self, file_path, content):
        """Делает бэкап и перезаписывает файл новым кодом"""
        self.create_backup(file_path)
        
        # Убедимся, что папка для файла существует (если ИИ придумал вложенность)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)