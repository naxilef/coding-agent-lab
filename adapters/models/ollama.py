"""Send prepared chat messages to a local Ollama server."""

from http.client import HTTPConnection
import json
import math
import os


class OllamaClient:
    """Return reply text from Ollama without validating model actions."""

    def __init__(self, model: str | None = None, temperature: float = 0.0) -> None:
        self.model = model or os.environ.get("OLLAMA_MODEL") or "qwen2.5-coder:7b"
        if not math.isfinite(temperature) or temperature < 0:
            raise ValueError("Temperature must be a finite non-negative number")
        self.temperature = temperature

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Request a non-streamed JSON reply and return its unvalidated content."""
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": self.temperature},
        }).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", 11434, timeout=120)
        try:
            connection.request(
                "POST", "/api/chat", body=payload,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            if response.status != 200:
                raise RuntimeError(f"Ollama HTTP {response.status}: {body}")
            envelope = json.loads(body)
            content = envelope.get("message", {}).get("content")
            if not isinstance(content, str):
                raise ValueError("Ollama response is missing message.content text")
            return content
        finally:
            connection.close()
