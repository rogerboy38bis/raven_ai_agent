"""
MiniMax LLM Provider - The Jewel of the Crown 👑
https://api.minimax.chat/

Models:
- abab6.5s-chat - Latest flagship model (MiniMax-Text-01)
- abab6.5g-chat - General purpose
- abab5.5-chat - Legacy model

Special Features:
- Excellent Chinese language support
- Voice synthesis integration (T2A)
- Long context (up to 1M tokens with abab6.5s)
- Very competitive pricing
"""

import frappe
import httpx
from typing import Dict, List, Optional, Generator
from .base import LLMProvider
from ._secrets import resolve_secret


class MiniMaxProvider(LLMProvider):
    """
    MiniMax API Provider - Chinese AI Powerhouse
    
    Features:
    - 1M token context window (abab6.5s)
    - Excellent Chinese/English bilingual
    - Voice synthesis built-in
    - Competitive pricing
    - Good for business applications
    """
    
    name = "minimax"
    BASE_URL = "https://api.minimax.io/v1"
    
    MODELS = {
        "MiniMax-M2": "Agentic capabilities, Advanced reasoning",
        "MiniMax-M2-Stable": "High concurrency and commercial use",
        "MiniMax-M2.1": "Coding Plan model - polyglot programming mastery",
    }
    
    PRICING = {
        "MiniMax-M2": {"input": 1.00, "output": 4.00},
        "MiniMax-M2-Stable": {"input": 1.00, "output": 4.00},
        "MiniMax-M2.1": {"input": 0, "output": 0},  # Included in Coding Plan
    }
    
    DEFAULT_MODEL = "MiniMax-M2.1"  # Default to Coding Plan model
    
    def __init__(self, settings: Dict):
        super().__init__(settings)

        # Prefer Coding Plan key (sk-cp-...) when available; fall back to regular.
        api_key = resolve_secret(
            settings,
            env_vars=(
                "RAVEN_MINIMAX_CP_KEY", "MINIMAX_CP_KEY",
                "RAVEN_MINIMAX_API_KEY", "MINIMAX_API_KEY",
            ),
            site_config_keys=(
                "minimax_cp_key", "MINIMAX_CP_KEY",
                "minimax_api_key", "MINIMAX_API_KEY",
            ),
            db_field="minimax_cp_key",
            settings_keys=("minimax_cp_key", "minimax_api_key"),
            label="MiniMax API key (CP or regular)",
            required=False,
        )
        if not api_key:
            # Try the regular key field if the CP field is empty in DB.
            api_key = resolve_secret(
                settings,
                env_vars=("RAVEN_MINIMAX_API_KEY", "MINIMAX_API_KEY"),
                site_config_keys=("minimax_api_key", "MINIMAX_API_KEY"),
                db_field="minimax_api_key",
                settings_keys=("minimax_api_key",),
                label="MiniMax API key",
            )

        # group_id is not encrypted, so it's safe to read from settings/conf directly.
        group_id = (
            settings.get("minimax_group_id")
            or settings.get("MINIMAX_GROUP_ID")
            or (frappe.conf.get("MINIMAX_GROUP_ID") if hasattr(frappe, "conf") else None)
            or "0"
        )

        self.api_key = api_key
        self.group_id = group_id
        # Use M2.1 for Coding Plan keys (sk-cp-), M2 for regular keys
        default = "MiniMax-M2.1" if api_key.startswith("sk-cp-") else "MiniMax-M2"
        self.default_model = settings.get("minimax_model") or default
        self.model = self.default_model
    
    def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> str:
        """Send chat request to MiniMax API using OpenAI-compatible endpoint"""
        model = model or self.default_model
        
        # Use OpenAI-compatible endpoint (simpler format)
        url = f"{self.BASE_URL}/chat/completions"
        
        # Standard OpenAI format - filter out empty messages
        # MiniMax doesn't support multiple system messages, so merge them
        formatted_messages = []
        system_content = []
        
        for m in messages:
            content = m.get("content", "")
            if not content or not content.strip():
                continue
            
            if m["role"] == "system":
                system_content.append(content)
            else:
                formatted_messages.append({
                    "role": m["role"],
                    "content": content
                })
        
        # Add merged system message at the beginning
        if system_content:
            formatted_messages.insert(0, {
                "role": "system",
                "content": "\n\n".join(system_content)
            })
        
        # Ensure at least one user message exists
        if not any(m["role"] == "user" for m in formatted_messages):
            formatted_messages.append({"role": "user", "content": "Hello"})
        
        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Debug logging
        frappe.logger().debug(f"[MiniMax] Request URL: {url}")
        frappe.logger().debug(f"[MiniMax] Payload: {payload}")
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
            # Log response for debugging
            if response.status_code != 200:
                frappe.logger().error(f"[MiniMax] Error {response.status_code}: {response.text}")
            
            response.raise_for_status()
            data = response.json()
            
            # Check for API-level errors
            if "error" in data:
                raise Exception(f"MiniMax API error: {data['error']}")
            
            return data["choices"][0]["message"]["content"]
    
    def chat_stream(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Generator[str, None, None]:
        """Stream response from MiniMax using OpenAI-compatible endpoint"""
        model = model or self.default_model
        
        with httpx.Client(timeout=60.0) as client:
            url = f"{self.BASE_URL}/chat/completions"
            with client.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
                    "temperature": temperature,
                    "max_completion_tokens": max_tokens,
                    "stream": True
                }
            ) as response:
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        import json
                        chunk = line[6:]
                        if chunk.strip() == "[DONE]":
                            break
                        data = json.loads(chunk)
                        if data.get("choices"):
                            delta = data["choices"][0].get("delta", {})
                            if delta.get("content"):
                                yield delta["content"]
    
    def text_to_speech(
        self,
        text: str,
        voice_id: str = "male-qn-qingse",
        speed: float = 1.0
    ) -> bytes:
        """
        Convert text to speech using MiniMax T2A
        
        Voice IDs:
        - male-qn-qingse: Young male
        - female-shaonv: Young female
        - female-yujie: Mature female
        - male-qn-jingying: Professional male
        """
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.BASE_URL}/t2a_v2",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "speech-01-turbo",
                    "text": text,
                    "voice_setting": {
                        "voice_id": voice_id,
                        "speed": speed
                    },
                    "audio_setting": {
                        "format": "mp3",
                        "sample_rate": 32000
                    }
                }
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Decode base64 audio
            import base64
            return base64.b64decode(data["data"]["audio"])
    
    def get_pricing(self, model: str = None) -> Dict[str, float]:
        """Get pricing for model"""
        model = model or self.default_model
        return self.PRICING.get(model, {"input": 0, "output": 0})
    
    def get_default_model(self) -> str:
        return self.default_model
    
    @classmethod
    def get_available_voices(cls) -> Dict[str, str]:
        """List available TTS voices"""
        return {
            "male-qn-qingse": "Young Male (清澈)",
            "female-shaonv": "Young Female (少女)",
            "female-yujie": "Mature Female (御姐)",
            "male-qn-jingying": "Professional Male (精英)",
            "male-qn-badao": "Authoritative Male (霸道)",
            "female-tianmei": "Sweet Female (甜美)",
        }
