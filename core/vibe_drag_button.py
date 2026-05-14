import os
import re
import shutil
import uuid
from pathlib import Path
from PyQt6.QtWidgets import QPushButton, QApplication
from PyQt6.QtCore import Qt, QMimeData, QUrl, QTimer
from PyQt6.QtGui import QDrag, QPixmap

class VibeDragButton(QPushButton):
    """
    Гибридная кнопка отправки v4.2 (Очистка буфера обмена + Сохранение тегов в UI).
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
            log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
            log_func("⚠️ Введите запрос перед перетягиванием!", color="#ffaa00")
            return

        log_func = self.mw.chat_handler.log_system if hasattr(self.mw, 'chat_handler') else self.mw.log_system
        log_func("🚀 Подготовка гибридного пакета (Drag + Paste)...", color="#bb86fc")

        # 1. Формируем контекст (используем исходный текст с тегами для сборщика)
        payload = self.mw.ai_controller.context_builder.build_payload(user_text, is_coding_mode=True, is_browser=True)
        full_prompt = payload["text"]
        image_paths = payload.get("image_paths", [])

        # 2. РЕГИСТРАЦИЯ ЗАДАЧИ И ПОЛУЧЕНИЕ НАСТОЯЩЕГО TRACE_ID
        trace_id = None
        if hasattr(self.mw.ai_controller, 'register_drag_task'):
            # Активируем радар ДО перетаскивания и получаем точный ID лога
            trace_id = self.mw.ai_controller.register_drag_task(full_prompt)

        # 3. ОТОБРАЖЕНИЕ В ЧАТЕ И ЛОГАХ (Сохраняем теги @[...] в интерфейсе программы)
        mode_notice = "⚡ Кодинг (Hybrid Drag)"
        self.mw.chat_logger.log("USER", user_text)
        
        # Строим правильную кликабельную ссылку для контекстного меню логов
        trace_link = f"<a href='trace://{trace_id}' style='color: #569cd6; text-decoration: none;'><b>ВЫ</b></a>" if trace_id else "<b>ВЫ</b>"
        
        self.mw.chat_history.append(f"<br><span style='color: #569cd6;'>{trace_link} [{mode_notice}]: {user_text}</span>")
        
        if hasattr(self.mw, 'chat_handler'):
            self.mw.chat_handler.scroll_chat()
        else:
            self.mw.scroll_chat()
            
        self.mw.tokens_sent += self.mw.ai_controller.estimate_tokens(full_prompt)
        self.mw.update_status_bar()

        # 4. РАЗДЕЛЕНИЕ: В БУФЕР ИДЕТ ОЧИЩЕННЫЙ ТЕКСТ ПОЛЬЗОВАТЕЛЯ (Без тегов @[...])
        clean_clipboard_text = re.sub(r'@\[[^\]]+\]', '', user_text).strip()
        QApplication.clipboard().setText(clean_clipboard_text)

        # 5. ПОДГОТОВКА ФАЙЛОВ ДЛЯ DRAG (Парсим пути из оригинального user_text)
        transit_dir = Path(self.mw.project_path) / ".vibecoder" / "transit"
        transit_dir.mkdir(parents=True, exist_ok=True)
        urls = []
        processed_paths = set()

        # Функция для безопасного добавления уникальных абсолютных путей
        def add_file_url(file_path):
            if not file_path:
                return
            abs_path = file_path if os.path.isabs(file_path) else os.path.join(self.mw.project_path, file_path)
            abs_path = os.path.realpath(abs_path)
            if abs_path not in processed_paths and os.path.exists(abs_path):
                urls.append(QUrl.fromLocalFile(abs_path))
                processed_paths.add(abs_path)

        # А) Картинки из собранного пейлоада
        for img_path in image_paths:
            add_file_url(img_path)

        # Б) Любые прикрепленные файлы из множества UI-состояния
        if hasattr(self.mw, 'attached_files') and self.mw.attached_files:
            for file_tag in self.mw.attached_files:
                add_file_url(file_tag)

        # В) Резервный поиск файлов напрямую по тегам @[...] в исходном тексте запроса
        extracted_tags = re.findall(r'@\[([^\]]+)\]', user_text)
        for tag_path in extracted_tags:
            add_file_url(tag_path.strip())

        # Г) Технический файл с тяжелым контекстом (RAG, деревья)
        context_file = transit_dir / "vibecoder_context.txt"
        context_file.write_text(full_prompt, encoding='utf-8')
        add_file_url(str(context_file))

        # 6. СТАРТ ФИЗИЧЕСКОГО ПЕРЕТАСКИВАНИЯ
        log_func(f"📦 Собрано файлов для Drag: {len(urls)} шт.", color="#bb86fc")
        log_func("📋 Ваш запрос скопирован. Бросьте файлы -> Ctrl+V -> Enter.", color="#31a24c", is_bold=True)

        self.mw.prompt_input.clear()
        
        # Полная очистка визуальной панели и множества/списка вложений
        if hasattr(self.mw, 'attachment_panel'):
            self.mw.attachment_panel.clear()
        if hasattr(self.mw, 'attached_files'):
            self.mw.attached_files.clear()

        drag = QDrag(self)
        mime = QMimeData()
        if urls:
            mime.setUrls(urls)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab().scaled(120, 45, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        result = drag.exec(Qt.DropAction.CopyAction)
        
        # Очистка мусора через 20 секунд
        QTimer.singleShot(20000, lambda: self.cleanup_transit(transit_dir))

    def cleanup_transit(self, transit_dir):
        try:
            if transit_dir.exists():
                shutil.rmtree(transit_dir)
        except Exception:
            pass