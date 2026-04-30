import json
import os
from datetime import datetime

class ChatLogger:
    def __init__(self, project_path):
        self.log_file = os.path.join(project_path, '.vibe_backups', 'chat_history.json')
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump([], f)

    def log(self, role, text, hidden_data=None):
        """
        role: "USER", "AI", "SYSTEM", "RELAY"
        hidden_data: Скрытый текст (например, для эстафеты)
        Возвращает индекс (ID) записи.
        """
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "role": role,
            "text": text,
            "hidden_data": hidden_data
        }
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            data = []
        
        data.append(entry)
        
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        return len(data) - 1 # Возвращаем ID записи

    def get_by_id(self, log_id):
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data[int(log_id)]
        except:
            return None
            
    def get_all(self):
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []