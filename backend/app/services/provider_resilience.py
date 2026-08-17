from __future__ import annotations

from app.core.config import get_settings
from app.services.ai_providers import (
    AIProviderError,
    OllamaPlanningProvider,
    OpenAIPlanningProvider,
)


class ProviderResilienceError(Exception):
    pass


def _provider(name: str, settings):
    if name == "openai":
        return OpenAIPlanningProvider(settings)

    if name == "ollama":
        return OllamaPlanningProvider(settings)

    raise ProviderResilienceError(
        f"Unsupported planning AI provider: {name}"
    )


def _provider_order(settings):
    names: list[str] = [settings.ai_provider]

    fallback = settings.ai_fallback_provider

    if fallback and fallback not in names:
        names.append(fallback)

    return [
        _provider(name, settings)
        for name in names
    ]


def generate_with_failover(
    *,
    instructions: str,
    input_text: str,
):
    settings = get_settings()
    errors = []

    for provider in _provider_order(settings):
        try:
            result = provider.generate(
                instructions=instructions,
                input_text=input_text,
            )

            return result, errors

        except AIProviderError as exc:
            errors.append(
                {
                    "provider": provider.name,
                    "error": str(exc),
                }
            )

    raise ProviderResilienceError(str(errors))


def golden_path_contract() -> dict:
    settings = get_settings()

    strategy = [settings.ai_provider]

    if (
        settings.ai_fallback_provider
        and settings.ai_fallback_provider not in strategy
    ):
        strategy.append(settings.ai_fallback_provider)

    return {
        "required_capabilities": [
            "authentication",
            "active_project",
            "active_site",
            "document_evidence",
            "deterministic_gis",
            "planning_run",
            "bounded_tool_registry",
            "grounded_synthesis",
            "map_action",
            "professional_review",
        ],
        "provider_strategy": strategy,
        "satellite_primary": "copernicus_cdse/sentinel-2-l2a",
        "statutory_decision_engine": False,
    }
