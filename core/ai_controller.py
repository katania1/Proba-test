import os
import uuid
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QMessageBox, QApplication

from core.ai_orchestrator import AIOrchestrator
from core.bridge import VibeBridge
from core.mcp_manager import MCPManager
from core.context_builder import ContextBuilder

from core.trace_manager import TraceManager
from core.mcp_handler import MCPHandler
from core.prompt_service import PromptService
from core.file_ops_handler import FileOpsHandler
from core.api_execution_manager import APIExecutionManager


class AIController(QObject):
    ai_response_signal = pyqtSignal(str)
    limit_reached_signal = pyqtSignal()
    bridge_log_signal = pyqtSignal(str, str)

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.orchestrator = AIOrchestrator()
        self.bridge = VibeBridge()
        self.mcp_manager = MCPManager(self.mw.project_path)
        self.context_builder = ContextBuilder(self)

        self.trace_manager = TraceManager(self.mw.project_path)
        self.mcp_handler = MCPHandler(self)
        self.prompt_service = PromptService(self)
        self.file_ops_handler = FileOpsHandler(self)
        self.api_execution_manager = APIExecutionManager(self)

        self.bridge.on_result_received = lambda text: self.ai_response_signal.emit(text)
        self.bridge.on_limit_reached = lambda: self.limit_reached_signal.emit()
        self.bridge.on_log_received = lambda msg, color="": self.bridge_log_signal.emit(msg, color)

        self.ai_response_signal.connect(self.process_ai_response)
        self.limit_reached_signal.connect(self.process_limit_reached)
        self.bridge_log_signal.connect(self.process_bridge_log)

        self.retry_count = 0
        self.is_waiting_for_commit_msg = False
        self.is_waiting_for_relay_msg = False
        self.current_mode_is_chat = False

    @property
    def agent_trace(self):
        return self.trace_manager.agent_trace

    @agent_trace.setter
    def agent_trace(self, value):
        self.trace_manager.agent_trace = value

    @property
    def current_trace_id(self):
        return self.trace_manager.current_trace_id

    @current_trace_id.setter
    def current_trace_id(self, value):
        self.trace_manager.current_trace_id = value

    def process_bridge_log(self, msg, color):
        real_color = color if color else None
        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.log_system(msg, color=real_color)
        else:
            self.mw.log_system(msg, color=real_color)

    def _save_current_trace(self):
        self.trace_manager.save_current_trace(log_callback=self.process_bridge_log)

    def start(self):
        self.bridge.start_server()

    def estimate_tokens(self, text):
        return int(len(text) / 2.5)

    def register_drag_task(self, full_prompt):
        trace_id = str(uuid.uuid4())[:12]
        self.current_trace_id = trace_id 
        self.trace_manager.start_new_trace(trace_id, "Исходный запрос (Hybrid Drag)", full_prompt)
        
        if hasattr(self, '_save_current_trace'):
            self._save_current_trace()

        self.retry_count = 0
        self.mcp_handler.reset_state()
        self.current_mode_is_chat = False
        return trace_id

    def activate_radar(self):
        log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
        log_func("Синхронизация радара. Ожидание ответа ИИ...", color="#858585")
        target = self.mw.get_current_target_id()
        self.bridge.add_task("___RADAR_MODE___", target_id=target, images=[])

    def handle_terminal_error(self, error_text):
        engine_data = self.mw.get_selected_engine_data()
        is_browser = engine_data.get("provider_id", "Browser") == "Browser"

        trace_id = str(uuid.uuid4())[:12]
        self.current_trace_id = trace_id
        self.mw.chat_logger.log("SYSTEM", f"Перехват ошибки терминала:\n{error_text}", trace_id=trace_id)

        ui_alert = self.prompt_service.build_terminal_error_alert(error_text, trace_id)
        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.append_html(ui_alert)
        else:
            self.mw.chat_history.append(ui_alert)

        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.scroll_chat()
        else:
            self.mw.scroll_chat()

        system_text = self.prompt_service.build_terminal_error_prompt(error_text)
        self.mcp_handler.reset_state()
        self.trace_manager.start_new_trace(trace_id, "Перехват ошибки терминала", system_text)

        if is_browser:
            self.mw.last_full_prompt = system_text
            self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
            self.mw.update_status_bar()
            self.retry_count = 0
            self.bridge.add_task(self.mw.last_full_prompt, target_id=self.mw.get_current_target_id(), images=[])
        else:
            self.mw.last_full_prompt = self.orchestrator.format_request(
                user_prompt=system_text, project_path=self.mw.project_path,
                current_file_path=self.mw.current_file_path, file_content=""
            )
            self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
            self.mw.update_status_bar()
            self.retry_count = 0
            self.execute_api_task(engine_data.get("provider_id"), engine_data.get("model"))

    def send_task(self, is_coding_mode=True):
        user_text = self.mw.prompt_input.toPlainText().strip()
        if not user_text:
            return

        trace_id = str(uuid.uuid4())[:12]
        engine_data = self.mw.get_selected_engine_data()
        provider_id = engine_data.get("provider_id", "Browser")
        selected_model = engine_data.get("model", "")
        target_id = self.mw.get_current_target_id()
        is_browser = (provider_id == "Browser")

        try:
            selected_tab = self.mw.status_bar.combo_tabs.currentText()
        except AttributeError:
            selected_tab = "Browser"

        if is_browser and "🔴" in selected_tab:
            self.mw.show_popup("Ошибка связи", "Нет активных вкладок браузера!", is_error=True)
            return

        self.mcp_handler.reset_state()
        self.current_mode_is_chat = not is_coding_mode

        payload = self.context_builder.build_payload(user_text, is_coding_mode, is_browser)
        self.mw.last_full_prompt = payload["text"]
        self.mw.chat_logger.log("USER", user_text, trace_id=trace_id)
        
        tab_display_name = selected_tab.split(" [")[0].replace("🟢 ", "") if is_browser else selected_model
        media_notice = f" <i>(+ {len(payload['image_paths'])} картинки)</i>" if payload['image_paths'] else ""
        mode_notice = "⚡ Кодинг" if is_coding_mode else "💬 Чат"

        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.append_html(f"<span style='color: #569cd6;'><a href='trace://{trace_id}' style='color: #569cd6; text-decoration: none;'><b>ВЫ</b></a> [{mode_notice}] (в <i>{tab_display_name}</i>){media_notice}<b>:</b> {user_text}</span><br>")
        else:
            self.mw.chat_history.append(f"<div style='margin-top: 2px; margin-bottom: 2px;'><span style='color: #569cd6;'><a href='trace://{trace_id}' style='color: #569cd6; text-decoration: none;'><b>ВЫ</b></a> [{mode_notice}] (в <i>{tab_display_name}</i>){media_notice}<b>:</b> {user_text}</span></div>")

        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.scroll_chat()
        else:
            self.mw.scroll_chat()

        self.current_trace_id = trace_id 
        self.trace_manager.start_new_trace(trace_id, f"Исходный запрос ({mode_notice})", self.mw.last_full_prompt)

        self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
        self.mw.update_status_bar()
        self.retry_count = 0
        self.mw.prompt_input.clear()
        self.mw.attachment_panel.clear()

        if is_browser:
            self.bridge.add_task(self.mw.last_full_prompt, is_relay=False, target_id=target_id, images=payload["images"])
            log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
            log_func(f"Задача отправлена во вкладку '{tab_display_name}'. Режим: {mode_notice}.")
        else:
            self.execute_api_task(provider_id, selected_model, payload["image_paths"], payload["api_sys_prompt"])

    def execute_api_task(self, provider_id, selected_model, image_paths=None, sys_prompt=""):
        self.api_execution_manager.execute(provider_id, selected_model, image_paths, sys_prompt)

    def request_ai_commit_message(self, diff_text):
        self.is_waiting_for_commit_msg = True
        prompt = self.prompt_service.build_commit_message_prompt(diff_text)
        log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
        log_func("Запрос ИИ-коммита...")
        log_func("Отправка diff для генерации ИИ-коммита...", color="#673ab7")

        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.scroll_chat()
        else:
            self.mw.scroll_chat()

        engine_data = self.mw.get_selected_engine_data()
        is_browser = engine_data.get("provider_id", "Browser") == "Browser"

        self.mw.last_full_prompt = prompt if is_browser else self.orchestrator.format_request(prompt, project_path=self.mw.project_path, current_file_path=None, file_content="")
        self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
        self.mw.update_status_bar()
        self.retry_count = 0

        if is_browser:
            self.bridge.add_task(self.mw.last_full_prompt, target_id=self.mw.get_current_target_id(), images=[])
        else:
            self.execute_api_task(engine_data.get("provider_id"), engine_data.get("model"), sys_prompt="Ты — профессиональный программист, генерирующий идеальные коммиты.")

    def force_relay(self):
        self.is_waiting_for_relay_msg = True
        prompt = self.prompt_service.build_force_relay_prompt()
        log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
        log_func("Запрос транзитного пакета у ИИ...")
        log_func("Сбор Транзитного Пакета (эстафеты)...", color="#005f73")

        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.scroll_chat()
        else:
            self.mw.scroll_chat()

        self.mw.last_full_prompt = self.orchestrator.format_request(user_prompt=prompt, project_path=self.mw.project_path, current_file_path=self.mw.current_file_path, file_content="")
        self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
        self.mw.update_status_bar()
        self.retry_count = 0
        
        engine_data = self.mw.get_selected_engine_data()
        if engine_data.get("provider_id") == "Browser":
            self.bridge.add_task(self.mw.last_full_prompt, target_id=self.mw.get_current_target_id(), images=[])
        else:
            self.execute_api_task(engine_data.get("provider_id"), engine_data.get("model"), sys_prompt="Ты — координатор проекта. Формируй брифы четко.")

    def send_requested_files(self, file_paths):
        engine_data = self.mw.get_selected_engine_data()
        is_browser = engine_data.get("provider_id", "Browser") == "Browser"

        self.mw.chat_logger.log("SYSTEM", f"Авто-отправка файлов: {', '.join(file_paths)}", trace_id=self.current_trace_id)
        log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
        log_func(f"Автоматически отправлен код: {', '.join(file_paths)}")

        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.scroll_chat()
        else:
            self.mw.scroll_chat()

        system_text = self.prompt_service.build_requested_files_prompt(file_paths)
        self.mw.last_full_prompt = system_text

        if is_browser:
            self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
            self.mw.update_status_bar()
            self.retry_count = 0
            self.bridge.add_task(self.mw.last_full_prompt, target_id=self.mw.get_current_target_id(), images=[])
            log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
            log_func("Текст файлов отправлен в чат. Ожидание ответа...")
        else:
            self.mw.last_full_prompt = self.orchestrator.format_request(user_prompt=system_text, project_path=self.mw.project_path, current_file_path=self.mw.current_file_path, file_content="")
            self.mw.tokens_sent += self.estimate_tokens(self.mw.last_full_prompt)
            self.mw.update_status_bar()
            self.retry_count = 0
            self.execute_api_task(engine_data.get("provider_id"), engine_data.get("model"))

    def process_limit_reached(self):
        if not self.mw.btn_pause.isChecked():
            self.mw.btn_pause.setChecked(True)
            self.mw.toggle_pause()

        log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
        log_func("Внимание: Получен сигнал об изменении лимитов Gemini!", color="#ffaa00")
        msg = QMessageBox(self.mw)
        msg.setWindowTitle("⚠️ Лимиты Gemini Pro")
        msg.setText("Похоже, лимиты продвинутой версии (Pro) исчерпаны, и чат перешел на быструю version (Flash).\n\nЧто делаем дальше?")
        btn_relay = msg.addButton("🔄 Собрать Эстафету", QMessageBox.ButtonRole.AcceptRole)
        btn_continue = msg.addButton("⚡ Продолжить на Flash", QMessageBox.ButtonRole.RejectRole)
        msg.setStyleSheet("QMessageBox { background-color: #252526; color: #d4d4d4; } QLabel { color: #d4d4d4; font-size: 13px; } QPushButton { background-color: #0e639c; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #1177bb; }")
        msg.exec()

        if msg.clickedButton() == btn_relay:
            log_func("Запускаю авто-сборку Транзитного Пакета...", color="#ff4444", is_bold=True)
            self.force_relay()
        else:
            log_func("Продолжаем работу на версии Flash. Будьте внимательны к качеству кода.", color="#31a24c", is_bold=True)
            if self.mw.btn_pause.isChecked():
                self.mw.btn_pause.setChecked(False)
                self.mw.toggle_pause()

    def process_ai_response(self, raw_text):
        if "You've reached your Pro model limit" in raw_text or "Limit resets" in raw_text:
            self.process_limit_reached()
            return

        if self.is_waiting_for_relay_msg:
            self.is_waiting_for_relay_msg = False
            self.retry_count = 0
            self.mw.tokens_received += self.estimate_tokens(raw_text)
            self.mw.update_status_bar()

            ai_summary = self.orchestrator.extract_thoughts_robustly(raw_text)
            if not ai_summary:
                self.mw.show_popup("Ошибка Эстафеты", "ИИ не смог собрать пакет.\nПридется переносить историю вручную.", is_error=True)
                return

            mega_prompt = self.prompt_service.build_relay_mega_prompt(ai_summary)
            clipboard = QApplication.clipboard()
            clipboard.setText(mega_prompt)

            log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
            log_func("Транзитный пакет успешно скопирован в буфер обмена!", color="#31a24c")
            if hasattr(self.mw, 'chat_handler'):
                self.mw.chat_handler.scroll_chat()
            else:
                self.mw.scroll_chat()
            self.mw.show_popup("Эстафета готова!", "Мега-промпт успешно скопирован в буфер обмена!\n\nВставьте его в новый чат Gemini.")
            return

        if self.is_waiting_for_commit_msg:
            self.is_waiting_for_commit_msg = False
            self.retry_count = 0
            self.mw.tokens_received += self.estimate_tokens(raw_text)
            self.mw.update_status_bar()

            commit_msg = self.orchestrator.extract_thoughts_robustly(raw_text)
            if not commit_msg:
                commit_msg = "Автоматический коммит (не удалось распарсить ответ ИИ)"

            safe_msg = commit_msg.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
            if hasattr(self.mw, 'chat_handler'):
                self.mw.chat_handler.append_html(f"<span style='color: #4CAF50;'><b>ИИ-Коммит:</b><br>{safe_msg}</span><br>")
            else:
                self.mw.chat_history.append(f"<div style='margin-top: 2px; margin-bottom: 2px; color: #4CAF50;'><b>ИИ-Коммит:</b><br>{safe_msg}</div>")
                
            self.mw.chat_logger.log("AI", f"Сгенерирован коммит:\n{commit_msg}", trace_id=self.current_trace_id)

            if hasattr(self.mw, 'chat_handler'):
                self.mw.chat_handler.scroll_chat()
            else:
                self.mw.scroll_chat()

            if hasattr(self.mw, 'current_git_dialog') and self.mw.current_git_dialog and self.mw.current_git_dialog.isVisible():
                self.mw.current_git_dialog.text_input.setPlainText(commit_msg)
                self.mw.current_git_dialog.btn_ai.setText("✨ Сгенерировать ИИ-описание")
                self.mw.current_git_dialog.btn_ai.setEnabled(True)
            else:
                self.mw.open_git_dialog(prefill_msg=commit_msg)
            return

        self.mw.tokens_received += self.estimate_tokens(raw_text)
        self.mw.update_status_bar()

        step_suffix = f" (Шаг {self.mcp_handler.browser_mcp_step + 1})" if self.mcp_handler.browser_mcp_step > 0 else ""
        self.trace_manager.append_step(f"Ответ от ИИ{step_suffix}", raw_text)

        if getattr(self, 'current_mode_is_chat', False):
            self.retry_count = 0
            if raw_text.strip():
                self.mw.chat_logger.log("AI", raw_text, trace_id=self.current_trace_id)
                formatted_thoughts = self.orchestrator.markdown_to_html(raw_text.strip())
                if hasattr(self.mw, 'chat_handler'):
                    self.mw.chat_handler.append_html(f"<span style='color: #31a24c;'><b>ОТВЕТ ИИ:</b></span><br>{formatted_thoughts}<br>")
                else:
                    self.mw.chat_history.append(f"<div style='margin-top: 2px; margin-bottom: 2px;'><span style='color: #31a24c;'><b>ОТВЕТ ИИ:</b></span><br>{formatted_thoughts}</div>")
            else:
                if hasattr(self.mw, 'chat_handler'):
                    self.mw.chat_handler.append_html("<span style='color: #ff4444;'><b>ОШИБКА:</b></span> Браузер прислал пустой текст. Gemini изменил дизайн.<br>")
                else:
                    self.mw.chat_history.append("<div style='margin-top: 2px; margin-bottom: 2px;'><span style='color: #ff4444;'><b>ОШИБКА:</b></span> Браузер прислал пустой текст. Gemini изменил дизайн.</div>")
            
            if hasattr(self.mw, 'chat_handler'):
                self.mw.chat_handler.scroll_chat()
            else:
                self.mw.scroll_chat()
            return

        marker = '`' * 3
        clean_result_mcp = raw_text.replace(f'{marker}json', '').replace(marker, '').strip()
        command = self.orchestrator.extract_first_json(clean_result_mcp)

        engine_data = self.mw.get_selected_engine_data()
        is_browser = engine_data.get("provider_id", "Browser") == "Browser"

        if is_browser and command and isinstance(command, dict) and "tool" in command and "updates" not in command:
            self.mcp_handler.handle_tool_command(command)
            return

        result = self.orchestrator.parse_and_validate_response(raw_text)

        if result["status"] == "error":
            self.retry_count += 1
            if self.retry_count > 2:
                log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
                log_func("ИИ не смог выдать правильный JSON. Включена АВТО-ПАУЗА.", color="#ff4444", is_bold=True)
                if not self.mw.btn_pause.isChecked():
                    self.mw.btn_pause.setChecked(True)
                    self.mw.toggle_pause()
                return

            log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
            log_func(f"ОШИБКА ИИ: {result['error_message']}", color="#ff4444", is_bold=True)
            log_func(f"Авто-исправление (Попытка {self.retry_count} из 2)...", color="#ffaa00")

            fix_prompt = self.prompt_service.build_json_fix_prompt(result['error_message'])
            self.trace_manager.append_step(f"Авто-исправление ошибки (Попытка {self.retry_count})", fix_prompt)

            def send_delayed_fix():
                if engine_data.get("provider_id") == "Browser":
                    self.bridge.add_task(fix_prompt, target_id=self.mw.get_current_target_id())
                else:
                    old_prompt = self.mw.last_full_prompt
                    self.mw.last_full_prompt = fix_prompt
                    self.execute_api_task(engine_data.get("provider_id"), engine_data.get("model"))
                    self.mw.last_full_prompt = old_prompt
                if hasattr(self.mw, 'chat_handler'):
                    self.mw.chat_handler.scroll_chat()
                else:
                    self.mw.scroll_chat()

            QTimer.singleShot(2500, send_delayed_fix)
            return
        else:
            self.retry_count = 0
            data = result["data"]
            thoughts = data.get('thoughts', '')
            self.mw.chat_logger.log("AI", thoughts, trace_id=self.current_trace_id)

            if thoughts:
                formatted_thoughts = self.orchestrator.markdown_to_html(thoughts)
                if hasattr(self.mw, 'chat_handler'):
                    self.mw.chat_handler.append_html(f"<span style='color: #31a24c;'><b>МЫСЛИ ИИ:</b></span><br>{formatted_thoughts}<br>")
                else:
                    self.mw.chat_history.append(f"<div style='margin-top: 2px; margin-bottom: 2px;'><span style='color: #31a24c;'><b>МЫСЛИ ИИ:</b></span><br>{formatted_thoughts}</div>")

            requested_files = data.get("request_files", [])
            if requested_files:
                if hasattr(self.mw, 'chat_handler'):
                    self.mw.chat_handler.append_html(f"<span style='color: #e6a822;'><b>ИИ ЗАПРАШИВАЕТ ФАЙЛЫ:</b> {', '.join(requested_files)}</span><br>")
                else:
                    self.mw.chat_history.append(f"<div style='margin-top: 2px; margin-bottom: 2px;'><span style='color: #e6a822;'><b>ИИ ЗАПРАШИВАЕТ ФАЙЛЫ:</b> {', '.join(requested_files)}</span></div>")

                if hasattr(self.mw, 'chat_handler'):
                    self.mw.chat_handler.scroll_chat()
                else:
                    self.mw.scroll_chat()

                from core.request_files_dialog import RequestedFilesDialog
                from PyQt6.QtWidgets import QDialog
                
                dlg = RequestedFilesDialog(self, requested_files, self.mw)
                
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self.send_requested_files(requested_files)
                return

            create_files = data.get("create_files", [])
            if create_files:
                self.file_ops_handler.process_created_files(create_files)

            proposed_updates = data.get("updates", [])
            if proposed_updates:
                valid_updates = self.file_ops_handler.process_proposed_updates(proposed_updates, engine_data)
                
                if valid_updates is None:
                    return

                self.mw.proposed_updates = valid_updates
                if self.mw.proposed_updates:
                    self.mw.btn_reject_main.setVisible(True)
                    self.mw.btn_approve.setText(f"✅ Ревью (Файлов: {len(self.mw.proposed_updates)})")
                    log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
                    log_func(f"ИИ предлагает изменить {len(self.mw.proposed_updates)} файл(а). Жмите Ревью.", color="#31a24c", is_bold=True)

        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.scroll_chat()
        else:
            self.mw.scroll_chat()