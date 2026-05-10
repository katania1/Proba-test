from PyQt6.Qsci import QsciScintilla, QsciLexerPython
from PyQt6.QtGui import QColor, QFont, QGuiApplication
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton

class SearchPanel(QWidget):
    """Плавающая панель поиска по коду в стиле VS Code"""
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        
        self.setStyleSheet("""
            SearchPanel {
                background-color: #2d2d30; 
                border: 2px solid #0e639c; 
                border-radius: 6px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e; 
                color: #ffffff; 
                border: 1px solid #555555; 
                border-radius: 3px; 
                padding: 6px 8px; 
                font-family: 'Consolas', 'Segoe UI'; 
                font-size: 15px;
                font-weight: bold;
            }
        """)
        self.search_input.setPlaceholderText("Найти...")
        self.search_input.setMinimumWidth(320)
        self.search_input.setMinimumHeight(32)

        self.btn_prev = QPushButton("Вверх")
        self.btn_next = QPushButton("Вниз")
        self.btn_close = QPushButton("X")

        btn_style = """
            QPushButton { 
                background-color: #3c3c3c; 
                color: #ffffff; 
                border: 1px solid #555555; 
                border-radius: 3px; 
                font-size: 13px;
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton:hover { background-color: #505050; border-color: #0e639c; }
            QPushButton:pressed { background-color: #0e639c; }
        """
        
        for btn in [self.btn_prev, self.btn_next, self.btn_close]:
            btn.setStyleSheet(btn_style)
            btn.setMinimumHeight(30)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.btn_close.setFixedWidth(35)
        self.btn_close.setStyleSheet(btn_style.replace("#0e639c", "#d32f2f"))

        layout.addWidget(self.search_input)
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_close)

        self.hide()

        self.search_input.textChanged.connect(self.on_text_changed)
        self.search_input.returnPressed.connect(self.on_return_pressed)
        self.btn_next.clicked.connect(self.find_next)
        self.btn_prev.clicked.connect(self.find_prev)
        self.btn_close.clicked.connect(self.hide_panel)

    def on_return_pressed(self):
        if QGuiApplication.keyboardModifiers() == Qt.KeyboardModifier.ShiftModifier:
            self.find_prev()
        else:
            self.find_next()

    def toggle_panel(self):
        if self.isVisible(): self.hide_panel()
        else: self.show_panel()

    def show_panel(self):
        self.show()
        self.raise_()
        selected_text = self.editor.selectedText()
        if selected_text and '\n' not in selected_text:
            self.search_input.setText(selected_text)
        self.search_input.setFocus()
        self.search_input.selectAll()
        self.update_position()

    def hide_panel(self):
        self.hide()
        self.editor.setFocus()

    def update_position(self):
        self.move(self.editor.width() - self.width() - 30, 15)

    def on_text_changed(self, text):
        if text: self.editor.findFirst(text, False, False, False, True, True, 0, 0, True, False)

    def do_search(self, forward=True):
        text = self.search_input.text()
        if not text: return
        line, index = self.editor.getCursorPosition()
        if self.editor.hasSelectedText():
            ls, ids, le, ide = self.editor.getSelection()
            line, index = (le, ide) if forward else (ls, ids)
        self.editor.findFirst(text, False, False, False, True, forward, line, index, True, False)

    def find_next(self): self.do_search(forward=True)
    def find_prev(self): self.do_search(forward=False)


