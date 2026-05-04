import os
import json
import sqlite3
import urllib.request
import urllib.parse
import re
import subprocess

class ExternalMCPClient:
    """
    Полноценный клиент Model Context Protocol.
    Общается с внешними серверами (Node.js/Python) через stdio по спецификации JSON-RPC 2.0.
    """
    def __init__(self, command, env=None):
        # shell=True нужен для Windows, чтобы корректно работала команда npx
        self.process = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1
        )
        self.req_id = 1
        
        # --- Обязательный хэндшейк по стандарту MCP ---
        self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "VibeCoder", "version": "1.0"}
        })
        self.send_notification("notifications/initialized")

    def send_request(self, method, params=None):
        req = {"jsonrpc": "2.0", "id": self.req_id, "method": method}
        if params: req["params"] = params
        
        self.process.stdin.write(json.dumps(req) + "\n")
        self.process.stdin.flush()
        
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise Exception(f"MCP сервер разорвал соединение. Ошибка: {self.process.stderr.read()}")
            
            try:
                resp = json.loads(line)
                if "id" in resp and resp["id"] == self.req_id:
                    self.req_id += 1
                    return resp
            except json.JSONDecodeError:
                continue # Пропускаем обычные текстовые логи сервера

    def send_notification(self, method, params=None):
        req = {"jsonrpc": "2.0", "method": method}
        if params: req["params"] = params
        self.process.stdin.write(json.dumps(req) + "\n")
        self.process.stdin.flush()

    def get_tools(self):
        resp = self.send_request("tools/list")
        return resp.get("result", {}).get("tools", [])

    def call_tool(self, name, args):
        resp = self.send_request("tools/call", {
            "name": name,
            "arguments": args
        })
        return resp.get("result", {})

class MCPManager:
    def __init__(self, project_path):
        self.project_path = project_path
        self.external_client = None
        self.external_tools = []
        
        # --- НОВОЕ: Переменные для Светофора (Индикатора здоровья) ---
        self.status = "offline" 
        self.error_message = "MCP не инициализирован"
        
        # ВСТАВЬ СВОЙ КЛЮЧ ОТ CONTEXT7 СЮДА:
        self.context7_api_key = "ctx7sk-53f7a253-a33f-4b82-b243-6eae7aa3a016" 
        
        self._init_external_servers()

        # Наши встроенные (Internal) инструменты
        self.internal_tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Поиск в интернете (DuckDuckGo). Используй для поиска общих статей и новостей.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "description": "Поисковый запрос"}},
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_sql",
                    "description": "Выполняет SQL-запрос (SELECT) к локальной SQLite базе данных проекта.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "db_filename": {"type": "string", "description": "Имя файла базы данных (например: database.db)"},
                            "query": {"type": "string", "description": "SQL запрос (только SELECT)"}
                        },
                        "required": ["db_filename", "query"]
                    }
                }
            }
        ]

    def _init_external_servers(self):
        """Поднимает внешний сервер Context7 и выкачивает его инструменты"""
        if self.context7_api_key and self.context7_api_key != "ТВОЙ_КЛЮЧ_CONTEXT7":
            try:
                env = os.environ.copy()
                env["CONTEXT7_API_KEY"] = self.context7_api_key
                
                # Запускаем официальный пакет Upstash через Node.js
                self.external_client = ExternalMCPClient("npx -y @upstash/context7-mcp", env=env)
                
                # Запрашиваем схему инструментов у запущенного сервера
                c7_tools = self.external_client.get_tools()
                
                # Конвертируем MCP формат в формат OpenAI, который понимает наша нейросеть
                for tool in c7_tools:
                    self.external_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool.get("inputSchema", {})
                        }
                    })
                    
                # --- НОВОЕ: Успешный статус ---
                self.status = "online"
                self.error_message = f"Context7 подключен (Доступно инструментов: {len(c7_tools)})"
                
            except Exception as e:
                # --- НОВОЕ: Статус ошибки ---
                self.status = "error"
                self.error_message = f"Ошибка Context7: {str(e)}"
                print(f"⚠️ {self.error_message}")
        else:
            self.status = "offline"
            self.error_message = "Ключ Context7 не задан. Внешние инструменты отключены."

    def get_tools_schema(self):
        """Возвращает объединенный список: локальные + скачанные с Context7"""
        return self.internal_tools + self.external_tools

    def execute_tool(self, tool_name, kwargs):
        """Маршрутизатор: сам решает, кто должен выполнить команду"""
        try:
            # Сначала проверяем наши локальные инструменты
            if tool_name == "web_search":
                return self._tool_web_search(**kwargs)
            elif tool_name == "execute_sql":
                return self._tool_execute_sql(**kwargs)
                
            # Если это не наш инструмент, перенаправляем команду во внешний MCP сервер
            elif self.external_client:
                result = self.external_client.call_tool(tool_name, kwargs)
                
                # MCP возвращает ответ в виде массива content
                content_blocks = result.get("content", [])
                if content_blocks and content_blocks[0].get("type") == "text":
                    return content_blocks[0].get("text")
                return str(result)
            else:
                return f"Инструмент '{tool_name}' не найден."
        except Exception as e:
            return f"Ошибка выполнения инструмента {tool_name}: {str(e)}"

    # ==========================================
    # РЕАЛИЗАЦИЯ ЛОКАЛЬНЫХ ИНСТРУМЕНТОВ
    # ==========================================

    def _tool_web_search(self, query):
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({'q': query}).encode('utf-8')
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8')
            
            snippets = re.findall(r'class="[^"]*snippet[^"]*"[^>]*>(.*?)</td>', html, re.IGNORECASE | re.DOTALL)
            if not snippets: return "Поиск не дал результатов."
                
            clean_snippets = [re.sub(r'<[^>]+>', '', s).strip() for s in snippets[:4] if s]
            return f"Результаты веб-поиска по '{query}':\n" + "\n---\n".join(clean_snippets)
        except Exception as e:
            return f"Ошибка сети при поиске: {str(e)}"

    def _tool_execute_sql(self, db_filename, query):
        if not query.strip().upper().startswith("SELECT"):
            return "Разрешены только SELECT запросы."
            
        db_path = os.path.join(self.project_path, db_filename)
        if not os.path.exists(db_path):
            return f"Файл базы данных '{db_filename}' не найден."
            
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(query)
            column_names = [description[0] for description in cursor.description]
            rows = cursor.fetchmany(15)
            conn.close()
            
            if not rows: return "Таблица пуста или нет совпадений."
            return "\n".join([f"Колонки: {', '.join(column_names)}"] + [str(row) for row in rows])
        except Exception as e:
            return f"Ошибка SQL запроса: {str(e)}"