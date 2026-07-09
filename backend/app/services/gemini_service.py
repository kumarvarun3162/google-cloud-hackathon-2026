"""
gemini_service.py — All Gemini API calls for Phase 1 + Phase 2.

SDK: google-genai (new, replaces deprecated google-generativeai)
Model: gemini-1.5-flash — free on Google AI Studio (15 RPM, 1M TPM, 1500 RPD)
Get key (no payment): https://aistudio.google.com/app/apikey

Design:
  - Every prompt enforces a strict JSON schema → deterministic output shape.
  - temperature=0.1 → minimal randomness.
  - Silent fallback on every call → frontend always gets valid structured data.
  - Confidence self-reporting in prompts → UI can show override buttons.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import AsyncGenerator

from google import genai
from google.genai import types

from app.models.schemas import (
    ExtractedIssue,
    IssueCategory,
    ProcessingFlag,
    TranslationResult,
)
from app.utils.confidence import guardrail_check, make_annotation, score_to_level
from app.utils.config import get_settings

logger = logging.getLogger(__name__)

# ── Fallback rules ────────────────────────────────────────────────────────────

_FALLBACK_RULES: list[tuple[list[str], IssueCategory]] = [
    (["road", "pothole", "highway", "bridge", "sarak"],         IssueCategory.ROAD),
    (["water", "pipe", "supply", "pani", "sewage", "nali"],     IssueCategory.WATER),
    (["school", "teacher", "education", "class", "vidyalaya"],  IssueCategory.SCHOOL),
    (["hospital", "health", "doctor", "clinic", "medicine"],    IssueCategory.HEALTH),
    (["light", "electricity", "power", "bijli", "transformer"], IssueCategory.ELECTRICITY),
    (["toilet", "sanitation", "garbage", "cleanliness"],        IssueCategory.SANITATION),
    (["train", "bus", "transport"],                             IssueCategory.PUBLIC_TRANSPORT),
    (["farm", "crop", "irrigation", "kisan", "agriculture"],    IssueCategory.AGRICULTURE),
    (["house", "housing", "shelter", "awas"],                   IssueCategory.HOUSING),
    (["skill", "vocational", "training", "job", "employment"],  IssueCategory.VOCATIONAL),
]


def _rule_based_category(text: str) -> tuple[IssueCategory, float]:
    lower = text.lower()
    for keywords, category in _FALLBACK_RULES:
        if any(kw in lower for kw in keywords):
            return category, 0.45
    return IssueCategory.OTHER, 0.30


# ── Prompts ───────────────────────────────────────────────────────────────────

_TRANSLATION_PROMPT = """
Analyse this citizen submission text and return ONLY a JSON object — no markdown, no explanation.

Text: {text}

Return exactly:
{{
  "detected_language": "<BCP-47 code e.g. hi, en, te, pa, mr, bn>",
  "detected_language_name": "<full name in English>",
  "translated_text": "<English translation, or null if already English>",
  "translation_confidence": <float 0.0-1.0>,
  "is_english": <true|false>
}}
"""

_EXTRACTION_PROMPT = """
You are an AI analyst helping an Indian MP categorise citizen development requests.

Input (English): {english_text}
Original language: {language}
Constituency: {constituency}

Extract all distinct development issues. Return ONLY JSON.

Valid categories: road, water, school, health, electricity, sanitation,
vocational_training, agriculture, housing, public_transport, other

{{
  "issues": [
    {{
      "description": "<concise 1-sentence problem description>",
      "category": "<category>",
      "category_confidence": <float 0.0-1.0>,
      "location_hint": "<location mentioned or null>",
      "severity_hint": "<urgent|moderate|chronic|null>"
    }}
  ],
  "overall_confidence": <float 0.0-1.0>
}}

