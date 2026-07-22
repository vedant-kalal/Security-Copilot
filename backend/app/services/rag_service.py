"""
RAG (Retrieval-Augmented Generation) service.

Embeds an incident's context, retrieves the most semantically similar
guided-response playbooks from `playbooks` via pgvector cosine search,
and hands them to `LLMService` to ground the Gemini-generated
explanation (core workflow steps 11-12: "RAG retrieves playbooks" ->
"LLM generates response").

If Gemini embeddings are unavailable, retrieval falls back to a MITRE
technique-ID overlap search so playbook grounding still works offline.
"""
from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.playbook import Playbook
from app.repositories.playbook_repository import PlaybookRepository
from app.services.llm_service import LLMService

logger = get_logger(__name__)


class RAGService:
    def __init__(self, session: AsyncSession, llm_service: LLMService | None = None) -> None:
        self.session = session
        self.playbooks = PlaybookRepository(session)
        self.llm = llm_service or LLMService()

    async def retrieve_playbooks(
        self, incident_title: str, mitre_techniques: List[str], top_k: int = 3
    ) -> List[Playbook]:
        query_text = f"{incident_title}. Relevant techniques: {', '.join(mitre_techniques)}"
        embedding = await self.llm.embed_text(query_text)

        if embedding:
            results = await self.playbooks.search_similar(embedding, top_k=top_k)
            if results:
                return [playbook for playbook, _similarity in results]

        logger.info("Falling back to MITRE-overlap playbook retrieval (no embedding available)")
        return list(await self.playbooks.list_by_mitre(mitre_techniques, limit=top_k))
