"""Development comparison on MaintNorm validation; frozen test baseline unchanged."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .evaluation import read_norm, score_normalization, verify_manifest
from .normalization import normalize, normalize_nouns
from .vocabulary import fit_lexicon, predict


def run(root: Path) -> dict:
    manifest = verify_manifest(root)
    documents = [
        doc
        for company in "abc"
        for doc in read_norm(root / "maintnorm" / f"val_company_{company}.norm")
    ]
    training = [
        doc
        for company in "abc"
        for doc in read_norm(root / "maintnorm" / f"train_company_{company}.norm")
    ]
    lexicon = fit_lexicon(training)
    methods = {
        "identity": lambda text: text,
        "dictionary_v0": normalize,
        "noun_alias_v1": normalize_nouns,
        "train_lexicon_v1": lambda text: predict(text, lexicon),
    }
    return {
        "split": "validation",
        "purpose": "development_diagnostic_not_fresh_holdout",
        "policy_sha256": hashlib.sha256(
            Path(__file__).with_name("normalization.py").read_bytes()
        ).hexdigest(),
        "dataset_manifest": manifest,
        "trained_lexicon": lexicon,
        "scores": {
            name: score_normalization(documents, fn, casefold=True)
            for name, fn in methods.items()
        },
        "interpretation": "Noun aliases avoid inventing action completion from repl/chk/lub. Vocabulary coverage remains narrow. Policy was changed after test errors were reviewed; this validation comparison is development evidence, not independent generalization proof or agent accuracy.",
    }


def main(argv=None):
    if sys.version_info[:2] != (3, 11):
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/public"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.resolve().is_relative_to(args.data_root.resolve()):
            raise ValueError("output must not overwrite dataset snapshots")
        result = run(args.data_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"Saved normalization development comparison: {args.output}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
