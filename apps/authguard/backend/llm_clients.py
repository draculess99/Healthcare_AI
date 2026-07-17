from __future__ import annotations

import json
import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

# Curated text-capable choices. Environment defaults are inserted into the UI even
# when they are not in these lists, so model changes do not require a code edit.
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
]

GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-1.0-pro",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
]


def get_model_choices(provider: str) -> list[str]:
    normalized = (provider or "").strip().lower()
    if normalized.startswith("groq"):
        configured = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        choices = [configured, *GROQ_MODELS]
    elif normalized.startswith("gemini"):
        configured = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
        choices = [configured, *GEMINI_MODELS]
    else:
        return []
    return list(dict.fromkeys(choice for choice in choices if choice))


def local_explanation(context: dict[str, Any]) -> str:
    decision = context.get("decision", "HUMAN_REVIEW_REQUIRED")
    risk = context.get("risk_level", "Unknown")
    blockers = context.get("blockers", [])
    warnings = context.get("warnings", [])
    evidence = []
    if blockers:
        evidence.append("blocking items: " + "; ".join(blockers[:3]))
    if warnings:
        evidence.append("review warnings: " + "; ".join(warnings[:3]))
    detail = " ".join(evidence) or "the structured checks did not identify a blocking defect"
    return (
        f"The committee routed this case to {decision}. The XGBoost risk band is {risk}, and {detail}. "
        "This explanation is advisory; the deterministic rules and human-review gate control the workflow."
    )


def call_groq(prompt: str, model: str | None = None) -> tuple[str, str, dict[str, int] | None]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    selected_model = (model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")).strip()
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": selected_model,
            "temperature": 0.15,
            "max_tokens": 700,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful, conversational AI assistant explaining a prior-authorization decision-support result. "
                        "Provide a natural, verbose, and human-like explanation. "
                        "Never change the supplied decision, invent policy, provide medical advice, or claim an authorization was submitted or approved."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    usage = payload.get("usage", {})
    usage_dict = {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    } if usage else None
    return payload["choices"][0]["message"]["content"].strip(), selected_model, usage_dict


def call_gemini(prompt: str, model: str | None = None) -> tuple[str, str, dict[str, int] | None]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    selected_model = (model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")).strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent?key={api_key}"
    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "system_instruction": {
                "parts": [{
                    "text": (
                        "Explain the supplied prior-authorization decision-support result. Do not modify the decision, "
                        "invent policy, provide medical advice, or state that a request was submitted or approved."
                    )
                }]
            },
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.15, "maxOutputTokens": 700},
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    usage = payload.get("usageMetadata", {})
    usage_dict = {
        "prompt_tokens": usage.get("promptTokenCount", 0),
        "completion_tokens": usage.get("candidatesTokenCount", 0),
        "total_tokens": usage.get("totalTokenCount", 0),
    } if usage else None
    return payload["candidates"][0]["content"]["parts"][0]["text"].strip(), selected_model, usage_dict


def generate_explanation(
    provider: str,
    context: dict[str, Any],
    model: str | None = None,
) -> tuple[str, str | None, str, dict[str, int] | None]:
    normalized_provider = (provider or "Local Expert System").lower()
    prompt = (
        "Create a detailed committee explanation from this immutable structured result. "
        "Mention the strongest supporting and opposing evidence and the reason for human review when applicable.\n\n"
        + json.dumps(context, indent=2, default=str)
    )
    try:
        if normalized_provider.startswith("groq"):
            text, selected_model, usage = call_groq(prompt, model=model)
            return text, None, selected_model, usage
        if normalized_provider.startswith("gemini"):
            text, selected_model, usage = call_gemini(prompt, model=model)
            return text, None, selected_model, usage
        return local_explanation(context), None, "deterministic-local", None
    except Exception as exc:
        fallback_model = model or "unavailable"
        return (
            local_explanation(context),
            f"LLM provider unavailable; local explanation used: {exc}",
            fallback_model,
            None,
        )
