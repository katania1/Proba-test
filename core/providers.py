import requests
from abc import ABC, abstractmethod

class AbstractProvider(ABC):
    def __init__(self, api_key, base_url=None):
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Отправляет запрос к API и возвращает сгенерированный ответ (строку)."""
        pass

class OpenAIProvider(AbstractProvider):
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.base_url:
            self.base_url = "https://api.openai.com/v1"
            
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4o", # Дефолтная модель, можно сделать настраиваемой
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2 # Низкая температура для стабильного JSON
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

class AnthropicProvider(AbstractProvider):
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.base_url:
            self.base_url = "https://api.anthropic.com"
            
        url = f"{self.base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 8192,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        return response.json()["content"][0]["text"]

class GeminiAPIProvider(AbstractProvider):
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        # Для Gemini API system_prompt нужно передавать особым образом
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json"
        }
        
        # Комбинируем системный промпт и запрос
        full_text = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        
        data = {
            "contents": [{"parts": [{"text": full_text}]}],
            "generationConfig": {
                "temperature": 0.2
            }
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        
        resp_json = response.json()
        try:
            return resp_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise Exception(f"Неожиданный формат ответа Gemini: {resp_json}")