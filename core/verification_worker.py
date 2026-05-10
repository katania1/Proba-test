from PyQt6.QtCore import QThread, pyqtSignal

# ==========================================
# ФОНОВЫЙ ВОРКЕР ДЛЯ ПРОВЕРКИ API И МОДЕЛЕЙ
# ==========================================
class VerificationWorker(QThread):
    models_fetched = pyqtSignal(list)
    verification_done = pyqtSignal(bool, str)
    error_signal = pyqtSignal(str)

    def __init__(self, provider, action, model_to_verify=""):
        super().__init__()
        self.provider = provider
        self.action = action 
        self.model_to_verify = model_to_verify

    def run(self):
        try:
            if self.action == 'fetch_models':
                models = self.provider.get_models()
                self.models_fetched.emit(models)
            elif self.action == 'verify':
                success, msg = self.provider.verify_model(self.model_to_verify)
                self.verification_done.emit(success, msg)
        except Exception as e:
            self.error_signal.emit(str(e))