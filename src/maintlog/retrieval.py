"""Small deterministic BM25 baseline over normalized issue and action text."""

import math
from collections import Counter
from datetime import date

from .domain import Record, SearchHit
from .normalization import search_tokens
from .scope import Scope


def search(
    records: list[Record],
    query: str,
    *,
    top_k: int = 5,
    asset_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    normalization_policy: str = "dictionary_v0",
    vocabulary: dict | None = None,
) -> list[SearchHit]:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    terms = set(search_tokens(query, normalization_policy, vocabulary))
    if not terms:
        raise ValueError("query must contain searchable text")
    corpus = Scope(asset_id, start, end).select(records)
    if not corpus:
        return []
    docs = [
        Counter(
            search_tokens(
                r.issue_raw + " " + r.action_raw + " " + r.narrative_raw,
                normalization_policy,
                vocabulary,
            )
        )
        for r in corpus
    ]
    lengths = [sum(doc.values()) for doc in docs]
    average_length = sum(lengths) / len(docs) or 1.0
    frequencies = Counter(term for doc in docs for term in doc)
    hits: list[SearchHit] = []
    for record, doc, length in zip(corpus, docs, lengths):
        score = 0.0
        for term in sorted(terms):
            count = doc[term]
            if not count:
                continue
            frequency = frequencies[term]
            inverse_frequency = math.log(
                1 + (len(docs) - frequency + 0.5) / (frequency + 0.5)
            )
            denominator = count + 1.5 * (1 - 0.75 + 0.75 * length / average_length)
            score += inverse_frequency * count * 2.5 / denominator
        if score > 0:
            hits.append(SearchHit(record, score))
    return sorted(hits, key=lambda hit: (-hit.score, hit.record.record_id))[:top_k]
