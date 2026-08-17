from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import Settings


class AIProviderError(Exception):
    pass


@dataclass(frozen=True)
class AITextResult:
    text: str
    provider: str
    model: str


class OpenAIPlanningProvider:
    name = "openai"

    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
    ) -> AITextResult:
        if not self.settings.openai_api_key:
            raise AIProviderError(
                "OPENAI_API_KEY is not configured.",
            )

        model = getattr(
            self.settings,
            "openai_planning_model",
            "gpt-5.6-luna",
        )

        try:
            response = httpx.post(
                f"{self.settings.openai_base_url.rstrip('/')}/responses",
                headers={
                    "Authorization": (
                        f"Bearer {self.settings.openai_api_key}"
                    ),
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "instructions": instructions,
                    "input": input_text,
                },
                timeout=90,
            )

            response.raise_for_status()
            data = response.json()

            text = data.get("output_text")

            if not text:
                parts: list[str] = []

                for item in data.get("output", []):
                    for content in item.get(
                        "content",
                        [],
                    ):
                        if (
                            content.get("type")
                            == "output_text"
                        ):
                            parts.append(
                                content.get(
                                    "text",
                                    "",
                                )
                            )

                text = "\n".join(parts)

            if not text:
                raise AIProviderError(
                    "OpenAI returned no text output.",
                )

            return AITextResult(
                text=text,
                provider="openai",
                model=model,
            )

        except AIProviderError:
            raise

        except Exception as exc:
            raise AIProviderError(
                "OpenAI Planning Provider unavailable.",
            ) from exc


class OllamaPlanningProvider:
    name = "ollama"

    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
    ) -> AITextResult:
        model = getattr(
            self.settings,
            "ollama_planning_model",
            "qwen3:8b",
        )

        try:
            response = httpx.post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "messages": [
                        {
                            "role": "system",
                            "content": instructions,
                        },
                        {
                            "role": "user",
                            "content": input_text,
                        },
                    ],
                },
                timeout=300,
            )

            response.raise_for_status()

            text = (
                response.json()
                .get("message", {})
                .get("content", "")
                .strip()
            )

            if not text:
                raise AIProviderError(
                    "Ollama returned no text output.",
                )

            return AITextResult(
                text=text,
                provider="ollama",
                model=model,
            )

        except AIProviderError:
            raise

        except Exception as exc:
            raise AIProviderError(
                "Ollama Planning Provider unavailable.",
            ) from exc