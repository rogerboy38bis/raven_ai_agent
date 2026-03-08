import frappe
import requests
import platform
import psutil
from datetime import datetime


def get_ollama_config():
    """Get Ollama configuration from IoT Ollama Settings DocType."""
    try:
        from raven_ai_agent.raven_ai_agent.doctype.iot_ollama_settings.iot_ollama_settings import IoTOllamaSettings
        return IoTOllamaSettings.get_settings()
    except Exception:
        return {
            "enabled": True,
            "ollama_url": "http://localhost:11434",
            "default_model": "tinyllama",
            "request_timeout": 120,
            "bot_mention_trigger": "iot",
            "bot_description": "IoT Ollama AI Bot",
        }


class IoTAgent:
    """IoT Agent - Ollama AI integration for educational IoT project.
    Reads configuration from IoT Ollama Settings DocType."""

    def __init__(self, user=None):
        self.user = user or frappe.session.user
        config = get_ollama_config()
        self.ollama_url = config["ollama_url"]
        self.model = config["default_model"]
        self.timeout = config["request_timeout"]
        self.enabled = config["enabled"]

    def process_command(self, query):
        """Route IoT commands."""
        if not self.enabled:
            return {"success": False, "error": "IoT Ollama bot is disabled. Enable it in IoT Ollama Settings."}
        query = query.strip()
        cmd = query.lower()
        if cmd in ("help", ""):
            return self._help()
        elif cmd.startswith("ask "):
            return self._ask_ollama(query[4:].strip())
        elif cmd == "status":
            return self._ollama_status()
        elif cmd == "models":
            return self._ollama_status()
        elif cmd.startswith("pull "):
            return self._pull_model(cmd[5:].strip())
        elif cmd == "sysinfo":
            return self._system_info()
        else:
            return self._ask_ollama(query)

    def _help(self):
        h = "## IoT Bot Commands\n\n"
        h += "| Command | Description |\n|---------|-------------|\n"
        h += "| `@iot ask <prompt>` | Ask Ollama AI |\n"
        h += "| `@iot status` | Ollama service status |\n"
        h += "| `@iot models` | List available models |\n"
        h += "| `@iot pull <model>` | Pull a new model |\n"
        h += "| `@iot sysinfo` | VPS system info |\n"
        h += "| `@iot <anything>` | Direct AI query |\n"
        return {"success": True, "response": h}

    def _ask_ollama(self, prompt):
        """Send prompt to Ollama and return response."""
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("response", "No response")
            dur = data.get("total_duration", 0) / 1e9
            out = f"**Ollama ({self.model}):**\n\n{answer}"
            if dur > 0:
                out += f"\n\n_Generated in {dur:.1f}s_"
            return {"success": True, "response": out}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": f"⚠️ Ollama service is offline at `{self.ollama_url}`.\n\n"
                    f"To start Ollama on the VPS:\n"
                    f"```\nsudo systemctl start ollama\n# or\nollama serve &\n```\n\n"
                    f"Configure URL in **IoT Ollama Settings** if running on a different host."}
        except requests.exceptions.Timeout:
            return {"success": False, "error": f"Ollama timed out after {self.timeout}s (CPU-only mode can be slow)."}
        except Exception as e:
            return {"success": False, "error": f"Ollama error: {str(e)}"}

    def _ollama_status(self):
        """Check Ollama service status."""
        try:
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            s = "## Ollama Status\n\n"
            s += "| Property | Value |\n|----------|-------|\n"
            s += "| Status | Online |\n"
            s += f"| URL | `{self.ollama_url}` |\n"
            s += f"| Models | {len(models)} |\n"
            s += f"| Default | {self.model} |\n"
            s += "| Server | VPS (CPU-only) |\n"
            if models:
                s += "\n### Available Models\n\n"
                for m in models:
                    sz = m.get("size", 0) / (1024**3)
                    s += f"- **{m["name"]}** ({sz:.1f} GB)\n"
            return {"success": True, "response": s}
        except Exception:
            return {"success": True, "response": "## Ollama Status\n\n| Status | Offline |\n| URL | `" + self.ollama_url + "` |"}

    def _pull_model(self, model_name):
        """Pull a model from Ollama registry."""
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/pull",
                json={"name": model_name, "stream": False},
                timeout=600
            )
            if resp.status_code == 200:
                return {"success": True, "response": f"Model **{model_name}** pulled successfully."}
            return {"success": False, "error": f"Pull failed: {resp.text[:200]}"}
        except Exception as e:
            return {"success": False, "error": f"Pull error: {str(e)}"}

    def _system_info(self):
        """Get VPS system information."""
        try:
            cpu_pct = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            info = "## VPS System Info\n\n"
            info += "| Metric | Value |\n|--------|-------|\n"
            info += f"| Host | {platform.node()} |\n"
            info += f"| OS | {platform.system()} {platform.release()} |\n"
            info += f"| CPU | {cpu_pct}% ({psutil.cpu_count()} cores) |\n"
            info += f"| RAM | {mem.used//(1024**2)}MB / {mem.total//(1024**2)}MB ({mem.percent}%) |\n"
            info += f"| Disk | {disk.used//(1024**3)}GB / {disk.total//(1024**3)}GB ({disk.percent}%) |\n"
            info += f"| Ollama | {self.ollama_url} |\n"
            info += f"| Model | {self.model} |\n"
            return {"success": True, "response": info}
        except Exception as e:
            return {"success": False, "error": f"System info error: {str(e)}"}
