import os
import json
import time
import uuid

class ChatLogger:
    def __init__(self, project_path):
        self.project_path = project_path
        self.vibe_dir = os.path.join(self.project_path, '.vibecoder')
        os.makedirs(self.vibe_dir, exist_ok=True)
        
        self.log_file = os.path.join(self.vibe_dir, 'chats.json')
        
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump([], f)

    def log(self, role, content, hidden_data=""):
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "role": role,
            "content": content,
            "hidden_data": hidden_data
        }
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except:
            logs = []
            
        logs.append(entry)
        
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=4, ensure_ascii=False)
            
        return entry["id"]

    def get_by_id(self, log_id):
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
                for log in logs:
                    if log.get("id") == log_id:
                        return log
        except: pass
        return None
        
    def get_all(self):
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return []