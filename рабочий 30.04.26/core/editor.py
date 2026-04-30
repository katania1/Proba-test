from PyQt6.Qsci import QsciScintilla, QsciLexerPython
from PyQt6.QtGui import QColor, QFont

class DarkPythonEditor(QsciScintilla):
    def __init__(self):
        super().__init__()
        
        # Базовые настройки
        self.setUtf8(True)
        font = QFont("Consolas", 11)
        self.setFont(font)
        self.setMarginsFont(font)
        
        # Настройка панели с номерами строк (Слева)
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "00000") # Ширина под 4-значные числа
        self.setMarginsBackgroundColor(QColor("#252526"))
        self.setMarginsForegroundColor(QColor("#858585"))
        
        # Цвета самого редактора (Фон и курсор)
        self.setPaper(QColor("#1e1e1e"))
        self.setCaretForegroundColor(QColor("#d4d4d4"))
        self.setCaretLineVisible(True) # Подсветка текущей строки
        self.setCaretLineBackgroundColor(QColor("#2a2d2e"))
        
        # --- Подсветка синтаксиса (Лексер) ---
        self.lexer = QsciLexerPython(self)
        self.lexer.setDefaultFont(font)
        self.lexer.setDefaultPaper(QColor("#1e1e1e"))
        
        # Назначаем цвета (Палитра VS Code)
        self.lexer.setColor(QColor("#569cd6"), QsciLexerPython.Keyword)          # def, class, return
        self.lexer.setColor(QColor("#4EC9B0"), QsciLexerPython.ClassName)         # Имена классов
        self.lexer.setColor(QColor("#DCDCAA"), QsciLexerPython.FunctionMethodName)# Имена функций
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.SingleQuotedString)# Строки ''
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.DoubleQuotedString)# Строки ""
        
        # Исправление для многострочных комментариев/строк
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.TripleSingleQuotedString) # Строки '''
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.TripleDoubleQuotedString) # Строки """
        
        self.lexer.setColor(QColor("#6A9955"), QsciLexerPython.Comment)           # Комментарии #
        self.lexer.setColor(QColor("#b5cea8"), QsciLexerPython.Number)            # Цифры
        self.lexer.setColor(QColor("#d4d4d4"), QsciLexerPython.Identifier)        # Переменные
        self.lexer.setColor(QColor("#d4d4d4"), QsciLexerPython.Operator)          # Знаки =, +, -
        
        self.setLexer(self.lexer)