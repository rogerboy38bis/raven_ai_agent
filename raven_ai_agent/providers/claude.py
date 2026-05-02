"""
Claude (Anthropic) LLM Provider
https://docs.anthropic.com/

Models:
- claude-3-5-sonnet-20241022 - Best balance of speed/intelligence
- claude-3-opus-20240229 - Most capable
- claude-3-haiku-20240307 - Fastest, most affordable
"""

import frappe
from typing import Dict, List, Optional, Generator
from .base import LLMProvider
from ._secrets import resolve_secret

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class ClaudeProvider(LLMProvider):
    """
    Anthropic Claude Provider
    
    Features:
    - Constitutional AI (safety-focused)
    - 200K context window
    - Excellent reasoning and coding
    - Tool use / function calling
    """
    
    name = "claude"
    
    MODELS = {
        "claude-3-5-sonnet-20241022": "Best balance - recommended",
        "claude-3-opus-20240229": "Most capable, slower",
        "claude-3-haiku-20240307": "Fastest, cheapest",
        "claude-3-5-haiku-20241022": "Improved Haiku",
    }
    
    # Pricing per 1M tokens (USD)
    PRICING = {
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
        "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    }
    
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
    
    def __init__(self, settings: Dict):
        super().__init__(settings)

        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        api_key = resolve_secret(
            settings,
            env_vars=("RAVEN_CLAUDE_API_KEY", "CLAUDE_API_KEY", "ANTHROPIC_API_KEY"),
            site_config_keys=("claude_api_key", "CLAUDE_API_KEY", "ANTHROPIC_API_KEY"),
            db_field="claude_api_key",
            settings_keys=("claude_api_key",),
            label="Claude API key",
        )
        self.api_key = api_key
        self.client = Anthropic(api_key=api_key)
        self.default_model = settings.get("claude_model", self.DEFAULT_MODEL)
    
    def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> str:
        """Send chat request to Claude API"""
        model = model or self.default_model
        
        # Convert OpenAI format to Claude format
        system_prompt = ""
        claude_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_prompt += msg["content"] + "\n"
            else:
                claude_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt.strip(),
            messages=claude_messages,
            temperature=temperature
        )
        
        return response.content[0].text
    
    def chat_stream(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Generator[str, None, None]:
        """Stream response from Claude"""
        model = model or self.default_model
        
        system_prompt = ""
        claude_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_prompt += msg["content"] + "\n"
            else:
                claude_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        with self.client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt.strip(),
            messages=claude_messages,
            temperature=temperature
        ) as stream:
            for text in stream.text_stream:
                yield text
    
    def get_pricing(self, model: str = None) -> Dict[str, float]:
        """Get pricing for model"""
        model = model or self.default_model
        return self.PRICING.get(model, {"input": 0, "output": 0})
    
    def get_default_model(self) -> str:
        return self.default_model
