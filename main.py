import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
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
    app.setStyleSheet(DARK_THEME)
    
    # 1. Задаем глобальные имена ПЕРЕД настройкой путей
    app.setOrganizationName("VibeCoder")
    app.setApplicationName("IDE")
    
    # 2. Создаем директории (Qt иногда не может сам создать вложенную папку)
    app_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(app_dir, "config")
    vibe_dir = os.path.join(config_dir, "VibeCoder") # Вложенная папка организации
    
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(vibe_dir, exist_ok=True) # КРИТИЧНОЕ ИСПРАВЛЕНИЕ
    
    # 3. Принудительно переключаем QSettings на локальные INI файлы
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, config_dir)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.SystemScope, config_dir)
    
    # 4. Тестовая запись и проверка
    pref = QSettings("VibeCoder", "Preferences")
    pref.setValue("portable_mode", True)
    pref.sync()
    
    api = QSettings("VibeCoder", "API_Config")
    api.setValue("init", True)
    api.sync()
    
    # Выводим в консоль терминала точный путь, где создался файл
    print(f"[VibeCoder] Настройки сохраняются в: {pref.fileName()}")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()