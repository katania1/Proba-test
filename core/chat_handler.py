import os
import json
from datetime import datetime
from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtGui import QAction, QTextCursor
from PyQt6.QtWidgets import QFileDialog, QApplication

class ChatHandler(QObject):
    """
    Менеджер чата и системы логов.
    Управляет историей, ссылками внутри чата и экспортом Debug-пакетов.
    """
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window

    def append_html(self, html_msg):
        """Безопасная вставка HTML без создания лишних текстовых блоков (фикс пробелов)"""
        cursor = self.mw.chat_history.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.mw.chat_history.setTextCursor(cursor)
        cursor.insertHtml(html_msg)
        self.scroll_chat()

    def log_system(self, text, color="#858585", is_bold=False):
        self.mw.chat_logger.log("SYSTEM", text)
        weight = "bold" if is_bold else "normal"
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # Используем span и жесткий <br> вместо блочных div, чтобы Qt не добавлял отступы абзацев
        html_msg = f"<span style='color: {color}; font-weight: {weight}; font-size: 0.95em; margin-left: 10px;'><span style='color: #666666;'>[{current_time}]</span> {text}</span><br>"
        self.append_html(html_msg)

    def scroll_chat(self):
        scrollbar = self.mw.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def load_recent_chat_history(self):
        """Загружает историю с восстановлением кликабельных ссылок и таймстемпов"""
        logs = self.mw.chat_logger.get_all()
        if logs:
            self.append_html("<br><span style='color: #888888;'><i>--- История предыдущей сессии (последние 20 сообщений) ---</i></span><br>")
            for log in logs[-20:]:
                role = log.get("role", "")
                content = log.get("content", "")
                trace_id = log.get("trace_id")
                ts = log.get("timestamp")
                
                # Расшифровываем сохраненное время физического действия
                time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else ""
                ts_prefix = f"<span style='color: #666666;'>[{time_str}]</span> " if time_str else ""
                
                if role == "USER":
                    safe_content = content.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
                    trace_link = f"<a href='trace://{trace_id}' style='color: #569cd6; text-decoration: none;'><b>ВЫ</b></a>" if trace_id else "<b>ВЫ</b>"
                    self.append_html(f"<span style='color: #569cd6;'>{ts_prefix}{trace_link}<b>:</b> {safe_content}</span><br>")
                elif role == "AI":
                    formatted = self.mw.ai_controller.orchestrator.markdown_to_html(content)
                    self.append_html(f"<span style='color: #31a24c;'>{ts_prefix}<b>МЫСЛИ ИИ:</b></span><br>{formatted}<br>")
                elif role == "SYSTEM":
                    self.append_html(f"<span style='color: #858585; font-size: 0.95em; margin-left: 10px;'>{ts_prefix}{content}</span><br>")
            
            self.append_html("<br><span style='color: #888888;'><i>--- Текущая сессия ---</i></span><br>")
            self.scroll_chat()

    def show_chat_context_menu(self, pos):
        """Контекстное меню логов с поддержкой одиночного и каскадного экспорта"""
        menu = self.mw.chat_history.createStandardContextMenu()
        
        anchor = self.mw.chat_history.anchorAt(pos)
        if anchor.startswith("trace://"):
            trace_id = anchor.replace("trace://", "")
            menu.addSeparator()
            
            # Раздел одиночного шага
            act_copy_single = QAction("📋 Скопировать только этот шаг (Debug-пакет)", self.mw)
            act_copy_single.triggered.connect(lambda: self.export_debug_log(trace_id, to_file=False, scope="single"))
            
            act_save_single = QAction("💾 Сохранить только этот шаг как .txt", self.mw)
            act_save_single.triggered.connect(lambda: self.export_debug_log(trace_id, to_file=True, scope="single"))
            
            # Раздел каскадной выгрузки (от выбранного места до конца)
            act_copy_cascade = QAction("📋 Скопировать историю (отсюда и до конца)", self.mw)
            act_copy_cascade.triggered.connect(lambda: self.export_debug_log(trace_id, to_file=False, scope="cascade"))
            
            act_save_cascade = QAction("💾 Сохранить историю (отсюда и до конца) как .txt", self.mw)
            act_save_cascade.triggered.connect(lambda: self.export_debug_log(trace_id, to_file=True, scope="cascade"))
            
            menu.addAction(act_copy_single)
            menu.addAction(act_save_single)
            menu.addAction(act_copy_cascade)
            menu.addAction(act_save_cascade)
            
        menu.addSeparator()
        action_clear = menu.addAction("🗑️ Очистить окно чата")
        
        action = menu.exec(self.mw.chat_history.viewport().mapToGlobal(pos))
        if action == action_clear:
            self.mw.chat_history.clear()
            self.log_system("Окно чата очищено (история сохранена в базе данных).")

    def handle_chat_link(self, url: QUrl):
        url_str = url.toString()
        
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
                    self.log_system("Код успешно скопирован в буфер обмена!", color="#31a24c", is_bold=True)
                else:
                    self.log_system("Ошибка: Код устарел или не найден в памяти сессии.", color="#d32f2f", is_bold=True)
            except Exception as e:
                self.log_system(f"Ошибка копирования кода: {e}", color="#d32f2f", is_bold=True)
            return
        
        if "relay" in url_str:
            entry_id = url.path() if url.scheme() == "relay" else url_str.split(":")[-1]
            entry = self.mw.chat_logger.get_by_id(entry_id)
            if entry and entry.get("hidden_data"):
                self.mw.show_raw_text_dialog("Текст Эстафеты", entry["hidden_data"])

    def export_debug_log(self, trace_id, to_file=True, scope="single"):
        """Собирает Чат + Систему + Трейсы (поддерживает точечный шаг и каскадную склейку)"""
        trace_file = os.path.join(self.mw.project_path, ".vibecoder", "agent_traces.json")
        if not os.path.exists(trace_file):
            self.mw.show_popup("Ошибка экспорта", "Файл с логами агента не найден.", is_error=True)
            return

        try:
            with open(trace_file, 'r', encoding='utf-8') as f:
                traces = json.load(f)
            
            # Находим индекс выбранного лога в архиве трассировок
            target_idx = next((i for i, t in enumerate(traces) if t["id"] == trace_id), None)
            if target_idx is None:
                self.log_system("Ошибка: Лог сессии не найден в архиве.", color="#ff4444")
                return

            selected_trace = traces[target_idx]
            selected_ts = selected_trace.get("timestamp", 0)

            # Определяем глубину выгрузки скрытого следа агента
            exported_traces = [selected_trace] if scope == "single" else traces[target_idx:]

            # Формируем документ
            lines = [
                f"=== VIBECODER DEBUG REPORT ===",
                f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Project: {self.mw.project_path}",
                f"Selected Trace ID: {trace_id}",
                f"Export Scope: {scope.upper()}",
                f"Engine: {self.mw.get_selected_engine_data().get('model', 'Unknown')}",
                "-" * 40,
                "\n[БЛОК А: КОНТЕКСТ ЧАТА]"
            ]
            
            chat_logs = self.mw.chat_logger.get_all()
            if scope == "single":
                # Одиночный режим: берем фиксированный срез логов вокруг события
                log_idx = next((i for i, log in enumerate(chat_logs) if log.get("trace_id") == trace_id), None)
                if log_idx is not None:
                    filtered_logs = chat_logs[max(0, log_idx - 5):log_idx + 3]
                else:
                    filtered_logs = chat_logs[-10:]
            else:
                # Каскадный режим: отсекаем всё, что было хронологически до выбранного трейса
                if selected_ts:
                    filtered_logs = [log for log in chat_logs if log.get("timestamp", 0) >= selected_ts - 2]
                else:
                    log_idx = next((i for i, log in enumerate(chat_logs) if log.get("trace_id") == trace_id), None)
                    filtered_logs = chat_logs[log_idx:] if log_idx is not None else chat_logs[-15:]

            for log in filtered_logs:
                role = log.get("role", "")
                content = log.get("content", "")
                ts = log.get("timestamp")
                time_str = f"[{datetime.fromtimestamp(ts).strftime('%H:%M:%S')}] " if ts else ""
                lines.append(f"{time_str}[{role}]: {content}")

            lines.append("\n" + "="*40)
            lines.append("[БЛОК Б: СКРЫТЫЙ СЛЕД АГЕНТА (TRACE)]")
            
            for t_data in exported_traces:
                lines.append(f"\n>>> TRACE ID: {t_data['id']} <<<")
                for i, step in enumerate(t_data.get("steps", []), 1):
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
                    self.log_system(f"Отладочный лог сохранен: {os.path.basename(file_name)}", color="#31a24c")
            else:
                QApplication.clipboard().setText(final_text)
                self.log_system("Debug-пакет скопирован в буфер обмена.", color="#31a24c")

        except Exception as e:
            self.mw.show_popup("Ошибка экспорта", f"Не удалось собрать пакет: {e}", is_error=True)