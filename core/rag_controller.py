import os
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QDir, QTimer, QThread, pyqtSignal

from core.vector_db import VectorDatabase
from core.indexer_worker import IndexerWorker
from core.rag_dialog import RAGAnalyticsDialog
from core.embeddings import EmbeddingFactory

class ScannerThread(QThread):
    scan_finished = pyqtSignal(dict, bool)

    def __init__(self, project_path, allowed_extensions, last_mtimes):
        super().__init__()
        self.project_path = project_path
        self.allowed_extensions = allowed_extensions
        self.last_mtimes = last_mtimes

    def run(self):
        has_changes = False
        current_mtimes = {}
        
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', '__pycache__', 'node_modules')]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in self.allowed_extensions:
                    path = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(path)
                        current_mtimes[path] = mtime
                        if path not in self.last_mtimes or self.last_mtimes[path] != mtime:
                            has_changes = True
                    except OSError:
                        pass
                        
        self.scan_finished.emit(current_mtimes, has_changes)


class RagController:
    def __init__(self, main_window):
        self.mw = main_window 
        self.indexer_worker = None
        
        self.last_mtimes = {} 
        
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._start_background_scan)

        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(2000) 
        self.debounce_timer.timeout.connect(self.trigger_silent_update)

        self.allowed_extensions = {
            '.py', '.js', '.html', '.css', '.md', '.txt', '.json', 
            '.bat', '.sh', '.cpp', '.h', '.cs', '.java', '.php', '.go', '.rs'
        }
        
        self.scanner_thread = None

    def cleanup(self):
        """Полная остановка таймеров и потоков перед уничтожением контроллера (Защита от утечек контекста)"""
        self.poll_timer.stop()
        self.debounce_timer.stop()
        
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_thread.quit()
            self.scanner_thread.wait(1000)
            
        if self.indexer_worker and self.indexer_worker.isRunning():
            self.indexer_worker.stop()
            self.indexer_worker.wait(1000)
            
        # Точечный сброс системного кэша ChromaDB при реальной смене проекта
        try:
            import chromadb
            chromadb.api.client.SharedSystemClient.clear_system_cache()
            self.mw.log_system("🧹 [ChromaDB] Системный кэш векторов сброшен при очистке контроллера.")
        except Exception:
            pass

    def get_context_for_prompt(self, user_text):
        if not user_text or len(user_text.strip()) < 10:
            return ""

        db_path = os.path.join(self.mw.project_path, ".vibecoder", "vector_db")
        if not os.path.exists(db_path):
            return ""

        try:
            db = VectorDatabase(self.mw.project_path)
            if db.collection.count() == 0:
                return ""
                
            embed_provider, _ = EmbeddingFactory.get_provider("Gemini")
            self.mw.log_system("🔍 [RAG] Векторизация вопроса и поиск по кодовой базе...")
            
            query_vector = embed_provider.get_embedding(user_text)
            results = db.search(query_vector, n_results=3)
            
            if not results:
                return ""

            rag_context = "=== СИСТЕМНЫЙ КОНТЕКСТ ПРОЕКТА (RAG) ===\n"
            rag_context += "Ниже представлены фрагменты кода из текущего проекта, которые семантически связаны с запросом пользователя.\n"
            rag_context += "Используй их для понимания архитектуры, но не меняй, если пользователь явно не просил.\n\n"
            
            marker = '`' * 3
            for i, res in enumerate(results):
                file_path = res['metadata'].get('file_path', 'Неизвестный файл')
                rag_context += f"--- Файл: {file_path} (Совпадение #{i+1}) ---\n"
                rag_context += f"{marker}python\n{res['text']}\n{marker}\n\n"

            self.mw.log_system(f"🧠 [RAG] Найдено {len(results)} релевантных фрагментов.")
            return rag_context

        except Exception as e:
            self.mw.log_system(f"⚠️ Ошибка RAG-поиска: {str(e)}", color="#ffaa00")
            return ""

    def setup_watcher(self):
        self.poll_timer.stop()
        self.debounce_timer.stop()
        self.last_mtimes.clear()
        
        for root, dirs, files in os.walk(self.mw.project_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', '__pycache__', 'node_modules')]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in self.allowed_extensions:
                    path = os.path.join(root, f)
                    try:
                        self.last_mtimes[path] = os.path.getmtime(path)
                    except OSError:
                        pass
                        
        self.poll_timer.start(3000)

    def _start_background_scan(self):
        if self.scanner_thread and self.scanner_thread.isRunning():
            return
            
        self.scanner_thread = ScannerThread(self.mw.project_path, self.allowed_extensions, self.last_mtimes)
        self.scanner_thread.scan_finished.connect(self._on_scan_finished)
        self.scanner_thread.start()

    def _on_scan_finished(self, current_mtimes, has_changes):
        if has_changes:
            self.last_mtimes = current_mtimes
            self.debounce_timer.start()

    def show_analytics(self):
        db = VectorDatabase(self.mw.project_path)
        dlg = RAGAnalyticsDialog(self.mw, vector_db=db, settings=self.mw.settings)
        dlg.exec()

    def start_indexing(self):
        if self.indexer_worker and self.indexer_worker.isRunning():
            self.indexer_worker.stop()
            self.mw.btn_rag.setText("🧠 Остановка...")
            return

        reply = QMessageBox.question(self.mw, 'Векторная база данных', 
            "Запустить/обновить семантический индекс для всего проекта?\n(Это может занять время и потратить квоты API).", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
        if reply == QMessageBox.StandardButton.Yes:
            self.mw.btn_rag.setEnabled(False)
            self.mw.btn_rag.setText("🧠 Индексация...")
            self.mw.btn_rag.setStyleSheet("background-color: #ffaa00; color: black; font-weight: bold; border-radius: 4px; padding: 0 10px;")
            
            self.indexer_worker = IndexerWorker(self.mw.project_path, self.mw.file_manager, silent=False)
            self.indexer_worker.progress_signal.connect(self._on_indexer_progress)
            self.indexer_worker.finished_signal.connect(self._on_indexer_finished)
            self.indexer_worker.error_signal.connect(self._on_indexer_error)
            self.indexer_worker.log_signal.connect(lambda msg, color: self.mw.log_system(msg, color=color))
            self.indexer_worker.start()

    def trigger_silent_update(self):
        if self.indexer_worker and self.indexer_worker.isRunning():
            return 
            
        self.mw.btn_rag.setText("🧠 Синхронизация...")
        self.mw.btn_rag.setStyleSheet("background-color: #e6a822; color: black; font-weight: bold; border-radius: 4px; padding: 0 10px;")
        
        self.indexer_worker = IndexerWorker(self.mw.project_path, self.mw.file_manager, silent=True)
        self.indexer_worker.finished_signal.connect(self._on_silent_rag_finished)
        self.indexer_worker.log_signal.connect(lambda msg, color: self.mw.log_system(msg, color=color))
        self.indexer_worker.start()

    def _on_silent_rag_finished(self):
        self.mw.btn_rag.setText("🧠 RAG (Индекс)")
        self.mw.btn_rag.setStyleSheet("background-color: #00838f; color: white; font-weight: bold; border-radius: 4px; padding: 0 10px;")

    def _on_indexer_progress(self, current, total, filename):
        self.mw.status_bar.showMessage(f"🔄 Индексация (RAG): {current}/{total} | Файл: {filename}")

    def _on_indexer_finished(self):
        self.mw.btn_rag.setEnabled(True)
        self.mw.btn_rag.setText("🧠 RAG (Индекс)")
        self.mw.btn_rag.setStyleSheet("background-color: #00838f; color: white; font-weight: bold; border-radius: 4px; padding: 0 10px;")
        self.mw.update_status_bar() 
        self.mw.show_popup("Готово", "Индексация проекта успешно завершена (или остановлена)!\nТеперь ИИ 'знает' вашу кодовую базу.")

    def _on_indexer_error(self, err_msg):
        self.mw.btn_rag.setEnabled(True)
        self.mw.btn_rag.setText("🧠 RAG (Индекс)")
        self.mw.btn_rag.setStyleSheet("background-color: #00838f; color: white; font-weight: bold; border-radius: 4px; padding: 0 10px;")
        self.mw.update_status_bar()
        self.mw.show_popup("Ошибка RAG", f"Сбой индексации:\n{err_msg}", is_error=True)