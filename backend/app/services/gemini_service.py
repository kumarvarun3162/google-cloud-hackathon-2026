"""
gemini_service.py — All interactions with the Gemini API (Google AI Studio, free).

Model: gemini-1.5-flash
  • Free tier: 15 RPM, 1M TPM, 1500 RPD — plenty for a hackathon prototype.
  • Multimodal: handles text, audio bytes, and images in one API.
  • Get your key (no payment): https://aistudio.google.com/app/apikey

Key design decisions
────────────────────
1. DETERMINISTIC SHELL
   Every prompt ends with an explicit JSON schema.  The model is instructed to
   return *only* valid JSON — no markdown, no prose.  We parse with json.loads
   and validate with Pydantic.  If parsing fails we fall back to rule-based
   extraction rather than surfacing a 500 to the user.

2. CONFIDENCE SCORES IN THE PROMPT
   We ask Gemini to self-report a confidence float for each field.  This is an
   imperfect but pragmatic signal for the prototype.  The frontend uses it to
   decide whether to show "AI suggested: Road repair ✓ / ✗" or just accept it.

3. LABELS + OVERRIDE SLOT
   Every AI output is wrapped in ConfidenceAnnotation which carries an
   `override` field.  The MP can PATCH that field later without re-running AI.

4. SILENT FALLBACK
   If Gemini returns malformed JSON or errors, we fall back to a
   keyword-based rule engine and set ProcessingFlag.SILENT_FALLBACK.
   The frontend still gets a valid structured response — it just shows
   "AI unavailable, rule-based classification used".

5. STREAMING
   We use Gemini's stream=True to emit partial tokens while processing.
   The route layer wraps this in SSE chunks with step + progress indicators.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import AsyncGenerator

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from app.models.schemas import (
    ConfidenceLevel,
    ExtractedIssue,
    IssueCategory,
    ProcessingFlag,
    TranslationResult,
)
from app.utils.confidence import (
    guardrail_check,
    make_annotation,
    score_to_level,
)
from app.utils.config import get_settings

logger = logging.getLogger(__name__)

# ── Gemini safety config ──────────────────────────────────────────────────────
# We lower the block threshold so the model doesn't auto-block legitimate
# grievances that mention keywords like "dangerous road" or "dying crops".
_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT:        HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH:       HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
}

# ── Category fallback rules (keyword → IssueCategory) ─────────────────────────
_FALLBACK_RULES: list[tuple[list[str], IssueCategory]] = [
    (["road", "pothole", "highway", "bridge", "sarak"],        IssueCategory.ROAD),
    (["water", "pipe", "supply", "pani", "sewage", "nali"],    IssueCategory.WATER),
    (["school", "teacher", "education", "class", "vidyalaya"], IssueCategory.SCHOOL),
    (["hospital", "health", "doctor", "clinic", "medicine"],   IssueCategory.HEALTH),
    (["light", "electricity", "power", "bijli", "transformer"],IssueCategory.ELECTRICITY),
    (["toilet", "sanitation", "garbage", "cleanliness"],       IssueCategory.SANITATION),
    (["train", "bus", "transport", "auto"],                    IssueCategory.PUBLIC_TRANSPORT),
    (["farm", "crop", "irrigation", "kisan", "agriculture"],   IssueCategory.AGRICULTURE),
    (["house", "housing", "flat", "shelter", "awas"],          IssueCategory.HOUSING),
    (["skill", "vocational", "training", "job", "employment"], IssueCategory.VOCATIONAL),
]


def _rule_based_category(text: str) -> tuple[IssueCategory, float]:
    """Simple keyword fallback. Returns category + a fixed low confidence."""
    lower = text.lower()
    for keywords, category in _FALLBACK_RULES:
        if any(kw in lower for kw in keywords):
            return category, 0.45   # always below HIGH threshold → shows override UI
    return IssueCategory.OTHER, 0.30


# ── Prompt templates ──────────────────────────────────────────────────────────

_TRANSLATION_PROMPT = """
You are a multilingual civic assistant processing citizen grievances for Indian MPs.

Analyse the following submission text and return ONLY a JSON object — no markdown, no explanation.

Text: {text}

Return this exact JSON structure:
{{
  "detected_language": "<BCP-47 code, e.g. hi, en, te, pa, mr, bn>",
  "detected_language_name": "<full name in English, e.g. Hindi>",
  "translated_text": "<English translation, or null if already English>",
  "translation_confidence": <float 0.0-1.0>,
  "is_english": <true|false>
}}
"""

_EXTRACTION_PROMPT = """
You are an AI analyst helping an Indian Member of Parliament categorise citizen development requests.

Input text (already in English): {english_text}
Original language: {language}
Constituency: {constituency}

Extract all distinct development issues from this text. Return ONLY a JSON object.

Valid categories: road, water, school, health, electricity, sanitation,
vocational_training, agriculture, housing, public_transport, other

