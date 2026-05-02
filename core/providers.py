import requests
from abc import ABC, abstractmethod

class AbstractProvider(ABC):
    def __init__(self, api_key, base_url=None):
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "", model: str = "") -> str:
        """Отправляет запрос к API и возвращает сгенерированный ответ (строку)."""
        pass

    @abstractmethod
    def get_models(self) -> list:
        """Запрашивает теоретический список доступных моделей у провайдера."""
        pass

    @abstractmethod
    def verify_model(self, model: str) -> tuple[bool, str]:
        """Делает микро-запрос для проверки реального доступа к модели (баланс/лимиты)."""
        pass

class OpenAIProvider(AbstractProvider):
    def generate(self, prompt: str, system_prompt: str = "", model: str = "gpt-4o") -> str:
        if not self.base_url:
            self.base_url = "https://api.openai.com/v1"
            
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model or "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def get_models(self) -> list:
        if not self.base_url:
            self.base_url = "https://api.openai.com/v1"
        url = f"{self.base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        models = [m["id"] for m in data.get("data", [])]
        return sorted(models, reverse=True)

    def verify_model(self, model: str) -> tuple[bool, str]:
        if not self.base_url:
            self.base_url = "https://api.openai.com/v1"
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        
        # Попытка 1: С классическим ограничением (спасает от ошибки баланса в OpenRouter)
        data = {
            "model": model or "gpt-4o",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 15
        }
        
        try:
            res = requests.post(url, headers=headers, json=data, timeout=15)
            res.raise_for_status()
            return True, "Доступ подтвержден! Модель готова к работе."
        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json().get("error", {})
                    err_msg = error_data.get("message", err_msg)
                    
                    # Попытка 2: Если это o1-подобная модель, требующая max_completion_tokens
                    if "max_tokens" in err_msg and "max_completion_tokens" in err_msg:
                        data.pop("max_tokens")
                        data["max_completion_tokens"] = 15
                        
                        res2 = requests.post(url, headers=headers, json=data, timeout=15)
                        res2.raise_for_status()
                        return True, "Доступ подтвержден! (Использован max_completion_tokens)"
                        
                except Exception:
                    pass
            return False, f"Ошибка доступа: {err_msg}"

class AnthropicProvider(AbstractProvider):
    def generate(self, prompt: str, system_prompt: str = "", model: str = "claude-3-5-sonnet-20241022") -> str:
        if not self.base_url:
            self.base_url = "https://api.anthropic.com"
            
        url = f"{self.base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        data = {
            "model": model or "claude-3-5-sonnet-20241022",
            "max_tokens": 8192,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        return response.json()["content"][0]["text"]

    def get_models(self) -> list:
        if not self.base_url:
            self.base_url = "https://api.anthropic.com"
        url = f"{self.base_url.rstrip('/')}/v1/models"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        models = [m["id"] for m in data.get("data", []) if m["type"] == "model"]
        return sorted(models, reverse=True)

    def verify_model(self, model: str) -> tuple[bool, str]:
        if not self.base_url:
            self.base_url = "https://api.anthropic.com"
        url = f"{self.base_url.rstrip('/')}/v1/messages"
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        data = {
            "model": model or "claude-3-5-sonnet-20241022",
            "max_tokens": 15,
            "messages": [{"role": "user", "content": "ping"}]
        }
        try:
            res = requests.post(url, headers=headers, json=data, timeout=15)
            res.raise_for_status()
            return True, "Доступ подтвержден! Модель готова к работе."
        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    err_msg = e.response.json().get("error", {}).get("message", err_msg)
                except ValueError:
                    pass
            return False, f"Ошибка доступа: {err_msg}"

class GeminiAPIProvider(AbstractProvider):
    def generate(self, prompt: str, system_prompt: str = "", model: str = "gemini-1.5-pro") -> str:
        used_model = model or "gemini-1.5-pro"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{used_model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        
        full_text = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        
        data = {
            "contents": [{"parts": [{"text": full_text}]}],
            "generationConfig": {"temperature": 0.2}
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        
        resp_json = response.json()
        try:
            return resp_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise Exception(f"Неожиданный формат ответа Gemini: {resp_json}")

    def get_models(self) -> list:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        models = []
        for m in data.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                name = m["name"].split("/")[-1]
                models.append(name)
        return sorted(models, reverse=True)

    def verify_model(self, model: str) -> tuple[bool, str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"parts": [{"text": "ping"}]}],
        }
        try:
            res = requests.post(url, headers=headers, json=data, timeout=15)
            res.raise_for_status()
            return True, "Доступ подтвержден! Модель готова к работе."
        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    err_msg = e.response.json().get("error", {}).get("message", err_msg)
                except ValueError:
                    pass
            return False, f"Ошибка доступа: {err_msg}"