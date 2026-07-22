"""Playbook repository, including pgvector cosine-similarity search."""
import math
from typing import Sequence
from uuid import UUID

import numpy as np
from sqlalchemy import select

from app.models.playbook import Playbook
from app.repositories.base import BaseRepository


class PlaybookRepository(BaseRepository[Playbook]):
    model = Playbook

    async def get(self, pk: UUID) -> Playbook | None:
        return await self.session.get(Playbook, pk)

    async def search_similar(self, query_embedding: list[float], top_k: int = 3) -> Sequence[tuple[Playbook, float]]:
        """Return the `top_k` playbooks most similar to `query_embedding` using pure Python math.
        This avoids the need for the pgvector extension and is extremely fast for small datasets.
        """
        stmt = select(Playbook).where(Playbook.embedding.is_not(None))
        result = await self.session.execute(stmt)
        playbooks = result.scalars().all()

        def cosine_similarity(v1: list[float], v2: list[float]) -> float:
            vec1 = np.array(v1)
            vec2 = np.array(v2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(np.dot(vec1, vec2) / (norm1 * norm2))

        scored_playbooks = []
        for pb in playbooks:
            if pb.embedding:
                sim = cosine_similarity(query_embedding, pb.embedding)
                scored_playbooks.append((pb, sim))

        scored_playbooks.sort(key=lambda x: x[1], reverse=True)
        return scored_playbooks[:top_k]

    async def list_by_mitre(self, technique_ids: Sequence[str], limit: int = 5) -> Sequence[Playbook]:
        stmt = select(Playbook).where(Playbook.mitre_techniques.overlap(list(technique_ids))).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
