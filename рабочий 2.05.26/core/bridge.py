from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import logging
import uuid
import time  # <-- НОВЫЙ ИМПОРТ

# Отключаем спам в консоли
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

class VibeBridge:
    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app) 
        
        self.is_paused = False
        self.current_task = None
        self.on_result_received = None 
        self.on_limit_reached = None   
        
        # --- Учет живых вкладок ---
        self.active_tabs = {}
        
        self._setup_routes()

    def _setup_routes(self):
        # --- Обработчик пульса от вкладок ---
        @self.app.route('/ping', methods=['POST', 'OPTIONS'])
        def ping():
            if request.method == 'OPTIONS':
                return '', 204
            data = request.json or {}
            tab_id = data.get('tab_id')
            tab_name = data.get('tab_name', tab_id)
            if tab_id:
                # Записываем время и имя вкладки
                self.active_tabs[tab_id] = {'time': time.time(), 'name': tab_name}
            return jsonify({"status": "ok"})

        @self.app.route('/api/system_state', methods=['GET'])
        def system_state():
            return jsonify({"is_paused": self.is_paused})

        @self.app.route('/api/get_task', methods=['GET'])
        def get_task():
            if not self.current_task:
                return jsonify({"state": "STOPPED"})
                
            # --- Проверка адресата ---
            req_target = request.args.get('target_id')
            task_target = self.current_task.get('target_id')
            
            # Если задача предназначена конкретной вкладке, а пришла другая - не отдаем
            if task_target and req_target and task_target != req_target:
                return jsonify({"state": "RUNNING", "task_id": self.current_task['task_id'], "prompt": None})
                
            if self.current_task['status'] == 'pending':
                self.current_task['status'] = 'processing'
                # Привязываем задачу к вкладке, которая её забрала
                self.current_task['target_id'] = req_target 
                return jsonify({
                    "state": "RUNNING",
                    "task_id": self.current_task['task_id'],
                    "prompt": self.current_task['prompt'],
                    "is_relay": self.current_task.get('is_relay', False)
                })
                
            return jsonify({
                "state": "RUNNING", 
                "task_id": self.current_task['task_id'],
                "prompt": None
            })

        @self.app.route('/api/submit_result', methods=['POST'])
        def submit_result():
            data = request.json
            if self.current_task and self.current_task['task_id'] == data.get('task_id'):
                result_text = data.get('result', '')
                if self.on_result_received:
                    self.on_result_received(result_text)
                self.current_task = None 
            return jsonify({"success": True})

        @self.app.route('/api/limit_reached', methods=['POST'])
        def limit_reached():
            if self.on_limit_reached:
                self.on_limit_reached()
            return jsonify({"success": True})

    # --- Функция для интерфейса UI ---
    def get_active_tabs(self):
        current_time = time.time()
        
        # 🟢 ИСПРАВЛЕНИЕ ПРЫЖКА ЗДЕСЬ: Увеличиваем таймаут с 5 до 12 секунд!
        # Теперь, даже если вкладка намертво "задумается" генерируя ответ,
        # программа подождет 12 секунд, прежде чем сбросить её.
        stale = [t for t, info in self.active_tabs.items() if current_time - info['time'] > 12.0]
        for t in stale:
            del self.active_tabs[t]
            
        # Формируем красивый список для выпадающего меню ("Имя Вкладки [TAB-XXXX]")
        return [f"{info['name']} [{t_id}]" for t_id, info in self.active_tabs.items()]

    def start_server(self):
        server_thread = threading.Thread(target=lambda: self.app.run(
            host='127.0.0.1', 
            port=5070, 
            debug=False, 
            use_reloader=False
        ))
        server_thread.daemon = True
        server_thread.start()

    def add_task(self, prompt, is_relay=False, target_id=None):
        """Добавляет задачу. Если is_relay=True, расширение сначала откроет новый чат"""
        task_id = str(uuid.uuid4())[:8]
        self.current_task = {
            'task_id': task_id,
            'prompt': prompt,
            'status': 'pending',
            'is_relay': is_relay,
            'target_id': target_id  # Адресат задачи
        }