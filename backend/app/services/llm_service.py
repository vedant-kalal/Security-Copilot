"""
LLM integration service (Google Gemini).

Uses the official `google-genai` SDK. Two capabilities are exposed:

  * `embed_text`   — turns text into a vector for pgvector similarity
                      search (used to index and retrieve playbooks).
  * `generate_incident_explanation` — turns an incident + retrieved
                      playbook(s) into a plain-English summary and a
                      concrete, numbered remediation recommendation
                      (architecture doc: "The user never needs to
                      understand logs. Everything is translated into
                      plain English.").

Both methods degrade gracefully (deterministic templated output) if no
API key is configured or the Gemini API call fails, so the pipeline
never breaks a demo because of network/quota issues.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class IncidentExplanation:
    summary: str
    recommendation: str
    generated_by_llm: bool


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        self._client_init_attempted = False

    def _get_client(self):
        if self._client is not None:
            return self._client
        if self._client_init_attempted:
            return None
        self._client_init_attempted = True

        if not self.settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not configured — LLM/RAG features will use templated fallbacks")
            return None

        try:
            from google import genai

            self._client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
            return self._client
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize Gemini client: %s", exc)
            return None

    async def embed_text(self, text: str) -> Optional[List[float]]:
        """Embed a piece of text using the Gemini embedding model.
        Returns None if the Gemini client is unavailable."""
        client = self._get_client()
        if client is None:
            return None
        try:
            from google.genai import types

            def _sync_embed():
                result = client.models.embed_content(
                    model=self.settings.GEMINI_EMBEDDING_MODEL,
                    contents=text,
                    config=types.EmbedContentConfig(output_dimensionality=self.settings.GEMINI_EMBEDDING_DIMENSIONS),
                )
                return list(result.embeddings[0].values)

            return await asyncio.to_thread(_sync_embed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini embedding call failed: %s", exc)
            return None

    async def generate_incident_explanation(
        self,
        incident_title: str,
        severity: str,
        mitre_techniques: List[str],
        evidence_reasons: List[str],
        playbook_excerpts: List[str],
    ) -> IncidentExplanation:
        client = self._get_client()
        if client is None:
            return self._templated_explanation(incident_title, severity, mitre_techniques, evidence_reasons)

        prompt = self._build_prompt(incident_title, severity, mitre_techniques, evidence_reasons, playbook_excerpts)
        try:
            def _sync_generate():
                response = client.models.generate_content(model=self.settings.GEMINI_MODEL, contents=prompt)
                return (response.text or "").strip()

            text = await asyncio.to_thread(_sync_generate)
            summary, recommendation = self._split_response(text)
            if summary and recommendation:
                return IncidentExplanation(summary=summary, recommendation=recommendation, generated_by_llm=True)
            logger.warning("Gemini response did not match expected SUMMARY/RECOMMENDATION format; using fallback")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini generation call failed: %s", exc)

        return self._templated_explanation(incident_title, severity, mitre_techniques, evidence_reasons)

    @staticmethod
    def _build_prompt(
        title: str, severity: str, mitre: List[str], reasons: List[str], playbooks: List[str]
    ) -> str:
        reasons_block = "\n".join(f"- {r}" for r in reasons) or "- No specific evidence details available"
        playbooks_block = "\n\n".join(playbooks) or "No matching playbook found in the knowledge base."
        mitre_block = ", ".join(mitre) or "None mapped"

        return (
            "You are a security operations analyst assistant embedded in a SOC dashboard. "
            "Explain the following incident to a non-expert end user in plain English, then give a "
            "concrete, numbered remediation plan grounded in the reference playbook provided.\n\n"
            f"Incident title: {title}\n"
            f"Severity: {severity}\n"
            f"MITRE ATT&CK techniques: {mitre_block}\n"
            f"Evidence:\n{reasons_block}\n\n"
            f"Reference playbook(s):\n{playbooks_block}\n\n"
            "Respond in EXACTLY this format, with no extra commentary:\n"
            "SUMMARY: <2-4 sentence plain-English explanation of what happened and why it matters>\n"
            "RECOMMENDATION: <numbered list of concrete remediation steps, separated by ' | '>"
        )

    @staticmethod
    def _split_response(text: str) -> tuple[str, str]:
        summary, recommendation = "", ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("SUMMARY:"):
                summary = stripped.split(":", 1)[1].strip()
            elif stripped.upper().startswith("RECOMMENDATION:"):
                recommendation = stripped.split(":", 1)[1].strip()
        return summary, recommendation

    @staticmethod
    def _templated_explanation(
        title: str, severity: str, mitre: List[str], reasons: List[str]
    ) -> IncidentExplanation:
        reasons_text = "; ".join(reasons) if reasons else "correlated security telemetry"
        mitre_text = ", ".join(mitre) if mitre else "no specific MITRE ATT&CK technique"
        summary = (
            f"SentinelAI detected '{title}' at {severity} severity, based on {reasons_text}. "
            f"This activity maps to {mitre_text} in the MITRE ATT&CK framework."
        )
        recommendation = (
            "1. Isolate the affected device from the network if the activity is ongoing. "
            "2. Do not enter credentials or download files from the flagged source. "
            "3. Reset credentials for any accounts used on the flagged site. "
            "4. Report the incident to your security team for further investigation. "
            "5. Review the Evidence tab for full technical detail before marking this incident resolved."
        )
        return IncidentExplanation(summary=summary, recommendation=recommendation, generated_by_llm=False)
