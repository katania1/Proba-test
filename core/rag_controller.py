import os
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QDir, QTimer

from core.vector_db import VectorDatabase
from core.indexer_worker import IndexerWorker
from core.rag_dialog import RAGAnalyticsDialog

class RagController:
    def __init__(self, main_window):
        self.mw = main_window 
        self.indexer_worker = None
        
        # --- БРОНЕБОЙНАЯ СИСТЕМА ПОЛЛИНГА (POLLING) ---
        self.last_mtimes = {} # Словарь: {путь_к_файлу: время_последнего_изменения}
        
        # Таймер-сканер: тихо проверяет файлы каждые 3 секунды
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._scan_all_files)

        # Таймер-предохранитель: ждет 2 секунды после нахождения изменений, 
        # чтобы ты успел досохранять файл, прежде чем дергать API
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(2000) 
        self.debounce_timer.timeout.connect(self.trigger_silent_update)

        self.allowed_extensions = {
            '.py', '.js', '.html', '.css', '.md', '.txt', '.json', 
            '.bat', '.sh', '.cpp', '.c', '.h', '.java', '.go'
        }
        self.ignore_dirs = {'.git', '.vibecoder', 'venv', 'env', '__pycache__', 'node_modules', '.idea'}

        self.setup_watcher()

    def setup_watcher(self):
        """Запускает таймер и собирает стартовые даты всех файлов проекта"""
        if not self.mw.project_path or len(self.mw.project_path) <= 3: 
            self.poll_timer.stop()
            return

        self.last_mtimes.clear()
        
        # Первичное сканирование (без запуска индексации)
        self._scan_all_files(initial_setup=True)
        
        # Запускаем бесконечный цикл проверок (каждые 10000 мс)
        self.poll_timer.start(10000)

    def _scan_all_files(self, initial_setup=False):
        """Пробегает по файлам и ищет изменения в дате редактирования (mtime)"""
        # Если автообновление выключено в настройках - ничего не делаем
        if not self.mw.settings.value("auto_rag_update", True, type=bool) and not initial_setup:
            return

        has_changes = False
        current_files = set()

        # Быстрый проход по директориям
        for root, dirs, files in os.walk(self.mw.project_path):
            # Отсекаем мусорные папки на лету
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in self.allowed_extensions:
                    file_path = os.path.join(root, filename)
                    current_files.add(file_path)
                    
                    try:
                        mtime = os.path.getmtime(file_path)
                        
                        # 1. Если это новый файл
                        if file_path not in self.last_mtimes:
                            self.last_mtimes[file_path] = mtime
                            if not initial_setup: 
                                has_changes = True
                                
                        # 2. Если файл изменили (дата новее)
                        elif mtime > self.last_mtimes[file_path]:
                            self.last_mtimes[file_path] = mtime
                            has_changes = True
                            
                    except OSError:
                        pass # Файл недоступен

        # 3. Проверяем, не удалили ли какой-то файл
        deleted_files = set(self.last_mtimes.keys()) - current_files
        if deleted_files:
            for f in deleted_files:
                del self.last_mtimes[f]
            if not initial_setup:
                has_changes = True

        # Если нашли любые изменения - заводим таймер на индексацию
        if has_changes and not initial_setup:
            self.debounce_timer.start()

    def show_analytics(self, pos):
        if not self.mw.project_path or self.mw.project_path == QDir.currentPath() or len(self.mw.project_path) <= 3:
            self.mw.show_popup("Ошибка", "Сначала откройте или создайте рабочий проект.")
            return
            
        try:
            db = VectorDatabase(self.mw.project_path)
            dlg = RAGAnalyticsDialog(self.mw, db, self.mw.settings)
            dlg.exec()
        except Exception as e:
            self.mw.log_system(f"Ошибка открытия базы RAG: {e}", "#ff4444")

    def start_indexing(self):
        if self.indexer_worker and self.indexer_worker.isRunning():
            self.indexer_worker.stop()
            self.mw.btn_rag.setText("⏳ Остановка...")
            self.mw.btn_rag.setEnabled(False)
            return
            
        if not self.mw.project_path or self.mw.project_path == QDir.currentPath() or len(self.mw.project_path) <= 3:
            self.mw.show_popup("Ошибка", "Сначала выберите или создайте рабочий проект в Менеджере Проектов.", is_error=True)
            return
            
        reply = self.mw.show_question("RAG Индексация", 
                                   "Запустить семантическую индексацию проекта?\nЭто может занять некоторое время в зависимости от размера кодовой базы.")
        if reply == QMessageBox.StandardButton.No:
            return

        self.mw.btn_rag.setEnabled(True)
        self.mw.btn_rag.setText("🛑 Стоп RAG")
        self.mw.btn_rag.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; border-radius: 4px; padding: 0 10px;")
        
        self.indexer_worker = IndexerWorker(self.mw.project_path, self.mw.file_manager)
        self.indexer_worker.progress_signal.connect(self._on_indexer_progress)
        self.indexer_worker.log_signal.connect(self.mw.log_system)
        self.indexer_worker.finished_signal.connect(self._on_indexer_finished)
        self.indexer_worker.error_signal.connect(self._on_indexer_error)
        
        self.indexer_worker.start()

    def trigger_silent_update(self):
        """Фоновое обновление индекса только для измененных файлов"""
        if not self.mw.settings.value("auto_rag_update", True, type=bool):
            return 

        if self.indexer_worker and self.indexer_worker.isRunning():
            return 

        self.mw.btn_rag.setStyleSheet("background-color: #e6a822; color: black; font-weight: bold; border-radius: 4px; padding: 0 10px;")
        self.mw.btn_rag.setText("⏳ RAG...")
        
        self.indexer_worker = IndexerWorker(self.mw.project_path, self.mw.file_manager, silent=True)
        self.indexer_worker.finished_signal.connect(self._on_silent_rag_finished)
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
        self.mw.show_popup("Ошибка индексации", f"Произошла ошибка при векторизации:\n{err_msg}", is_error=True)
        self.mw.log_system(f"Ошибка RAG: {err_msg}", "#ff4444")