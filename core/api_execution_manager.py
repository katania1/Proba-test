import json
from PyQt6.QtCore import QSettings
from core.providers import OpenAIProvider, AnthropicProvider, GeminiAPIProvider
from core.api_worker import APIWorker


class APIExecutionManager:
    """
    Оркестратор сетевых API и провайдеров (Фабрика).
    Отвечает за чтение учетных данных, инициализацию нужного класса провайдера
    и запуск асинхронного воркера (APIWorker) для выполнения задач.
    """

    def __init__(self, controller):
        self.ctrl = controller

    def execute(self, provider_id, selected_model, image_paths=None, sys_prompt=""):
        """
        Инициализирует провайдера на основе настроек и запускает генерацию.
        Все логи и ошибки автоматически перенаправляются в системный чат.
        """
        if not sys_prompt:
            sys_prompt = self.ctrl.orchestrator.system_prompt

        settings = QSettings("VibeCoder", "API_Config")
        provider = None

        try:
            if provider_id == "OpenAI":
                key = settings.value("openai_api_key", "")
                url = settings.value("openai_base_url", "https://api.openai.com/v1")
                if not key:
                    raise Exception("API ключ OpenAI не задан! Откройте ⚙️ API.")
                provider = OpenAIProvider(key, url)

            elif provider_id == "Anthropic":
                key = settings.value("anthropic_api_key", "")
                url = settings.value("anthropic_base_url", "https://api.anthropic.com")
                if not key:
                    raise Exception("API ключ Anthropic не задан! Откройте ⚙️ API.")
                provider = AnthropicProvider(key, url)

            elif provider_id == "Gemini":
                key = settings.value("gemini_api_key", "")
                if not key:
                    raise Exception("API ключ Gemini не задан! Откройте ⚙️ API.")
                provider = GeminiAPIProvider(key)

            else:
                # Динамический парсинг кастомных OpenAI-совместимых провайдеров
                custom_providers = json.loads(settings.value("custom_providers", "[]"))
                found = next((p for p in custom_providers if p["id"] == provider_id), None)
                
                if not found:
                    raise Exception(f"Неизвестный провайдер: {provider_id}")
                
                if not found["key"]:
                    log_func = (
                        self.ctrl.mw.chat_handler.log_system
                        if hasattr(self.ctrl.mw, "chat_handler")
                        else self.ctrl.mw.log_system
                    )
                    log_func(f"Внимание: Ключ для {found['name']} пуст.", color="#ffaa00")
                
                provider = OpenAIProvider(found["key"], found["url"])

            if provider:
                media_log = f" и {len(image_paths)} картинками" if image_paths else ""
                log_func = (
                    self.ctrl.mw.chat_handler.log_system
                    if hasattr(self.ctrl.mw, "chat_handler")
                    else self.ctrl.mw.log_system
                )
                log_func(
                    f"Отправка запроса{media_log} через API (Модель: {selected_model})..."
                )

                # Переопределяем метод generate "на лету" для внедрения параметров сессии
                original_generate = provider.generate
                provider.generate = lambda p, sp: original_generate(
                    p, sp, model=selected_model, image_paths=image_paths
                )

                self.ctrl.worker = APIWorker(
                    provider,
                    self.ctrl.mw.last_full_prompt,
                    sys_prompt,
                    mcp_manager=self.ctrl.mcp_manager,
                )
                self.ctrl.worker.finished_signal.connect(self.ctrl.process_ai_response)

                err_log_func = (
                    self.ctrl.mw.chat_handler.log_system
                    if hasattr(self.ctrl.mw, "chat_handler")
                    else self.ctrl.mw.log_system
                )
                self.ctrl.worker.error_signal.connect(
                    lambda err: err_log_func(
                        f"ОШИБКА API: {err}", color="#ff4444", is_bold=True
                    )
                )
                self.ctrl.worker.log_signal.connect(lambda msg: err_log_func(msg))
                self.ctrl.worker.start()

        except Exception as e:
            self.ctrl.mw.show_popup("Ошибка конфигурации API", str(e), is_error=True)
            err_log_func = (
                self.ctrl.mw.chat_handler.log_system
                if hasattr(self.ctrl.mw, "chat_handler")
                else self.ctrl.mw.log_system
            )
            err_log_func(f"Сбой запуска API: {str(e)}", color="#ff4444", is_bold=True)