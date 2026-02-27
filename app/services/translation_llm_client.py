import os
from typing import Dict, Final

import httpx


TRANSLATION_LLM_BASE_URL: Final[str] = os.getenv("TRANSLATION_LLM_BASE_URL", "http://localhost:11534")
TRANSLATION_LLM_MODEL_NAME: Final[str] = os.getenv("TRANSLATION_LLM_MODEL_NAME", "translategemma")

LANGUAGE_LABELS: Dict[str, str] = {
    "en": "English",
    "pt-BR": "Brazilian Portuguese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "ja": "Japanese",
    "zh-Hans": "Chinese (Simplified)",
}


class TranslationClient:
    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text:
            return ""

        source_label = LANGUAGE_LABELS.get(source_lang, source_lang)
        target_label = LANGUAGE_LABELS.get(target_lang, target_lang)

        prompt = (
            "You are a professional "
            f"{source_label} ({source_lang}) to {target_label} ({target_lang}) translator. "
            "Your goal is to accurately convey the meaning and nuances of the original text "
            "while adhering to the grammar, vocabulary, and cultural sensitivities of the target language. "
            "Preserve all numbers, units, acronyms, and technical terms when appropriate. "
            "If the text is incomplete or illegible, indicate that briefly in the target language without inventing content. "
            f"Produce only the {target_label} translation, without any additional explanations or commentary.\n\n"
            f"Please translate the following {source_label} text into {target_label}:\n\n"
            f"{text}"
        )

        try:
            async with httpx.AsyncClient(base_url=TRANSLATION_LLM_BASE_URL, timeout=120.0) as client:
                response = await client.post(
                    "/api/chat",
                    json={
                        "model": TRANSLATION_LLM_MODEL_NAME,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt,
                            }
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as error:
            return (
                "Falha ao traduzir este trecho com o modelo de tradução. "
                "Mensagem técnica: "
                f"{str(error)}"
            )

        message = data.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content

        content_fallback = data.get("response")
        if isinstance(content_fallback, str):
            return content_fallback

        return "Falha ao interpretar a resposta do modelo durante a tradução deste trecho."

    async def translate_en_to_pt_br(self, text: str) -> str:
        return await self.translate(text=text, source_lang="en", target_lang="pt-BR")
