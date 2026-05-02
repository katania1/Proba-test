from PyQt6.Qsci import QsciScintilla, QsciLexerPython
from PyQt6.QtGui import QColor, QFont

class DarkPythonEditor(QsciScintilla):
    def __init__(self):
        super().__init__()
        
        # --- БАЗОВЫЕ НАСТРОЙКИ ---
        self.setUtf8(True)
        self.setEolMode(QsciScintilla.EolMode.EolUnix) 
        
        font = QFont("Consolas", 11)
        self.setFont(font)
        self.setMarginsFont(font)
        
        # --- ИСПРАВЛЕНИЕ: ЖЕСТКИЕ ТАБЫ ДЛЯ ПУНКТИРОВ ---
        # Указываем движку, что отступ = ровно 4 пробела. 
        # Без этого главные линии под def не рисуются!
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setIndentationWidth(4)
        
        # Пунктирные направляющие в коде
        self.setIndentationGuides(True)
        self.SendScintilla(2132, 3) # SCI_SETINDENTATIONGUIDES, SC_IV_LOOKBOTH
        self.setIndentationGuidesForegroundColor(QColor("#707070")) # Сделаем их ярче
        
        # --- НАСТРОЙКИ ПАНЕЛЕЙ (MARGINS) ---
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "00000") 
        self.setMarginsBackgroundColor(QColor("#252526"))
        self.setMarginsForegroundColor(QColor("#858585"))
        self.setMarginWidth(1, 0)
        
        # --- СИСТЕМА СВОРАЧИВАНИЯ (НИТИ СБОКУ) ---
        try:
            self.setFolding(QsciScintilla.FoldStyle.BoxedTreeFoldStyle)
        except AttributeError:
            self.setFolding(2)
            
        self.setMarginType(2, QsciScintilla.MarginType.SymbolMargin)
        self.setMarginSensitivity(2, True)
        self.setMarginWidth(2, 20)
        self.setFoldMarginColors(QColor("#252526"), QColor("#252526"))
        
        self.SendScintilla(2162, 16 | 32 | 64) 
        
        # --- ИСПРАВЛЕНИЕ: ЦВЕТА НИТЕЙ СВОРАЧИВАНИЯ ---
        fold_fg = QColor("#d4d4d4")    # Цвет самих нитей (светлый)
        margin_bg = QColor("#252526")  # Фон панели (чтобы нити сливались с панелью)
        box_bg = QColor("#1e1e1e")     # Фон внутри квадратиков [+] (под цвет редактора)
        
        # 1. Красим ВСЕ 7 маркеров: делаем светлую линию на фоне панели
        for m in range(25, 32):
            self.setMarkerForegroundColor(fold_fg, m)
            self.setMarkerBackgroundColor(margin_bg, m)
            
        # 2. Выборочно меняем фон ТОЛЬКО для квадратиков, делая внутри "дырку"
        boxes = [
            QsciScintilla.SC_MARKNUM_FOLDER,
            QsciScintilla.SC_MARKNUM_FOLDEROPEN,
            QsciScintilla.SC_MARKNUM_FOLDEREND,
            QsciScintilla.SC_MARKNUM_FOLDEROPENMID
        ]
        for m in boxes:
            self.setMarkerBackgroundColor(box_bg, m)
        
        # --- ОБЩИЙ ВИД РЕДАКТОРА ---
        self.setPaper(QColor("#1e1e1e"))
        self.setCaretForegroundColor(QColor("#d4d4d4"))
        self.setCaretLineVisible(True) 
        self.setCaretLineBackgroundColor(QColor("#2a2d2e"))
        
        # --- ПОДСВЕТКА СИНТАКСИСА (ЛЕКСЕР) ---
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