import os
import re
import tempfile
import uuid
from PyQt6.QtWidgets import (QTextEdit, QTextBrowser, QMenu, QWidget, 
                             QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import (QKeyEvent, QWheelEvent, QSyntaxHighlighter, 
                         QTextCharFormat, QColor, QFont, QPixmap, QImage)

# =======================================================
# ПАНЕЛЬ ПРИКРЕПЛЕННЫХ МЕДИА-ФАЙЛОВ (КАРТИНКИ)
# =======================================================
class AttachmentChip(QWidget):
    remove_signal = pyqtSignal(str)

    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)
        self.setStyleSheet("background-color: #333333; border-radius: 4px; border: 1px solid #569cd6;")

        # Миниатюра картинки (или эмодзи, если не загрузилась)
        lbl_icon = QLabel()
        pixmap = QPixmap(self.file_path)
        if not pixmap.isNull():
            lbl_icon.setPixmap(pixmap.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            lbl_icon.setText("🖼️")
        layout.addWidget(lbl_icon)

        # Имя файла с ограничением по длине
        lbl_name = QLabel(os.path.basename(self.file_path))
        lbl_name.setStyleSheet("color: #d4d4d4; border: none; font-size: 11px;")
        font_metrics = lbl_name.fontMetrics()
        elided_text = font_metrics.elidedText(os.path.basename(self.file_path), Qt.TextElideMode.ElideMiddle, 150)
        lbl_name.setText(elided_text)
        lbl_name.setToolTip(self.file_path)
        layout.addWidget(lbl_name)

        # Кнопка удаления
        btn_remove = QPushButton("❌")
        btn_remove.setFixedSize(16, 16)
        btn_remove.setStyleSheet("background: transparent; border: none; color: #ff4444; font-size: 10px; font-weight: bold;")
        btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_remove.clicked.connect(lambda: self.remove_signal.emit(self.file_path))
        layout.addWidget(btn_remove)

class AttachmentPanel(QScrollArea):
    attachments_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.attachments = []
        self.init_ui()

    def init_ui(self):
        self.setFixedHeight(45)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet("QScrollArea { background-color: transparent; border: none; } QScrollBar:horizontal { height: 8px; }")
        
        self.container = QWidget()
        self.container.setStyleSheet("background-color: transparent;")
        self.layout = QHBoxLayout(self.container)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self.layout.addStretch() # Прижимаем элементы влево
        self.setWidget(self.container)
        self.hide() # По умолчанию панель скрыта, пока нет файлов

    def add_attachment(self, file_path):
        if file_path not in self.attachments:
            self.attachments.append(file_path)
            chip = AttachmentChip(file_path)
            chip.remove_signal.connect(self.remove_attachment)
            self.layout.insertWidget(self.layout.count() - 1, chip)
            self.show()
            self.attachments_changed.emit()

    def remove_attachment(self, file_path):
        if file_path in self.attachments:
            self.attachments.remove(file_path)
            for i in range(self.layout.count() - 1):
                widget = self.layout.itemAt(i).widget()
                if isinstance(widget, AttachmentChip) and widget.file_path == file_path:
                    widget.setParent(None)
                    widget.deleteLater()
                    break
            if not self.attachments:
                self.hide()
            self.attachments_changed.emit()
            
    def get_attachments(self):
        return self.attachments
        
    def clear(self):
        self.attachments.clear()
        # Удаляем все виджеты, кроме stretch
        while self.layout.count() > 1:
            widget = self.layout.itemAt(0).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.hide()
        self.attachments_changed.emit()


# =======================================================
# ПОДСВЕТКА СИНТАКСИСА (Поддержка @[...] и тегов)
# =======================================================
class TagHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, attached_files=None):
        super().__init__(parent)
        self.attached_files = attached_files if attached_files is not None else set()
        
        self.mention_format = QTextCharFormat()
        self.mention_format.setForeground(QColor("#569cd6"))
        
        self.attached_format = QTextCharFormat()
        self.attached_format.setForeground(QColor("#31a24c"))
        self.attached_format.setFontWeight(QFont.Weight.Bold)
        
    def highlightBlock(self, text):
        pattern = r'@\[.*?\]|@[\w\.\-\/\\]+'
        for match in re.finditer(pattern, text):
            raw_tag = match.group()
            filename = raw_tag[1:].strip("[]")
            
            start, length = match.start(), match.end() - match.start()
            if filename in self.attached_files:
                self.setFormat(start, length, self.attached_format)
            else:
                self.setFormat(start, length, self.mention_format)

