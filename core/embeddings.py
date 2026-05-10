import json
import requests
from abc import ABC, abstractmethod
from PyQt6.QtCore import QSettings

class AbstractEmbedding(ABC):
    @abstractmethod
    def get_embedding(self, text: str) -> list[float]:
        pass

class GeminiEmbedding(AbstractEmbedding):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = "gemini-embedding-001" 

    def get_embedding(self, text: str) -> list[float]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        data = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": text}]}
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code != 200:
            try:
                error_msg = response.json().get("error", {}).get("message", response.text)
                raise Exception(f"Embedding API Error ({response.status_code}): {error_msg}")
            except Exception as e:
                raise Exception(f"Embedding API Error: {response.status_code} - {response.text}")
                
        resp_json = response.json()
        try:
            return resp_json["embedding"]["values"]
        except KeyError:
            raise Exception(f"Неожиданный формат ответа эмбеддинга: {resp_json}")

class EmbeddingFactory:
    _current_key_index = 0
    _available_keys = []
    _current_provider_name = None
    _key_comments = {} # Храним маппинг "ключ -> комментарий" для красивых логов

    @classmethod
    def _load_keys(cls, provider_name="Gemini"):
        settings = QSettings("VibeCoder", "API_Config")
        keys = []
        cls._key_comments.clear()
        
        if provider_name == "Gemini":
            emb_keys_str = settings.value("gemini_embedding_key", "").strip()
            main_key_str = settings.value("gemini_api_key", "").strip()
            
            if emb_keys_str:
                try:
                    # Пытаемся распарсить как новый JSON-массив
                    keys_data = json.loads(emb_keys_str)
                    for item in keys_data:
                        # Берем ТОЛЬКО те ключи, где стоит галочка
                        if item.get("enabled", True):
                            k = item.get("key", "").strip()
                            if k:
                                keys.append(k)
                                cls._key_comments[k] = item.get("comment", "")
                except:
                    # Фолбэк на случай старого формата через запятую (на всякий случай)
                    for k in emb_keys_str.split(','):
                        k = k.strip()
                        if k:
                            keys.append(k)
                            cls._key_comments[k] = ""
                            
            # Фоллбэк: если пул пуст или все ключи ВЫКЛЮЧЕНЫ чекбоксами, берем основной
            if not keys and main_key_str:
                keys = [main_key_str]
                cls._key_comments[main_key_str] = "Основной ключ (Фоллбэк)"
                
        cls._available_keys = keys
        return keys

    @classmethod
    def get_provider(cls, provider_name="Gemini"):
        # Обновляем пул, если провайдер сменился или пул пуст
        if not cls._available_keys or cls._current_provider_name != provider_name:
            cls._load_keys(provider_name)
            cls._current_provider_name = provider_name
            cls._current_key_index = 0
            
        if not cls._available_keys:
            raise ValueError(f"API ключи для {provider_name} не заданы! Проверьте настройки API.")
            
        if cls._current_key_index >= len(cls._available_keys):
            cls._current_key_index = 0
            
        key_to_use = cls._available_keys[cls._current_key_index]
        comment = cls._key_comments.get(key_to_use, "")
        
        comment_text = f" [{comment}]" if comment else ""
        masked_key = f"{key_to_use[:6]}...{key_to_use[-4:]}" if len(key_to_use) > 10 else "***"
        
        if comment == "Основной ключ (Фоллбэк)":
            log_msg = f"Провайдер векторизации: {provider_name} (⚠️ Используется {comment_text}: {masked_key})"
        else:
            log_msg = f"Провайдер векторизации: {provider_name} (Резервный ключ {cls._current_key_index + 1}/{len(cls._available_keys)}{comment_text}: {masked_key})"
        
        if provider_name == "Gemini":
            provider = GeminiEmbedding(key_to_use)
            provider.api_key = key_to_use # Пробрасываем ключ для воркера
            return provider, log_msg
            
        raise NotImplementedError(f"Провайдер эмбеддингов '{provider_name}' пока не реализован.")

    @classmethod
    def switch_to_next_key(cls):
        """Возвращает True, если есть следующий ключ в пуле, и переключается на него."""
        if not cls._available_keys:
            return False
        if cls._current_key_index < len(cls._available_keys) - 1:
            cls._current_key_index += 1
            return True
        return False