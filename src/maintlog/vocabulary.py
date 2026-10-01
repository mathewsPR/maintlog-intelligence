"""vocabulary.py  Experimental vocabulary learned only from declared training labels."""

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .evaluation import MASK, NormDocument

SAFE_SOURCE = re.compile(r"[A-Za-z]+")
SAFE_TARGET = re.compile(r"[A-Za-z]+(?:[ -][A-Za-z]+)*")
WORD = re.compile(r"(?<![\w/.-])([A-Za-z]+)(?![\w/.-])")


def fit_lexicon(
    documents: list[NormDocument], *, min_support: int = 5, confidence: float = 0.98
) -> dict:
    if type(min_support) is not int or min_support < 1 or not 0.5 <= confidence <= 1:
        raise ValueError("invalid vocabulary thresholds")
    counts = defaultdict(Counter)
    for doc in documents:
        for unit in doc.units:
            if (
                MASK.search(unit.target)
                or not SAFE_SOURCE.fullmatch(unit.source)
                or not SAFE_TARGET.fullmatch(unit.target)
            ):
                continue
            counts[unit.source.casefold()][unit.target.casefold()] += 1
    entries = {}
    for source, targets in sorted(counts.items()):
        target, support = sorted(targets.items(), key=lambda pair: (-pair[1], pair[0]))[
            0
        ]
        total = sum(targets.values())
        if (
            support >= min_support
            and support / total >= confidence
            and source != target
        ):
            entries[source] = {
                "target": target,
                "support": support,
                "total": total,
                "confidence": support / total,
            }
    return {
        "method": "train_lexicon_v1",
        "min_support": min_support,
        "minimum_confidence": confidence,
        "entries": entries,
        "interpretation": "Training-label vocabulary for development experiments. Domain transfer and semantic correctness require evaluation; it is not enabled in company imports by default.",
    }


def predict(text: str, lexicon: dict) -> str:
    return WORD.sub(
        lambda match: (
            lexicon["entries"]
            .get(match.group(1).casefold(), {})
            .get("target", match.group(1))
        ),
        text,
    )


def load_vocabulary(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    lexicon = data.get("trained_lexicon", data)
    if not isinstance(lexicon, dict) or not isinstance(lexicon.get("entries"), dict):
        raise ValueError("vocabulary requires an entries object")
    if len(lexicon["entries"]) > 10000:
        raise ValueError("vocabulary entry limit exceeded")
    for source, entry in lexicon["entries"].items():
        if (
            not SAFE_SOURCE.fullmatch(source)
            or not isinstance(entry, dict)
            or not isinstance(entry.get("target"), str)
            or not SAFE_TARGET.fullmatch(entry["target"])
        ):
            raise ValueError("vocabulary entries must be alphabetic words/phrases")
    return lexicon


def vocabulary_hash(lexicon: dict) -> str:
    return hashlib.sha256(
        json.dumps(lexicon, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