# =======================================================
# КАСТОМНОЕ ПОЛЕ ВВОДА (ЧАТ)
# =======================================================
class VibeTextEdit(QTextEdit):
    send_signal = pyqtSignal()
    zoom_changed = pyqtSignal(int)
    tag_action_signal = pyqtSignal(str, bool)
    media_attached_signal = pyqtSignal(str) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_font_size = 11
        self.setAcceptDrops(True)
        self.project_path = "" 

    def set_custom_font_size(self, size):
        self.current_font_size = size
        self.setStyleSheet(f"background-color: #252526; border: 1px solid #3c3c3c; border-radius: 3px; color: #d4d4d4; font-size: {size}pt;")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.send_signal.emit()
                return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0: self.set_custom_font_size(min(30, self.current_font_size + 1))
            else: self.set_custom_font_size(max(8, self.current_font_size - 1))
            self.zoom_changed.emit(self.current_font_size)
            return
        super().wheelEvent(event)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText() or event.mimeData().hasImage():
            event.acceptProposedAction()

    # --- ПЕРЕХВАТ ВСТАВКИ ИЗ БУФЕРА ОБМЕНА (CTRL+V) ---
    def insertFromMimeData(self, source):
        # 1. Если это сырая картинка (скриншот из ножниц)
        if source.hasImage():
            image = source.imageData()
            if image:
                # Генерируем уникальное имя во временной папке ОС
                temp_dir = tempfile.gettempdir()
                filename = f"vibe_clip_{uuid.uuid4().hex[:8]}.png"
                filepath = os.path.normpath(os.path.join(temp_dir, filename))
                
                # Сохраняем картинку на диск и отправляем в панель
                image.save(filepath, "PNG")
                self.media_attached_signal.emit(filepath)
                return # Прерываем стандартную логику, чтобы картинка не сломала текстовое поле

        # 2. Если скопированы файлы из проводника (URLs)
        elif source.hasUrls():
            self._handle_urls(source.urls())
            return

        # 3. Иначе (обычный текст) используем стандартную вставку
        super().insertFromMimeData(source)

    # --- ПЕРЕХВАТ ПЕРЕТАСКИВАНИЯ (DRAG & DROP) ---
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self._handle_urls(event.mimeData().urls())
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    # Общая логика для файлов (Drag&Drop и Ctrl+V)
    def _handle_urls(self, urls):
        files = []
        for u in urls:
            if u.isLocalFile():
                abs_path = os.path.normpath(u.toLocalFile())
                ext = os.path.splitext(abs_path)[1].lower()
                
                # Если картинка — кидаем сигнал на панель прикреплений
                if ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp']:
                    self.media_attached_signal.emit(abs_path)
                    continue
                
                # Иначе обрабатываем как обычный текстовый файл/код
                if self.project_path:
                    proj_path = os.path.normpath(self.project_path)
                    try:
                        rel_path = os.path.relpath(abs_path, proj_path)
                        if not rel_path.startswith('..') and not os.path.isabs(rel_path):
                            files.append(f"@[{rel_path.replace(os.sep, '/')}]")
                        else:
                            files.append(f"@[{os.path.basename(abs_path)}]")
                    except ValueError:
                        files.append(f"@[{os.path.basename(abs_path)}]")
                else:
                    files.append(f"@[{os.path.basename(abs_path)}]")
                    
        if files:
            self.insertPlainText(" ".join(files) + " ")
            self.setFocus()

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        cursor = self.cursorForPosition(event.pos())
        block_text = cursor.block().text()
        pos_in_block = cursor.positionInBlock()
        
        clicked_tag = None
        for match in re.finditer(r'@\[.*?\]|@[\w\.\-\/\\]+', block_text):
            if match.start() <= pos_in_block <= match.end():
                clicked_tag = match.group()[1:].strip("[]")
                break
                
        if clicked_tag:
            menu.addSeparator()
            if hasattr(self, 'highlighter') and clicked_tag in self.highlighter.attached_files:
                action = menu.addAction(f"❌ Открепить код: {clicked_tag}")
                action.triggered.connect(lambda: self.tag_action_signal.emit(clicked_tag, False))
            else:
                action = menu.addAction(f"📎 Прикрепить код: {clicked_tag}")
                action.triggered.connect(lambda: self.tag_action_signal.emit(clicked_tag, True))
                
        menu.exec(event.globalPos())

# =======================================================
# КАСТОМНОЕ ПОЛЕ ЛОГОВ (ИСТОРИЯ ЧАТА)
# =======================================================
class VibeChatBrowser(QTextBrowser):
    zoom_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_font_size = 11

    def set_custom_font_size(self, size):
        self.current_font_size = size
        self.setStyleSheet(f"background-color: #252526; border: 1px solid #3c3c3c; border-radius: 3px; color: #d4d4d4; font-size: {size}pt;")

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0: self.set_custom_font_size(min(30, self.current_font_size + 1))
            else: self.set_custom_font_size(max(8, self.current_font_size - 1))
            self.zoom_changed.emit(self.current_font_size)
            return
        super().wheelEvent(event)