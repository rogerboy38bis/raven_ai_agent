"""
DeepSeek LLM Provider
https://platform.deepseek.com/

Models:
- deepseek-chat (DeepSeek-V3) - General purpose, very cost-effective
- deepseek-reasoner (DeepSeek-R1) - Enhanced reasoning with chain-of-thought

API is OpenAI-compatible, making integration straightforward.
"""

import frappe
from typing import Dict, List, Optional, Generator
from openai import OpenAI
from .base import LLMProvider
from ._secrets import resolve_secret


class DeepSeekProvider(LLMProvider):
    """
    DeepSeek API Provider
    
    Features:
    - OpenAI-compatible API
    - Very cost-effective ($0.14/1M input, $0.28/1M output for deepseek-chat)
    - Strong reasoning capabilities
    - Good for code generation
    """
    
    name = "deepseek"
    BASE_URL = "https://api.deepseek.com"
    
    # Available models
    MODELS = {
        "deepseek-chat": "General purpose chat model (DeepSeek-V3)",
        "deepseek-reasoner": "Enhanced reasoning with chain-of-thought (DeepSeek-R1)",
    }
    
    DEFAULT_MODEL = "deepseek-chat"
    
    def __init__(self, settings: Dict):
        super().__init__(settings)

        api_key = resolve_secret(
            settings,
            env_vars=("RAVEN_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"),
            site_config_keys=("deepseek_api_key", "DEEPSEEK_API_KEY"),
            db_field="deepseek_api_key",
            settings_keys=("deepseek_api_key",),
            label="DeepSeek API key",
        )
        self.api_key = api_key

        # Use OpenAI client with DeepSeek base URL
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.BASE_URL,
        )
        
        self.default_model = settings.get("deepseek_model") or self.DEFAULT_MODEL
        self.model = self.default_model
    
    def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> str:
        """
        Send chat request to DeepSeek API
        
        Args:
            messages: Conversation messages
            model: Model to use (deepseek-chat or deepseek-reasoner)
            temperature: Sampling temperature
            max_tokens: Max response tokens
            stream: Whether to stream (use chat_stream instead)
            
        Returns:
            Response text
        """
        model = model or self.default_model
        
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            frappe.logger().error(f"[DeepSeek] API error: {str(e)}")
            raise
    
    def chat_stream(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Generator[str, None, None]:
        """
        Stream chat response from DeepSeek
        
        Yields:
            Response text chunks
        """
        model = model or self.default_model
        
        try:
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
                    
        except Exception as e:
            frappe.logger().error(f"[DeepSeek] Stream error: {str(e)}")
            raise
    
    def chat_with_reasoning(
        self,
        messages: List[Dict],
        temperature: float = 0.3,
        max_tokens: int = 4000
    ) -> Dict[str, str]:
        """
        Use DeepSeek-R1 for enhanced reasoning
        Returns both reasoning process and final answer
        
        Returns:
            {
                "reasoning": "Step-by-step thought process...",
                "answer": "Final answer..."
            }
        """
        response = self.client.chat.completions.create(
            model="deepseek-reasoner",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        
        content = response.choices[0].message.content
        reasoning_content = getattr(response.choices[0].message, 'reasoning_content', '')
        
        return {
            "reasoning": reasoning_content or "",
            "answer": content
        }
    
    def get_default_model(self) -> str:
        return self.default_model
    
    @classmethod
    def get_available_models(cls) -> Dict[str, str]:
        """List available DeepSeek models"""
        return cls.MODELS
