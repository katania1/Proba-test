from PyQt6.QtCore import QThread, pyqtSignal

class APIWorker(QThread):
    # Сигналы для связи с главным потоком интерфейса
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, provider, prompt, system_prompt=""):
        super().__init__()
        self.provider = provider
        self.prompt = prompt
        self.system_prompt = system_prompt

    def run(self):
        """Этот метод выполняется в отдельном фоновом потоке."""
        try:
            result = self.provider.generate(self.prompt, self.system_prompt)
            self.finished_signal.emit(result)
        except Exception as e:
            # Перехватываем любую сетевую ошибку (таймаут, неверный ключ, 404 и т.д.)
            self.error_signal.emit(f"API Error: {str(e)}")