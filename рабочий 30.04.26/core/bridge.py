from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import logging
import uuid

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
        
        self._setup_routes()

    def _setup_routes(self):
        @self.app.route('/api/system_state', methods=['GET'])
        def system_state():
            return jsonify({"is_paused": self.is_paused})

        @self.app.route('/api/get_task', methods=['GET'])
        def get_task():
            if not self.current_task:
                return jsonify({"state": "STOPPED"})
                
            if self.current_task['status'] == 'pending':
                self.current_task['status'] = 'processing'
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

    def start_server(self):
        server_thread = threading.Thread(target=lambda: self.app.run(
            host='127.0.0.1', 
            port=5070, 
            debug=False, 
            use_reloader=False
        ))
        server_thread.daemon = True
        server_thread.start()

    def add_task(self, prompt, is_relay=False):
        """Добавляет задачу. Если is_relay=True, расширение сначала откроет новый чат"""
        task_id = str(uuid.uuid4())[:8]
        self.current_task = {
            'task_id': task_id,
            'prompt': prompt,
            'status': 'pending',
            'is_relay': is_relay
        }