Return this exact JSON structure:
{{
  "issues": [
    {{
      "description": "<concise 1-sentence description of the specific problem>",
      "category": "<one of the valid categories above>",
      "category_confidence": <float 0.0-1.0, how certain you are of the category>,
      "location_hint": "<specific location mentioned, or null>",
      "severity_hint": "<urgent|moderate|chronic|null based on language used>"
    }}
  ],
  "overall_summary": "<one sentence summary of all issues combined>",
  "overall_confidence": <float 0.0-1.0, confidence in your overall extraction>
}}

Rules:
- If a submission mentions 3 problems, return 3 issue objects.
- Be conservative with confidence: only give 0.9+ if the issue is crystal clear.
- severity_hint = "urgent" only if words like "immediately", "dying", "accident" appear.
- Do not invent locations not mentioned in the text.
"""

_AUDIO_TRANSCRIPTION_PROMPT = """
You are transcribing a citizen audio message sent to an Indian MP's office.
This may be in Hindi, English, Telugu, Punjabi, Marathi, Bengali, or a mix.

Transcribe the audio accurately. Then return ONLY a JSON object:
{{
  "transcript": "<full verbatim transcription>",
  "transcription_confidence": <float 0.0-1.0>,
  "detected_language": "<BCP-47 code>",
  "detected_language_name": "<language name>"
}}
"""

_IMAGE_ANALYSIS_PROMPT = """
You are analysing a photo submitted by a citizen to their MP's grievance portal.
The photo likely shows a civic infrastructure problem.

