import requests
from abc import ABC, abstractmethod
from PyQt6.QtCore import QSettings

class AbstractEmbedding(ABC):
    """Абстрактный класс для всех провайдеров векторизации"""
    @abstractmethod
    def get_embedding(self, text: str) -> list[float]:
        pass

class GeminiEmbedding(AbstractEmbedding):
    """Провайдер эмбеддингов для бесплатного/платного API Gemini"""
    def __init__(self, api_key: str):
        self.api_key = api_key
        # ИСПРАВЛЕНИЕ: Актуальная и поддерживаемая модель векторизации
        self.model = "gemini-embedding-001" 

    def get_embedding(self, text: str) -> list[float]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        data = {
            "model": f"models/{self.model}",
            "content": {
                "parts": [{"text": text}]
            }
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
            # Возвращаем массив чисел float (вектор)
            return resp_json["embedding"]["values"]
        except KeyError:
            raise Exception(f"Неожиданный формат ответа эмбеддинга: {resp_json}")

class EmbeddingFactory:
    """Умная фабрика, которая решает, какой ключ взять, и возвращает логи для пользователя"""
    
    @staticmethod
    def get_provider(provider_name="Gemini"):
        settings = QSettings("VibeCoder", "API_Config")
        
        if provider_name == "Gemini":
            # 1. Сначала ищем специализированный ключ для RAG
            emb_key = settings.value("gemini_embedding_key", "").strip()
            # 2. Если его нет, падаем на основной ключ
            main_key = settings.value("gemini_api_key", "").strip()
            
            key_to_use = emb_key if emb_key else main_key
            
            if not key_to_use:
                raise ValueError("API ключи для Gemini не заданы! Проверьте настройки API.")
                
            # Формируем прозрачный лог для пользователя
            key_type = "Специализированный Embedding ключ" if emb_key else "Основной ключ генерации"
            masked_key = f"{key_to_use[:6]}...{key_to_use[-4:]}" if len(key_to_use) > 10 else "***"
            
            log_msg = f"Провайдер векторизации: Gemini ({key_type}: {masked_key})"
            
            return GeminiEmbedding(key_to_use), log_msg
            
        # Задел на будущее (OpenAI / Локальные модели)
        raise NotImplementedError(f"Провайдер эмбеддингов '{provider_name}' пока не реализован.")