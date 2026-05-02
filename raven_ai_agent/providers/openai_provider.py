"""
OpenAI LLM Provider (Refactored from original agent.py)
"""

import frappe
from typing import Dict, List, Optional, Generator
from openai import OpenAI
from .base import LLMProvider
from ._secrets import resolve_secret


class OpenAIProvider(LLMProvider):
    """OpenAI API Provider"""
    
    name = "openai"
    
    MODELS = {
        "gpt-4o": "Most capable model",
        "gpt-4o-mini": "Fast and cost-effective",
        "gpt-4-turbo": "Previous generation flagship",
        "gpt-3.5-turbo": "Legacy fast model",
    }
    
    DEFAULT_MODEL = "gpt-4o-mini"
    
    def __init__(self, settings: Dict):
        super().__init__(settings)

        api_key = resolve_secret(
            settings,
            env_vars=("RAVEN_OPENAI_API_KEY", "OPENAI_API_KEY"),
            site_config_keys=("openai_api_key", "OPENAI_API_KEY"),
            db_field="openai_api_key",
            settings_keys=("openai_api_key",),
            label="OpenAI API key",
        )
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key)
        self.default_model = settings.get("model", self.DEFAULT_MODEL)
    
    def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> str:
        model = model or self.default_model
        
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        
        return response.choices[0].message.content
    
    def chat_stream(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Generator[str, None, None]:
        model = model or self.default_model
        
        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def embed(self, text: str) -> List[float]:
        """Generate embedding using text-embedding-3-small"""
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
    
    def get_default_model(self) -> str:
        return self.default_model
