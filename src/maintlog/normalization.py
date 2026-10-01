"""Conservative dictionary baseline; never rewrite identifiers or unknown terms."""

import re

ABBREVIATIONS = {
    "brg": "bearing",
    "vib": "vibration",
    "temp": "temperature",
    "repl": "replaced",
    "chk": "checked",
    "lub": "lubricated",
}
# A hyphen, slash, digit, or underscore can be part of an identifier. Only
# standalone words can be expanded: BRG-204 and TEMP_01 stay unchanged.
_WORD = re.compile(r"(?<![\w/.-])([A-Za-z]+)(?![\w/.-])")


def normalize(text: str) -> str:
    return _WORD.sub(
        lambda match: ABBREVIATIONS.get(match.group(1).lower(), match.group(1)),
        text,
    )


def tokens(text: str) -> list[str]:
    return re.findall(r"[\w]+(?:[-./][\w]+)*", normalize(text).casefold())


NOUN_ALIASES = {"brg": "bearing", "vib": "vibration", "temp": "temperature"}


def normalize_nouns(text: str) -> str:
    """Retrieval aliases only; never turn repl/chk/lub into performed actions."""
    return _WORD.sub(
        lambda match: NOUN_ALIASES.get(match.group(1).lower(), match.group(1)), text
    )


def search_tokens(
    text: str, policy: str = "noun_alias_v1", vocabulary: dict | None = None
) -> list[str]:
    if vocabulary is not None:
        from .vocabulary import predict

        text = predict(text, vocabulary)
        return re.findall(r"[\w]+(?:[-./][\w]+)*", text.casefold())
    if policy == "dictionary_v0":
        return tokens(text)
    if policy not in {"noun_alias_v1", "identity"}:
        raise ValueError("unknown normalization policy")
    text = normalize_nouns(text) if policy == "noun_alias_v1" else text
    return re.findall(r"[\w]+(?:[-./][\w]+)*", text.casefold())
