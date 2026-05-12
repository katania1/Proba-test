import os
import shutil
import uuid
from pathlib import Path
from PyQt6.QtWidgets import QPushButton, QApplication
from PyQt6.QtCore import Qt, QMimeData, QUrl, QTimer
from PyQt6.QtGui import QDrag, QPixmap

class VibeDragButton(QPushButton):
    """
    Гибридная кнопка отправки v4.0 (Умный Drag + Изоляция контекста).
    Поддерживает перетаскивание абсолютно любых прикрепленных файлов.
    """
    def __init__(self, text, main_window):
        super().__init__(text)
        self.mw = main_window
        self.drag_start_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Клик — Обычная отправка скриптом\nПеретаскивание — Мгновенный Drop файлов + Ctrl+V чистого запроса")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self.drag_start_pos:
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        self.drag_start_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.start_vibe_drag()

    def start_vibe_drag(self):
        user_text = self.mw.prompt_input.toPlainText().strip()
        if not user_text:
            self.mw.chat_handler.log_system("⚠️ Введите запрос перед перетягиванием!", color="#ffaa00")
            return

        # Обращаемся к логгеру через новый фасад (или напрямую, пока ui_main не обновлен)
        log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
        
        log_func("🚀 Сборка гибридного пакета (Drag + Paste)...", color="#bb86fc")

        # 1. Формируем тяжелый контекст (Системный промпт, RAG, дерево)
        payload = self.mw.ai_controller.context_builder.build_payload(user_text, is_coding_mode=True, is_browser=True)
        full_prompt = payload["text"]
        image_paths = payload.get("image_paths", [])

        # 2. ЧИНИМ ССЫЛКУ "ВЫ" И МЕНЮ ЛОГОВ
        trace_id = str(uuid.uuid4())[:12]
        self.mw.ai_controller.current_trace_id = trace_id 
        
        mode_notice = "⚡ Кодинг (Hybrid Drag)"
        self.mw.chat_logger.log("USER", user_text)
        
        # Оборачиваем в гиперссылку для работы ПКМ
        self.mw.chat_history.append(
            f"<br><span style='color: #569cd6;'>"
            f"<a href='trace://{trace_id}' style='color: #569cd6; text-decoration: none;'><b>ВЫ</b></a> "
            f"[{mode_notice}]: {user_text}</span>"
        )
        
        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.scroll_chat()
        else:
            self.mw.scroll_chat()
        
        self.mw.tokens_sent += self.mw.ai_controller.estimate_tokens(full_prompt)
        self.mw.update_status_bar()

        # 3. ИДЕАЛЬНОЕ РАЗДЕЛЕНИЕ "МУХ И КОТЛЕТ"
        # В системный буфер (Ctrl+V) идет ТОЛЬКО чистый запрос (без тяжелого контекста)
        QApplication.clipboard().setText(user_text)

        transit_dir = Path(self.mw.project_path) / ".vibecoder" / "transit"
        transit_dir.mkdir(parents=True, exist_ok=True)
        urls = []

        # А) Добавляем картинки
        for img_path in image_paths:
            if os.path.exists(img_path):
                urls.append(QUrl.fromLocalFile(os.path.realpath(img_path)))
                
        # Б) ДОБАВЛЯЕМ ВСЕ ПРИКРЕПЛЕННЫЕ ФАЙЛЫ (Код, логи, текст)
        for file_tag in self.mw.attached_files:
            abs_path = os.path.join(self.mw.project_path, file_tag)
            if os.path.exists(abs_path):
                urls.append(QUrl.fromLocalFile(os.path.realpath(abs_path)))

        # В) Создаем текстовый дамп тяжелого контекста
        context_file = transit_dir / "vibecoder_context.txt"
        context_file.write_text(full_prompt, encoding='utf-8')
        urls.append(QUrl.fromLocalFile(os.path.realpath(str(context_file))))

        # 4. СТАРТ ПЕРЕТАСКИВАНИЯ
        log_func(f"📦 Собрано файлов для Drag: {len(urls)} шт.", color="#bb86fc")
        log_func("📋 Чистый запрос в буфере. Бросьте файлы -> Ctrl+V -> Enter.", color="#31a24c", is_bold=True)

        drag = QDrag(self)
        mime = QMimeData()
        if urls:
            mime.setUrls(urls)
            
        drag.setMimeData(mime)
        drag.setPixmap(self.grab().scaled(120, 45, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        result = drag.exec(Qt.DropAction.CopyAction)
        
        QTimer.singleShot(20000, lambda: self.cleanup_transit(transit_dir))
        
        if result != Qt.DropAction.IgnoreAction:
            self.mw.prompt_input.clear()
            self.mw.attachment_panel.clear()
            
            # Регистрируем задачу в контроллере для работы Радара
            if hasattr(self.mw.ai_controller, 'register_drag_task'):
                self.mw.ai_controller.register_drag_task(full_prompt)

    def cleanup_transit(self, transit_dir):
        try:
            if transit_dir.exists():
                shutil.rmtree(transit_dir)
        except Exception:
            pass