class DarkPythonEditor(QsciScintilla):
    def __init__(self):
        super().__init__()
        
        self.setUtf8(True)
        self.setEolMode(QsciScintilla.EolMode.EolUnix) 
        
        font = QFont("Consolas", 11)
        self.setFont(font)
        self.setMarginsFont(font)
        
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setIndentationWidth(4)
        
        self.setIndentationGuides(True)
        self.SendScintilla(2132, 3) 
        self.setIndentationGuidesForegroundColor(QColor("#707070"))
        
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "00000") 
        self.setMarginsBackgroundColor(QColor("#252526"))
        self.setMarginsForegroundColor(QColor("#858585"))
        self.setMarginWidth(1, 0)
        
        try:
            self.setFolding(QsciScintilla.FoldStyle.BoxedTreeFoldStyle)
        except AttributeError:
            self.setFolding(2)
            
        self.setMarginType(2, QsciScintilla.MarginType.SymbolMargin)
        self.setMarginSensitivity(2, True)
        self.setMarginWidth(2, 20)
        self.setFoldMarginColors(QColor("#252526"), QColor("#252526"))
        
        self.SendScintilla(2162, 16 | 32 | 64) 
        self.SendScintilla(2163, 0)
        
        fold_fg = QColor("#d4d4d4")    
        margin_bg = QColor("#252526")  
        box_bg = QColor("#1e1e1e")     
        
        for m in range(25, 32):
            self.setMarkerForegroundColor(fold_fg, m)
            self.setMarkerBackgroundColor(margin_bg, m)
            
        boxes = [
            QsciScintilla.SC_MARKNUM_FOLDER,
            QsciScintilla.SC_MARKNUM_FOLDEROPEN,
            QsciScintilla.SC_MARKNUM_FOLDEREND,
            QsciScintilla.SC_MARKNUM_FOLDEROPENMID
        ]
        for m in boxes:
            self.setMarkerBackgroundColor(box_bg, m)
        
        self.setPaper(QColor("#1e1e1e"))
        self.setCaretForegroundColor(QColor("#d4d4d4"))
        self.setCaretLineVisible(True) 
        self.setCaretLineBackgroundColor(QColor("#2a2d2e"))
        
        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)
        self.setMatchedBraceBackgroundColor(QColor("#3c3c3c"))
        self.setMatchedBraceForegroundColor(QColor("#569cd6"))
        self.setUnmatchedBraceBackgroundColor(QColor("#252526"))
        self.setUnmatchedBraceForegroundColor(QColor("#ff4444"))
        
        self.lexer = QsciLexerPython(self)
        self.lexer.setDefaultFont(font)
        self.lexer.setDefaultPaper(QColor("#1e1e1e"))
        
        self.lexer.setColor(QColor("#569cd6"), QsciLexerPython.Keyword)
        self.lexer.setColor(QColor("#4EC9B0"), QsciLexerPython.ClassName)
        self.lexer.setColor(QColor("#DCDCAA"), QsciLexerPython.FunctionMethodName)
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.SingleQuotedString)
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.DoubleQuotedString)
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.TripleSingleQuotedString)
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.TripleDoubleQuotedString)
        self.lexer.setColor(QColor("#6A9955"), QsciLexerPython.Comment)
        self.lexer.setColor(QColor("#b5cea8"), QsciLexerPython.Number)
        self.lexer.setColor(QColor("#d4d4d4"), QsciLexerPython.Identifier)
        self.lexer.setColor(QColor("#d4d4d4"), QsciLexerPython.Operator)
        
        self.setLexer(self.lexer)
        
        self.setAutoCompletionSource(QsciScintilla.AutoCompletionSource.AcsDocument)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)
        self.setAutoCompletionReplaceWord(True)

        # --- УМНАЯ КНОПКА ПРЫЖКА (TOP/END) ---
        self.btn_jump = QPushButton("⬇ END", self)
        self.btn_jump.setFixedSize(65, 26)
        self.btn_jump.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_jump.setToolTip("Перейти в конец/начало кода")
        self.btn_jump.setFocusPolicy(Qt.FocusPolicy.NoFocus) 
        self.btn_jump.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 30, 30, 180);
                color: #858585;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0e639c;
                color: white;
                border-color: #1177bb;
            }
        """)
        self.btn_jump.clicked.connect(self.toggle_jump)
        
        self.cursorPositionChanged.connect(self._update_jump_button)
        self.verticalScrollBar().valueChanged.connect(self._update_jump_button)

        self.search_panel = SearchPanel(self)

    def _is_at_bottom(self):
        """Универсальная проверка: находимся ли мы внизу документа"""
        vsb = self.verticalScrollBar()
        if vsb.maximum() > 0:
            return vsb.value() >= vsb.maximum() - 2
        else:
            current_line = self.getCursorPosition()[0]
            last_line = max(0, self.lines() - 1)
            return current_line >= (last_line / 2)

    def toggle_jump(self):
        """100% бронебойный прыжок с принудительной прокруткой ползунка"""
        if self._is_at_bottom():
            # Прыжок наверх
            self.SendScintilla(2316) # Нативный прыжок курсора (SCI_DOCUMENTSTART)
            self.verticalScrollBar().setValue(0) # Принудительно крутим ползунок
            self.setCursorPosition(0, 0)
        else:
            # Прыжок вниз
            self.SendScintilla(2318) # Нативный прыжок курсора (SCI_DOCUMENTEND)
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()) # Принудительно крутим ползунок
            last_line = max(0, self.lines() - 1)
            self.setCursorPosition(last_line, len(self.text(last_line)))
            
        self.setFocus()

    def _update_jump_button(self, *args):
        if not hasattr(self, 'btn_jump'): return
        
        if self._is_at_bottom():
            if self.btn_jump.text() != "⬆ TOP":
                self.btn_jump.setText("⬆ TOP")
        else:
            if self.btn_jump.text() != "⬇ END":
                self.btn_jump.setText("⬇ END")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'search_panel') and self.search_panel.isVisible():
            self.search_panel.update_position()
        if hasattr(self, 'btn_jump'):
            self.btn_jump.move(self.width() - 95, self.height() - 45)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_F:
            self.search_panel.show_panel()
            return
            
        if event.key() == Qt.Key.Key_Escape and hasattr(self, 'search_panel') and self.search_panel.isVisible():
            self.search_panel.hide_panel()
            return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            line, index = self.getCursorPosition()
            text_line = self.text(line)
            super().keyPressEvent(event)
            if text_line.strip().endswith(':'):
                indent = self.indentation(line) + self.indentationWidth()
                self.setIndentation(line + 1, indent)
                self.setCursorPosition(line + 1, indent)
            return

        char = event.text()
        if char in [')', ']', '}', '"', "'"]:
            line, index = self.getCursorPosition()
            text_line = self.text(line)
            if index < len(text_line) and text_line[index] == char:
                self.setCursorPosition(line, index + 1)
                return

        super().keyPressEvent(event)
        if char in ['(', '[', '{', '"', "'"]:
            pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
            line, index = self.getCursorPosition()
            self.insertAt(pairs[char], line, index)