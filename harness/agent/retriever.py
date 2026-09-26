"""Retriever: search ACTIVE chunks only, apply score filters, return citations.

Provider-neutral: keyword-overlap scoring over SQLite/Postgres text (no vector
DB required for v1). An embedding scorer can replace `_score` later without
changing the contract.
"""
from __future__ import annotations

import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from configs.settings import settings
from harness.agent.schemas import CitationHit
from harness.store import models as M


def _tokens(s: str) -> set[str]:
    return set(w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if len(w) > 2)


def _score(query: str, text: str) -> float:
    q, d = _tokens(query), _tokens(text)
    if not q or not d:
        return 0.0
    overlap = len(q & d)
    return overlap / max(len(q), 1) * (1.0 + min(len(d) / 200.0, 0.5))


def retrieve(db: Session, query: str, top_k: int | None = None) -> list[CitationHit]:
    k = top_k or settings.RETRIEVAL_TOP_K
    active_version_ids = db.scalars(
        select(M.KnowledgeVersion.id).where(M.KnowledgeVersion.status == "active")).all()
    if not active_version_ids:
        return []
    chunks = db.scalars(select(M.KnowledgeChunk)
                        .where(M.KnowledgeChunk.version_id.in_(active_version_ids))
                        .limit(2000)).all()
    scored: list[CitationHit] = []
    for c in chunks:
        s = _score(query, c.text)
        if s >= settings.RETRIEVAL_MIN_SCORE:
            scored.append(CitationHit(version_id=c.version_id, chunk_id=c.id,
                                      document_id=c.document_id, text=c.text,
                                      page=c.page, locator=c.locator, score=round(s, 4)))
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:k]
