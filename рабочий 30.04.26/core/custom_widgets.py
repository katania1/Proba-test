import os
import re
from PyQt6.QtWidgets import QTextEdit, QTextBrowser, QMenu
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (QKeyEvent, QWheelEvent, QSyntaxHighlighter, 
                         QTextCharFormat, QColor, QFont)

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
        pattern = r'@\[.*?\]|@[\w\.\-]+'
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_font_size = 11
        self.setAcceptDrops(True)

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
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            files = []
            for u in event.mimeData().urls():
                if u.isLocalFile():
                    name = os.path.basename(u.toLocalFile())
                    files.append(f"@[{name}]" if " " in name else f"@{name}")
            if files:
                self.insertPlainText(" ".join(files) + " ")
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        cursor = self.cursorForPosition(event.pos())
        block_text = cursor.block().text()
        pos_in_block = cursor.positionInBlock()
        
        clicked_tag = None
        for match in re.finditer(r'@\[.*?\]|@[\w\.\-]+', block_text):
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