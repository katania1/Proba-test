import os
import json
from datetime import datetime, timedelta

class TraceManager:
    """
    Изолированный сервис управления долгосрочной памятью агента (Инспектор).
    Отвечает за сохранение, загрузку и автоматическую ротацию (TTL 7 дней) логов.
    """
    def __init__(self, project_path):
        self.project_path = project_path
        self.trace_file = os.path.join(self.project_path, ".vibecoder", "agent_traces.json")
        self.current_trace_id = None
        self.agent_trace = []

    def start_new_trace(self, trace_id, initial_title, initial_content):
        """Инициализирует новую сессию трассировки"""
        self.current_trace_id = trace_id
        self.agent_trace = [{"title": initial_title, "content": initial_content}]
        self.save_current_trace()

    def append_step(self, title, content):
        """Добавляет новый шаг в текущую сессию"""
        if not self.current_trace_id:
            return
        self.agent_trace.append({"title": title, "content": content})
        self.save_current_trace()

    def save_current_trace(self, log_callback=None):
        """Сохраняет текущую сессию на диск с очисткой устаревших записей (TTL 7 дней)"""
        if not self.agent_trace or not self.current_trace_id:
            return
            
        os.makedirs(os.path.dirname(self.trace_file), exist_ok=True)
        
        traces = []
        if os.path.exists(self.trace_file):
            try:
                with open(self.trace_file, 'r', encoding='utf-8') as f:
                    traces = json.load(f)
            except Exception:
                pass
        
        # Удаляем предыдущую запись с таким же ID, чтобы перезаписать актуальными данными
        traces = [t for t in traces if t.get("id") != self.current_trace_id]
        
        # Формируем заголовок из содержимого первого шага
        title_text = self.agent_trace[0].get("content", "")
        if "=== ЗАДАЧА ПОЛЬЗОВАТЕЛЯ ===" in title_text:
            title = title_text.split("=== ЗАДАЧА ПОЛЬЗОВАТЕЛЯ ===")[-1].strip()[:100]
        else:
            title = title_text[:100]
        title = title.replace('\n', ' ') + "..."
        
        record = {
            "id": self.current_trace_id,
            "timestamp": datetime.now().isoformat(),
            "title": title,
            "steps": self.agent_trace
        }
        
        traces.append(record)
        
        # Очистка логов старше 7 дней (TTL)
        cutoff = datetime.now() - timedelta(days=7)
        valid_traces = []
        for t in traces:
            try:
                t_date = datetime.fromisoformat(t.get("timestamp", ""))
                if t_date > cutoff:
                    valid_traces.append(t)
            except Exception:
                pass 
                
        try:
            with open(self.trace_file, 'w', encoding='utf-8') as f:
                json.dump(valid_traces, f, ensure_ascii=False, indent=2)
        except Exception as e:
            if log_callback:
                log_callback(f"Ошибка сохранения лога инспектора: {e}", color="#ff4444")