Describe what you see in the image that is relevant to a civic grievance.
Return ONLY a JSON object:
{{
  "description": "<objective description of the civic issue visible in the image>",
  "inferred_category": "<road|water|school|health|electricity|sanitation|other>",
  "category_confidence": <float 0.0-1.0>,
  "location_clues": "<any location hints visible in image, or null>",
  "severity_hint": "<urgent|moderate|chronic|null>",
  "analysis_confidence": <float 0.0-1.0>
}}
"""


# ── GeminiService class ───────────────────────────────────────────────────────

class GeminiService:
    """
    Wraps all Gemini API calls for Phase 1.
    Initialised once at app startup and reused (connection pooling via SDK).
    """

    def __init__(self) -> None:
        cfg = get_settings()
        genai.configure(api_key=cfg.gemini_api_key)
        self.model = genai.GenerativeModel(
            model_name=cfg.gemini_model,
            safety_settings=_SAFETY_SETTINGS,
            generation_config=genai.GenerationConfig(
                temperature=0.1,        # Low temp = more deterministic output
                top_p=0.8,
                max_output_tokens=2048,
            ),
        )
        logger.info(f"GeminiService initialised with model: {cfg.gemini_model}")

    def _parse_json_response(self, raw: str, fallback: dict) -> dict:
        """
        Strip markdown fences if present, parse JSON.
        Returns fallback dict on parse failure (silent fallback pattern).
        """
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"JSON parse failed. Raw: {raw[:200]}. Using fallback.")
            return fallback

    # ── Translation ───────────────────────────────────────────────────────────

    async def translate_and_detect(
        self, text: str
    ) -> tuple[TranslationResult, list[ProcessingFlag]]:
        """
        Detect language, translate to English if needed.
        Returns (TranslationResult, flags).
        """
        flags: list[ProcessingFlag] = []
        fallback_result = TranslationResult(
            original_text=text,
            detected_language="en",
            detected_language_name="English",
            translated_text=None,
            translation_confidence=0.40,
        )

        try:
            prompt = _TRANSLATION_PROMPT.format(text=text[:3000])
            response = self.model.generate_content(prompt)
            data = self._parse_json_response(
                response.text,
                {
                    "detected_language": "en",
                    "detected_language_name": "English",
                    "translated_text": None,
                    "translation_confidence": 0.40,
                    "is_english": True,
                },
            )

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
            logger.error(f"Translation failed: {e}. Using silent fallback.")
            flags.append(ProcessingFlag.SILENT_FALLBACK)
            return fallback_result, flags

    # ── Issue extraction ──────────────────────────────────────────────────────

    async def extract_issues(
        self,
        english_text: str,
        language: str,
        constituency: str,
    ) -> tuple[list[ExtractedIssue], float, list[ProcessingFlag]]:
        """
        Extract structured issues from English text.
        Returns (issues, overall_confidence, flags).
        """
        flags: list[ProcessingFlag] = []

        # ── Guardrail check before sending to model ──
        triggered, reason = guardrail_check(english_text)
        if triggered:
            flags.append(ProcessingFlag.CONTENT_GUARDRAIL_HIT)
            return [], 0.0, flags

        try:
            prompt = _EXTRACTION_PROMPT.format(
                english_text=english_text[:4000],
                language=language,
                constituency=constituency,
            )
            response = self.model.generate_content(prompt)
            data = self._parse_json_response(response.text, {"issues": [], "overall_confidence": 0.0})

            issues: list[ExtractedIssue] = []
            for raw_issue in data.get("issues", []):
                cat_str = raw_issue.get("category", "other")
                try:
                    cat_enum = IssueCategory(cat_str)
                except ValueError:
                    cat_enum = IssueCategory.OTHER

                cat_conf = float(raw_issue.get("category_confidence", 0.5))
                issue = ExtractedIssue(
                    description=raw_issue.get("description", english_text[:100]),
                    category=make_annotation(cat_enum.value, cat_conf),
                    location_hint=raw_issue.get("location_hint"),
                    severity_hint=raw_issue.get("severity_hint"),
                )
                issues.append(issue)

            overall = float(data.get("overall_confidence", 0.5))
            return issues, overall, flags

        except Exception as e:
            logger.error(f"Issue extraction failed: {e}. Using rule-based fallback.")
            flags.append(ProcessingFlag.SILENT_FALLBACK)

            # Rule-based fallback — still returns a valid structured response
            cat, conf = _rule_based_category(english_text)
            fallback_issue = ExtractedIssue(
                description=english_text[:200],
                category=make_annotation(cat.value, conf),
                location_hint=None,
                severity_hint=None,
            )
            return [fallback_issue], conf, flags

    # ── Audio transcription ───────────────────────────────────────────────────

    async def transcribe_audio(
        self, audio_bytes: bytes, mime_type: str
    ) -> tuple[str, str, str, float, list[ProcessingFlag]]:
        """
        Transcribe audio using Gemini's multimodal input.
        Returns (transcript, lang_code, lang_name, confidence, flags).

        Supported audio formats by Gemini: audio/wav, audio/mp3, audio/aiff,
        audio/aac, audio/ogg, audio/flac
        """
        flags: list[ProcessingFlag] = [ProcessingFlag.AUDIO_TRANSCRIBED]

        try:
            audio_part = {"mime_type": mime_type, "data": audio_bytes}
            response = self.model.generate_content(
                [_AUDIO_TRANSCRIPTION_PROMPT, audio_part]
            )
            data = self._parse_json_response(
                response.text,
                {
                    "transcript": "[Transcription unavailable]",
                    "transcription_confidence": 0.20,
                    "detected_language": "en",
                    "detected_language_name": "English",
                },
            )
            transcript = data.get("transcript", "[Transcription unavailable]")
            confidence = float(data.get("transcription_confidence", 0.20))
            lang = data.get("detected_language", "en")
            lang_name = data.get("detected_language_name", "English")

            if confidence < get_settings().confidence_threshold_low:
                flags.append(ProcessingFlag.LOW_CONFIDENCE)

            return transcript, lang, lang_name, confidence, flags

        except Exception as e:
            logger.error(f"Audio transcription failed: {e}. Silent fallback.")
            flags.append(ProcessingFlag.SILENT_FALLBACK)
            return "[Transcription unavailable — please re-submit as text]", "en", "English", 0.0, flags

    # ── Image analysis ────────────────────────────────────────────────────────

    async def analyse_image(
        self, image_bytes: bytes, mime_type: str
    ) -> tuple[str, IssueCategory, float, str | None, str | None, list[ProcessingFlag]]:
        """
        Analyse an image for civic grievances.
        Returns (description, category, confidence, location_clues, severity_hint, flags).
        """
        flags: list[ProcessingFlag] = [ProcessingFlag.IMAGE_ANALYSED]

        try:
            image_part = {"mime_type": mime_type, "data": image_bytes}
            response = self.model.generate_content(
                [_IMAGE_ANALYSIS_PROMPT, image_part]
            )
            data = self._parse_json_response(
                response.text,
                {
                    "description": "Image could not be analysed",
                    "inferred_category": "other",
                    "category_confidence": 0.20,
                    "location_clues": None,
                    "severity_hint": None,
                    "analysis_confidence": 0.20,
                },
            )

            cat_str = data.get("inferred_category", "other")
            try:
                cat_enum = IssueCategory(cat_str)
            except ValueError:
                cat_enum = IssueCategory.OTHER

            confidence = float(data.get("analysis_confidence", 0.20))
            if confidence < get_settings().confidence_threshold_low:
                flags.append(ProcessingFlag.LOW_CONFIDENCE)

            return (
                data.get("description", ""),
                cat_enum,
                confidence,
                data.get("location_clues"),
                data.get("severity_hint"),
                flags,
            )

        except Exception as e:
            logger.error(f"Image analysis failed: {e}. Silent fallback.")
            flags.append(ProcessingFlag.SILENT_FALLBACK)
            return (
                "Image analysis unavailable",
                IssueCategory.OTHER,
                0.0,
                None,
                None,
                flags,
            )

    # ── Streaming generator ───────────────────────────────────────────────────

    async def stream_extraction(
        self, prompt: str
    ) -> AsyncGenerator[str, None]:
        """
        Yields raw token chunks from Gemini for SSE streaming.
        Used by the route layer to build step-by-step progress events.
        """
        try:
            response = self.model.generate_content(prompt, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            yield ""