Rules:
- Only give 0.9+ confidence if the issue is crystal clear.
- severity_hint = "urgent" only if words like "immediately", "accident", "dying" appear.
- Do not invent locations not mentioned in text.
"""

_AUDIO_PROMPT = """
Transcribe this Indian citizen audio message (may be Hindi, English, Telugu, Punjabi, Marathi, Bengali or mixed).
Return ONLY JSON:
{{
  "transcript": "<verbatim transcription>",
  "transcription_confidence": <float 0.0-1.0>,
  "detected_language": "<BCP-47>",
  "detected_language_name": "<language name>"
}}
"""

_IMAGE_PROMPT = """
Analyse this photo submitted to an Indian MP's grievance portal (likely shows a civic problem).
Return ONLY JSON:
{{
  "description": "<objective description of the civic issue visible>",
  "inferred_category": "<road|water|school|health|electricity|sanitation|other>",
  "category_confidence": <float 0.0-1.0>,
  "location_clues": "<any location hints visible or null>",
  "severity_hint": "<urgent|moderate|chronic|null>",
  "analysis_confidence": <float 0.0-1.0>
}}
"""


# ── GeminiService ─────────────────────────────────────────────────────────────

class GeminiService:

    def __init__(self) -> None:
        cfg = get_settings()
        self._client = genai.Client(api_key=cfg.gemini_api_key)
        self._model  = cfg.gemini_model
        self._gen_cfg = types.GenerateContentConfig(
            temperature=0.1,
            top_p=0.8,
            max_output_tokens=2048,
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="BLOCK_ONLY_HIGH",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="BLOCK_ONLY_HIGH",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_ONLY_HIGH",
                ),
            ],
        )
        logger.info(f"GeminiService ready — model: {self._model}")

    def _parse(self, raw: str, fallback: dict) -> dict:
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"JSON parse failed. Using fallback. Raw: {raw[:200]}")
            return fallback

    def _generate(self, prompt: str) -> str:
        """Synchronous generate call."""
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._gen_cfg,
        )
        return response.text

    # ── Translation ───────────────────────────────────────────────────────────

    async def translate_and_detect(
        self, text: str
    ) -> tuple[TranslationResult, list[ProcessingFlag]]:
        flags: list[ProcessingFlag] = []
        fallback = TranslationResult(
            original_text=text,
            detected_language="en",
            detected_language_name="English",
            translated_text=None,
            translation_confidence=0.40,
        )
        try:
            raw  = self._generate(_TRANSLATION_PROMPT.format(text=text[:3000]))
            data = self._parse(raw, {
                "detected_language": "en", "detected_language_name": "English",
                "translated_text": None, "translation_confidence": 0.40,
            })
            result = TranslationResult(
                original_text=text,
                detected_language=data.get("detected_language", "en"),
                detected_language_name=data.get("detected_language_name", "English"),
                translated_text=data.get("translated_text"),
                translation_confidence=float(data.get("translation_confidence", 0.40)),
            )
            if result.translated_text:
                flags.append(ProcessingFlag.TRANSLATION_USED)
            return result, flags
        except Exception as e:
            logger.error(f"Translation failed: {e}. Silent fallback.")
            flags.append(ProcessingFlag.SILENT_FALLBACK)
            return fallback, flags

    # ── Issue extraction ──────────────────────────────────────────────────────

    async def extract_issues(
        self, english_text: str, language: str, constituency: str
    ) -> tuple[list[ExtractedIssue], float, list[ProcessingFlag]]:
        flags: list[ProcessingFlag] = []
        triggered, _ = guardrail_check(english_text)
        if triggered:
            flags.append(ProcessingFlag.CONTENT_GUARDRAIL_HIT)
            return [], 0.0, flags

        try:
            raw  = self._generate(_EXTRACTION_PROMPT.format(
                english_text=english_text[:4000],
                language=language,
                constituency=constituency,
            ))
            data = self._parse(raw, {"issues": [], "overall_confidence": 0.0})

            issues: list[ExtractedIssue] = []
            for ri in data.get("issues", []):
                try:
                    cat = IssueCategory(ri.get("category", "other"))
                except ValueError:
                    cat = IssueCategory.OTHER
                conf = float(ri.get("category_confidence", 0.5))
                issues.append(ExtractedIssue(
                    description=ri.get("description", english_text[:100]),
                    category=make_annotation(cat.value, conf),
                    location_hint=ri.get("location_hint"),
                    severity_hint=ri.get("severity_hint"),
                ))

            overall = float(data.get("overall_confidence", 0.5))
            return issues, overall, flags

        except Exception as e:
            logger.error(f"Issue extraction failed: {e}. Rule-based fallback.")
            flags.append(ProcessingFlag.SILENT_FALLBACK)
            cat, conf = _rule_based_category(english_text)
            return [ExtractedIssue(
                description=english_text[:200],
                category=make_annotation(cat.value, conf),
            )], conf, flags

    # ── Audio transcription ───────────────────────────────────────────────────

    async def transcribe_audio(
        self, audio_bytes: bytes, mime_type: str
    ) -> tuple[str, str, str, float, list[ProcessingFlag]]:
        flags = [ProcessingFlag.AUDIO_TRANSCRIBED]
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    _AUDIO_PROMPT,
                ],
                config=self._gen_cfg,
            )
            data = self._parse(response.text, {
                "transcript": "[Transcription unavailable]",
                "transcription_confidence": 0.20,
                "detected_language": "en",
                "detected_language_name": "English",
            })
            transcript = data.get("transcript", "[Transcription unavailable]")
            confidence = float(data.get("transcription_confidence", 0.20))
            if confidence < get_settings().confidence_threshold_low:
                flags.append(ProcessingFlag.LOW_CONFIDENCE)
            return (
                transcript,
                data.get("detected_language", "en"),
                data.get("detected_language_name", "English"),
                confidence,
                flags,
            )
        except Exception as e:
            logger.error(f"Audio transcription failed: {e}.")
            flags.append(ProcessingFlag.SILENT_FALLBACK)
            return "[Transcription unavailable — please re-submit as text]", "en", "English", 0.0, flags

    # ── Image analysis ────────────────────────────────────────────────────────

    async def analyse_image(
        self, image_bytes: bytes, mime_type: str
    ) -> tuple[str, IssueCategory, float, str | None, str | None, list[ProcessingFlag]]:
        flags = [ProcessingFlag.IMAGE_ANALYSED]
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    _IMAGE_PROMPT,
                ],
                config=self._gen_cfg,
            )
            data = self._parse(response.text, {
                "description": "Image could not be analysed",
                "inferred_category": "other",
                "category_confidence": 0.20,
                "location_clues": None,
                "severity_hint": None,
                "analysis_confidence": 0.20,
            })
            try:
                cat = IssueCategory(data.get("inferred_category", "other"))
            except ValueError:
                cat = IssueCategory.OTHER

            confidence = float(data.get("analysis_confidence", 0.20))
            if confidence < get_settings().confidence_threshold_low:
                flags.append(ProcessingFlag.LOW_CONFIDENCE)

            return (
                data.get("description", ""),
                cat,
                confidence,
                data.get("location_clues"),
                data.get("severity_hint"),
                flags,
            )
        except Exception as e:
            logger.error(f"Image analysis failed: {e}.")
            flags.append(ProcessingFlag.SILENT_FALLBACK)
            return "Image analysis unavailable", IssueCategory.OTHER, 0.0, None, None, flags

    # ── Streaming ─────────────────────────────────────────────────────────────

    async def stream_extraction(self, prompt: str) -> AsyncGenerator[str, None]:
        try:
            for chunk in self._client.models.generate_content_stream(
                model=self._model,
                contents=prompt,
                config=self._gen_cfg,
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            yield ""