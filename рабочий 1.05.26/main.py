import sys
from PyQt6.QtWidgets import QApplication
from core.ui_main import MainWindow

# Глобальная темная тема (CSS для PyQt)
DARK_THEME = """
QMainWindow { background-color: #1e1e1e; }
QWidget { color: #d4d4d4; font-family: 'Segoe UI', sans-serif; font-size: 10pt; }

/* Дерево файлов */
QTreeView { background-color: #252526; border: none; outline: 0;}
QTreeView::item { padding: 4px; }
QTreeView::item:selected { background-color: #37373d; border-radius: 3px; }
QTreeView::item:hover { background-color: #2a2d2e; }

/* Текстовые поля (Чат и ввод) */
QTextEdit { 
    background-color: #252526; 
    border: 1px solid #3c3c3c; 
    border-radius: 5px; 
    padding: 8px; 
}

/* Кнопки */
QPushButton { 
    background-color: #0e639c; 
    color: white; 
    border: none; 
    border-radius: 5px; 
    padding: 8px 16px; 
    font-weight: bold;
}
QPushButton:hover { background-color: #1177bb; }
QPushButton:pressed { background-color: #094771; }

/* Разделители панелей (Сплиттеры) */
QSplitter::handle { background-color: #333333; width: 2px; }
QSplitter::handle:hover { background-color: #0e639c; }
"""

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    app.setStyleSheet(DARK_THEME) # Применяем дизайн
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()