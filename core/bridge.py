import logging
import threading
import time
import uuid
from flask import Flask, request, jsonify


class VibeBridge:
    """
    Транспортный мост (Flask-сервер на порту 5070) для двусторонней связи
    локальной IDE VibeCoder и браузерного расширения Chrome.
    Внедрена строгая сессионная изоляция (server_session_id) для сброса
    фантомных задач в очереди при перезапуске бэкенда.
    """
    def __init__(self):
        self.app = Flask(__name__)
        
        # Отключаем спам в консоли от Flask
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        # Уникальный идентификатор текущей запущенной сессии бэкенда
        self.server_session_id = str(uuid.uuid4())

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
        
        # --- ВИРТУАЛЬНЫЙ БУФЕР ОБМЕНА ---
        self.pending_clipboard_text = ""
        self.pending_clipboard_time = 0
        
        # Коллбэки для интеграции с контроллером IDE
        self.on_result_received = None
        self.on_limit_reached = None
        self.on_log_received = None  
        
        self.is_paused = False
        self.active_tabs = {}

        self._setup_routes()

    def get_active_tabs(self):
        """Возвращает список живых вкладок на основе таймстампов Heartbeat"""
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
            """
            Пассивный Heartbeat: регистрирует вкладку и отдает актуальный ID сессии.
            Не инициирует никаких действий в контроллере.
            """
            data = request.json
            if not data: 
                return jsonify({"status": "ok", "server_session_id": self.server_session_id})
                
            t_id = data.get('tab_id')
            t_name = data.get('tab_name', 'Gemini Tab')
            if t_id:
                with self.lock:
                    self.active_tabs[t_id] = {
                        'name': t_name,
                        'last_seen': time.time()
                    }
            return jsonify({"status": "ok", "server_session_id": self.server_session_id})

        @self.app.route('/get_task', methods=['GET'])
        def get_task():
            """
            Главный эндпоинт раздачи задач.
            Проверяет совпадение сессий: при несовпадении (рестарт бэкенда)
            очищает очередь от фантомных/старых задач.
            """
            if self.is_paused:
                return jsonify({
                    "status": "paused", 
                    "server_session_id": self.server_session_id
                })
                
            client_session_id = request.args.get('session_id', '')
            target_id = request.args.get('target_id')
            
            with self.lock:
                # Если клиент стучится со старым или пустым ID сессии — сбрасываем фантомную очередь
                if client_session_id != self.server_session_id:
                    if self.task_queue:
                        logging.warning(f"Сброс очереди задач при смене сессии. Удалено задач: {len(self.task_queue)}")
                        self.task_queue.clear()
                
                # Поиск целевой задачи для запросившей вкладки
                for i, task in enumerate(self.task_queue):
                    if task.get("target_id") == target_id or not task.get("target_id"):
                        return jsonify({
                            "status": "success", 
                            "task": self.task_queue.pop(i),
                            "server_session_id": self.server_session_id
                        })
                        
            return jsonify({
                "status": "empty", 
                "server_session_id": self.server_session_id
            })

        @self.app.route('/post_result', methods=['POST'])
        def post_result():
            """Прием готового ответа от ИИ и передача в IDE"""
            data = request.json
            if data and "result" in data:
                if self.on_result_received:
                    self.on_result_received(data["result"])
                return jsonify({"status": "success", "server_session_id": self.server_session_id})
            return jsonify({"status": "error"}), 400

        @self.app.route('/limit_reached', methods=['POST'])
        def limit_reached():
            """Уведомление об исчерпании Pro-лимитов"""
            if self.on_limit_reached:
                self.on_limit_reached()
            return jsonify({"status": "success", "server_session_id": self.server_session_id})

        @self.app.route('/log', methods=['POST'])
        def receive_log():
            """
            Пассивный прием системных логов от браузера.
            Исключительно транслирует текст, не вызывая смену состояния бэкенда.
            """
            data = request.json
            if data and "message" in data:
                if self.on_log_received:
                    self.on_log_received(data["message"], data.get("color", ""))
                return jsonify({"status": "success", "server_session_id": self.server_session_id})
            return jsonify({"status": "error"}), 400

        # ---> Отдача виртуального буфера с автоочисткой
        @self.app.route('/get_clipboard', methods=['GET'])
        def get_clipboard():
            with self.lock:
                if self.pending_clipboard_text:
                    # Проверяем, не прошло ли больше 60 секунд
                    if time.time() - self.pending_clipboard_time <= 60:
                        text = self.pending_clipboard_text
                        self.pending_clipboard_text = ""  # Одноразовая отдача (сразу очищаем)
                        return jsonify({
                            "status": "success", 
                            "text": text,
                            "server_session_id": self.server_session_id
                        })
                    else:
                        self.pending_clipboard_text = ""  # Время вышло, сжигаем текст
                return jsonify({
                    "status": "empty",
                    "server_session_id": self.server_session_id
                })

    def set_clipboard(self, text):
        """Метод для сохранения текста в буфер со стороны PyQt"""
        with self.lock:
            self.pending_clipboard_text = text
            self.pending_clipboard_time = time.time()

    def add_task(self, prompt, is_relay=False, target_id=None, images=None):
        """Добавление новой задачи в защищенную потоками очередь"""
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

    # --- НОВЫЙ МЕТОД: Очистка очереди и буфера при Паузе ---
    def clear_queue(self):
        """Полностью очищает очередь задач и виртуальный буфер (предотвращает появление старых сообщений после паузы)"""
        with self.lock:
            if self.task_queue:
                logging.info(f"Очистка очереди задач (удалено {len(self.task_queue)} шт.)")
                self.task_queue.clear()
            
            self.pending_clipboard_text = ""
            self.pending_clipboard_time = 0

    def start_server(self):
        """Фоновый запуск Flask-приложения в отдельном демоническом потоке"""
        thread = threading.Thread(
            target=lambda: self.app.run(host='127.0.0.1', port=5070, debug=False, use_reloader=False), 
            daemon=True
        )
        thread.start()