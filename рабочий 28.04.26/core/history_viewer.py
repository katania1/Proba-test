from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser
from PyQt6.QtCore import Qt

class HistoryDialog(QDialog):
    def __init__(self, parent, logger):
        super().__init__(parent)
        self.setWindowTitle("📜 Полная история переписок")
        self.resize(800, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; padding: 10px;")
        
        # Разрешаем кликабельные ссылки и направляем их в главное окно
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(parent.handle_chat_link) 
        
        layout.addWidget(self.browser)
        self.load_history(logger)

    def load_history(self, logger):
        history = logger.get_all()
        html = "<div style='font-family: Arial; font-size: 13px;'>"
        for i, item in enumerate(history):
            time = item['timestamp']
            role = item['role']
            text = item['text']
            
            # Экранируем переносы строк
            text = text.replace('\n', '<br>')
            
            if role == "USER":
                html += f"<div style='color: #569cd6; margin-top: 15px;'><b>[{time}] ВЫ:</b><br>{text}</div>"
            elif role == "AI":
                html += f"<div style='color: #bb86fc; margin-top: 15px;'><b>[{time}] GEMINI:</b><br>{text}</div>"
            elif role == "SYSTEM":
                html += f"<div style='color: #ffaa00; margin-top: 15px;'><b>[{time}] СИСТЕМА:</b> {text}</div>"
            elif role == "RELAY":
                html += f"<div style='color: #31a24c; margin-top: 15px; background-color: #1a3320; padding: 5px; border-radius: 4px;'>"
                html += f"<b>[{time}] 🔄 СМЕНА СЕССИИ:</b> {text} "
                html += f"<a href='relay:{i}' style='color: #569cd6;'><b>[Показать текст эстафеты]</b></a></div>"
                
        html += "</div>"
        self.browser.setHtml(html)
        
        # Прокрутка в самый низ к последним сообщениям
        scrollbar = self.browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())