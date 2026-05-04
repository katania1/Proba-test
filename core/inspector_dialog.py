from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, QTextBrowser
from PyQt6.QtCore import Qt

class InspectorDialog(QDialog):
    def __init__(self, parent, agent_trace):
        super().__init__(parent)
        self.setWindowTitle("🐞 Инспектор сессии (Agent Trace)")
        self.resize(1100, 700)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        # Список словарей вида [{"title": "User Request", "content": "..."}]
        self.agent_trace = agent_trace 
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget { background-color: #252526; border: 1px solid #3c3c3c; font-size: 13px; outline: none; }
            QListWidget::item { padding: 12px; border-bottom: 1px solid #333333; }
            QListWidget::item:selected { background-color: #0e639c; color: white; border-radius: 3px; }
            QListWidget::item:hover:!selected { background-color: #2a2d2e; }
        """)
        self.list_widget.currentRowChanged.connect(self.display_trace_item)
        
        self.text_browser = QTextBrowser()
        self.text_browser.setStyleSheet("""
            background-color: #1e1e1e; 
            border: 1px solid #3c3c3c; 
            font-family: Consolas, monospace; 
            font-size: 13px; 
            padding: 10px;
            color: #d4d4d4;
        """)
        
        splitter.addWidget(self.list_widget)
        splitter.addWidget(self.text_browser)
        splitter.setSizes([300, 800])
        
        layout.addWidget(splitter)
        
        self.populate_list()
        
    def populate_list(self):
        if not self.agent_trace:
            self.list_widget.addItem("📭 Нет данных о текущей сессии.")
            return
            
        for i, trace in enumerate(self.agent_trace):
            title = trace.get("title", f"Шаг {i+1}")
            self.list_widget.addItem(f"[{i+1}] {title}")
            
        self.list_widget.setCurrentRow(0)
        
    def display_trace_item(self, index):
        if 0 <= index < len(self.agent_trace):
            content = self.agent_trace[index].get("content", "")
            # Эскейпим HTML теги, чтобы сырой код (особенно RAG) отображался корректно
            safe_content = content.replace('<', '&lt;').replace('>', '&gt;')
            
            # Обертка pre сохраняет переносы строк и отступы JSON
            self.text_browser.setHtml(f"<pre style='white-space: pre-wrap; font-family: Consolas;'>{safe_content}</pre>")