import logging
from flask import Flask, request, jsonify
import threading
import time

class VibeBridge:
    def __init__(self):
        self.app = Flask(__name__)
        
        # Отключаем спам в консоли от Flask
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        # === УЛЬТИМАТИВНЫЙ ФИКС CORS и PNA (БЕЗ СТОРОННИХ БИБЛИОТЕК) ===
        @self.app.before_request
        def handle_preflight():
            # Мгновенно и правильно отвечаем на параноидальные проверки Chrome (Preflight)
            if request.method == "OPTIONS":
                res = jsonify({})
                res.headers.add('Access-Control-Allow-Origin', '*')
                res.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, Access-Control-Request-Private-Network')
                res.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                res.headers.add('Access-Control-Allow-Private-Network', 'true')
                return res, 200

        @self.app.after_request
        def add_cors_headers(response):
            # Добавляем правильные заголовки ко всем обычным ответам сервера
            if request.method != "OPTIONS": 
                response.headers.add('Access-Control-Allow-Origin', '*')
                response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
                response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                response.headers.add('Access-Control-Allow-Private-Network', 'true')
            return response

        self.task_queue = []
        self.lock = threading.Lock()
        self.task_counter = 1
        
        self.on_result_received = None
        self.on_limit_reached = None
        
        self.is_paused = False
        self.active_tabs = {}

        self._setup_routes()

    def get_active_tabs(self):
        with self.lock:
            current_time = time.time()
            alive_tabs = []
            keys_to_del = []
            for t_id, info in self.active_tabs.items():
                if current_time - info['last_seen'] < 12: # 12 секунд таймаут для Anti-Jump
                    alive_tabs.append(f"{info['name']} [{t_id}]")
                else:
                    keys_to_del.append(t_id)
            for k in keys_to_del:
                del self.active_tabs[k]
            return alive_tabs

    def _setup_routes(self):
        @self.app.route('/heartbeat', methods=['POST'])
        def heartbeat():
            data = request.json
            if not data: return jsonify({"status": "ok"})
            t_id = data.get('tab_id')
            t_name = data.get('tab_name', 'Gemini Tab')
            if t_id:
                with self.lock:
                    self.active_tabs[t_id] = {
                        'name': t_name,
                        'last_seen': time.time()
                    }
            return jsonify({"status": "ok"})

        @self.app.route('/get_task', methods=['GET'])
        def get_task():
            if self.is_paused:
                return jsonify({"status": "paused"})
                
            target_id = request.args.get('target_id')
            
            with self.lock:
                for i, task in enumerate(self.task_queue):
                    if task.get("target_id") == target_id or not task.get("target_id"):
                        return jsonify({"status": "success", "task": self.task_queue.pop(i)})
            return jsonify({"status": "empty"})

        @self.app.route('/post_result', methods=['POST'])
        def post_result():
            data = request.json
            if data and "result" in data:
                if self.on_result_received:
                    self.on_result_received(data["result"])
                return jsonify({"status": "success"})
            return jsonify({"status": "error"}), 400

        @self.app.route('/limit_reached', methods=['POST'])
        def limit_reached():
            if self.on_limit_reached:
                self.on_limit_reached()
            return jsonify({"status": "success"})

    # ---> ДОБАВЛЕН ПАРАМЕТР IMAGES <---
    def add_task(self, prompt, is_relay=False, target_id=None, images=None):
        with self.lock:
            task = {
                "id": self.task_counter,
                "prompt": prompt,
                "is_relay": is_relay,
                "target_id": target_id,
                "images": images or []
            }
            self.task_queue.append(task)
            self.task_counter += 1

    def start_server(self):
        thread = threading.Thread(target=lambda: self.app.run(host='127.0.0.1', port=5070, debug=False, use_reloader=False), daemon=True)
        thread.start()