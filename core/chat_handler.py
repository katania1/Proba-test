import os
import json
from datetime import datetime
from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QFileDialog, QApplication

class ChatHandler(QObject):
    """
    Менеджер чата и системы логов.
    Управляет историей, ссылками внутри чата и экспортом Debug-пакетов.
    """
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window

    def log_system(self, text, color="#858585", is_bold=False):
        self.mw.chat_logger.log("SYSTEM", text)
        weight = "bold" if is_bold else "normal"
        html_msg = f"<div style='color: {color}; font-weight: {weight}; font-size: 13px; margin-left: 10px;'>[СИСТЕМА] {text}</div>"
        self.mw.chat_history.append(html_msg)
        self.scroll_chat()

    def scroll_chat(self):
        scrollbar = self.mw.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def load_recent_chat_history(self):
        logs = self.mw.chat_logger.get_all()
        if logs:
            self.mw.chat_history.append("<br><span style='color: #888888;'><i>--- История предыдущей сессии (последние 20 сообщений) ---</i></span>")
            for log in logs[-20:]:
                role = log.get("role", "")
                content = log.get("content", "")
                
                if role == "USER":
                    safe_content = content.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
                    self.mw.chat_history.append(f"<br><span style='color: #569cd6;'><b>ВЫ:</b> {safe_content}</span>")
                elif role == "AI":
                    formatted = self.mw.ai_controller.orchestrator.markdown_to_html(content)
                    self.mw.chat_history.append(f"<span style='color: #31a24c;'><b>[МЫСЛИ ИИ]:</b></span>{formatted}")
                elif role == "SYSTEM":
                    self.mw.chat_history.append(f"<div style='color: #858585; font-size: 13px; margin-left: 10px;'>[СИСТЕМА] {content}</div>")
            
            self.mw.chat_history.append("<br><span style='color: #888888;'><i>--- Текущая сессия ---</i></span><br>")
            self.scroll_chat()

    def show_chat_context_menu(self, pos):
        menu = self.mw.chat_history.createStandardContextMenu()
        
        anchor = self.mw.chat_history.anchorAt(pos)
        if anchor.startswith("trace://"):
            trace_id = anchor.replace("trace://", "")
            menu.addSeparator()
            
            act_copy = QAction("📋 Скопировать Debug-пакет для анализа", self.mw)
            act_copy.triggered.connect(lambda: self.export_debug_log(trace_id, to_file=False))
            
            act_save = QAction("💾 Сохранить Debug-пакет как .txt", self.mw)
            act_save.triggered.connect(lambda: self.export_debug_log(trace_id, to_file=True))
            
            menu.addAction(act_copy)
            menu.addAction(act_save)
            
        menu.addSeparator()
        action_clear = menu.addAction("🗑️ Очистить окно чата")
        
        action = menu.exec(self.mw.chat_history.viewport().mapToGlobal(pos))
        if action == action_clear:
            self.mw.chat_history.clear()
            self.log_system("Окно чата очищено (история сохранена в базе данных).")

    def handle_chat_link(self, url: QUrl):
        url_str = url.toString()
        
        # --- Перехват кликов по скрытым логам инспектора ---
        if url_str.startswith("trace://"):
            trace_id = url.host() if url.host() else url_str.replace("trace://", "")
            self.mw.open_inspector(trace_id=trace_id)
            return
            
        if url_str.startswith("copycode://"):
            try:
                block_id = url_str.split("copycode://")[1]
                raw_code = self.mw.ai_controller.orchestrator.code_blocks_memory.get(block_id, "")
                if raw_code:
                    QApplication.clipboard().setText(raw_code)
                    self.log_system("📋 Код успешно скопирован в буфер обмена!", color="#31a24c", is_bold=True)
                else:
                    self.log_system("❌ Ошибка: Код устарел или не найден в памяти сессии.", color="#d32f2f", is_bold=True)
            except Exception as e:
                self.log_system(f"❌ Ошибка копирования кода: {e}", color="#d32f2f", is_bold=True)
            return
        
        if "relay" in url_str:
            entry_id = url.path() if url.scheme() == "relay" else url_str.split(":")[-1]
            entry = self.mw.chat_logger.get_by_id(entry_id)
            if entry and entry.get("hidden_data"):
                self.mw.show_raw_text_dialog("Текст Эстафеты", entry["hidden_data"])

    def export_debug_log(self, trace_id, to_file=True):
        """Собирает Чат + Систему + Трейс в один ультимативный отчет"""
        trace_file = os.path.join(self.mw.project_path, ".vibecoder", "agent_traces.json")
        if not os.path.exists(trace_file):
            self.mw.show_popup("Ошибка экспорта", "Файл с логами агента не найден.", is_error=True)
            return

        try:
            with open(trace_file, 'r', encoding='utf-8') as f:
                traces = json.load(f)
            
            # Ищем нужный лог
            trace_data = next((t for t in traces if t["id"] == trace_id), None)
            if not trace_data:
                self.log_system("❌ Ошибка: Лог сессии не найден в архиве.", color="#ff4444")
                return

            # Формируем документ
            lines = [
                f"=== VIBECODER DEBUG REPORT ===",
                f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Project: {self.mw.project_path}",
                f"Trace ID: {trace_id}",
                f"Engine: {self.mw.get_selected_engine_data().get('model', 'Unknown')}",
                "-" * 40,
                "\n[БЛОК А: КОНТЕКСТ ЧАТА (Последние сообщения)]"
            ]
            
            chat_logs = self.mw.chat_logger.get_all()[-10:]
            for log in chat_logs:
                lines.append(f"[{log['role']}]: {log['content'][:500]}{'...' if len(log['content']) > 500 else ''}")

            lines.append("\n" + "="*40)
            lines.append("[БЛОК Б: СКРЫТЫЙ СЛЕД АГЕНТА (TRACE)]")
            
            for i, step in enumerate(trace_data["steps"], 1):
                lines.append(f"\n--- ШАГ {i}: {step.get('title', 'Unknown')} ---")
                lines.append(step.get("content", ""))

            final_text = "\n".join(lines)

            if to_file:
                file_name, _ = QFileDialog.getSaveFileName(
                    self.mw, "Сохранить лог для анализа", 
                    os.path.expanduser(f"~/Desktop/VibeDebug_{trace_id}.txt"), 
                    "Text Files (*.txt)"
                )
                if file_name:
                    with open(file_name, 'w', encoding='utf-8') as f:
                        f.write(final_text)
                    self.log_system(f"✅ Отладочный лог сохранен: {os.path.basename(file_name)}", color="#31a24c")
            else:
                QApplication.clipboard().setText(final_text)
                self.log_system("📋 Debug-пакет скопирован в буфер обмена.", color="#31a24c")

        except Exception as e:
            self.mw.show_popup("Ошибка экспорта", f"Не удалось собрать пакет: {e}", is_error=True)