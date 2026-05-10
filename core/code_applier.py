import os
from PyQt6.QtWidgets import QDialog
from core.diff_viewer import DiffDialog

class CodeApplier:
    def __init__(self, main_window):
        self.mw = main_window # Ссылка на главное окно

    def is_path_safe(self, file_path):
        abs_project = os.path.abspath(self.mw.project_path)
        abs_file = os.path.abspath(os.path.join(self.mw.project_path, file_path))
        return os.path.commonpath([abs_project]) == os.path.commonpath([abs_project, abs_file])

    def get_file_content_safe(self, rel_path):
        if not self.is_path_safe(rel_path): 
            return None
        abs_path = os.path.abspath(os.path.join(self.mw.project_path, rel_path))
        if os.path.isfile(abs_path):
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass
        return None

    def manual_save(self):
        if not self.mw.current_file_path: return
        current_text = self.mw.editor.text()
        
        with open(self.mw.current_file_path, 'r', encoding='utf-8') as f:
            old_text = f.read()
            
        # Сохраняем, только если текст действительно изменился
        if current_text.replace('\r\n', '\n') != old_text.replace('\r\n', '\n'):
            self.mw.file_manager.save_file(self.mw.current_file_path, current_text) 
            self.mw.log_system(f"Ручное сохранение: {os.path.basename(self.mw.current_file_path)}", color="#31a24c")
            
            # ТИХОЕ УВЕДОМЛЕНИЕ вместо popup-окна (висит 3 секунды)
            self.mw.status_bar.showMessage(f"💾 Файл успешно сохранен", 3000)
            
            self.mw.update_git_status()
            self.mw.trigger_silent_rag_update()

    def review_and_approve(self):
        if self.mw.proposed_updates:
            update = self.mw.proposed_updates[0] 
            rel_path = update.get("file_path", "")
            new_code = update.get("code", "")
            abs_path = os.path.abspath(os.path.join(self.mw.project_path, rel_path))
            
            old_code = ""
            if os.path.exists(abs_path):
                with open(abs_path, 'r', encoding='utf-8') as f:
                    old_code = f.read()
                    
            dialog = DiffDialog(self.mw, old_code, new_code, f"{rel_path} (Файл 1 из {len(self.mw.proposed_updates)})")
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.mw.file_manager.save_file(abs_path, new_code)
                
                if self.mw.current_file_path and os.path.normpath(self.mw.current_file_path) == os.path.normpath(abs_path):
                    self.mw.editor.setText(new_code)
                    
                self.mw.log_system(f"Изменения от ИИ в {rel_path} сохранены!", color="#2e7d32")
                self.mw.update_git_status()
                self.mw.trigger_silent_rag_update()
                
                self.mw.proposed_updates.pop(0)
                
                if self.mw.proposed_updates:
                    self.mw.btn_approve.setText(f"✅ Ревью (Осталось: {len(self.mw.proposed_updates)})")
                else:
                    self.mw.btn_reject_main.setVisible(False)
                    self.mw.btn_approve.setText("✅ Утвердить код")
            else:
                self.reject_preview()
            return
            
        if self.mw.current_file_path:
            current_text = self.mw.editor.text()
            with open(self.mw.current_file_path, 'r', encoding='utf-8') as f:
                old_text = f.read()
                
            if current_text.replace('\r\n', '\n') != old_text.replace('\r\n', '\n'):
                rel_path = os.path.basename(self.mw.current_file_path)
                dialog = DiffDialog(self.mw, old_text, current_text, rel_path + " (Ручные правки)")
                
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    self.mw.file_manager.save_file(self.mw.current_file_path, current_text)
                    self.mw.log_system(f"Ручные правки в {rel_path} утверждены и сохранены!", color="#2e7d32")
                    self.mw.update_git_status()
                    self.mw.trigger_silent_rag_update()
                return

        self.mw.show_popup("Пусто", "Нет изменений для утверждения.")

    def reject_preview(self):
        if self.mw.memory_old_code is not None:
            self.mw.editor.setText(self.mw.memory_old_code)
            self.mw.memory_old_code = None
        self.mw.proposed_updates = []
        self.mw.btn_reject_main.setVisible(False)
        self.mw.btn_approve.setText("✅ Утвердить код")
        self.mw.log_system("Предпросмотр отклонен.", color="#ff4444")