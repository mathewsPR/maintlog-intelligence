# Public source snapshots

Downloaded for the user's requested evaluation on 2026-09-30. Source files are
unmodified and retain their original MIT license notices in each subdirectory.
`manifest.json` records source URLs, revisions, byte sizes, SHA-256 hashes, and
acquisition time. The evaluator rejects missing or altered required snapshots.

## MaintNorm

Authors: Tyler Bikaun, Melinda Hodkiewicz, and Wei Liu.
Paper: *MaintNorm: A corpus and benchmark model for lexical normalisation and
masking of industrial maintenance short text*, W-NUT 2024, pp. 68–78.
https://aclanthology.org/2024.wnut-1.7/

Original repository: https://github.com/nlp-tlp/maintnorm
Author-maintained mirror: https://huggingface.co/datasets/nlp-tlp/MaintNorm
Data revision: `ff058a2d4944e2cae1353dbb8ff2145249bebce3`.
Nine company-specific train/validation/test `.norm` files are included. Combined
files are not included, to avoid counting pooled/company duplicates as new data.
The license file was downloaded from the original repository's main branch;
its exact bytes are hashed in the manifest. We do not claim its URL was pinned.

Format: tab-separated source/target units; blank lines delimit documents. Targets
may contain multiword expansions, privacy masks, or empty deletions; a source
unit can be empty for an insertion. The evaluator keeps those cases explicitly.

These mining-equipment texts contain obfuscated identifiers. This is not a pump
asset-history dataset. Do not manufacture asset IDs, dates, or action labels to
force it into the application's CSV schema.

## MaintIE

Authors: Tyler K. Bikaun, Tim French, Michael Stewart, Wei Liu, Melinda Hodkiewicz.
Paper: *MaintIE: A Fine-Grained Annotation Schema and Benchmark for Information
Extraction from Maintenance Short Texts*, LREC-COLING 2024, pp. 10939–10951.
https://aclanthology.org/2024.lrec-main.954/

Original repository: https://github.com/nlp-tlp/maintie
Snapshot revision: `825e7710e4129598da997276a38b3cb40b200bc2`.
Included: `data/gold_release.json` and the original `LICENSE.md`.

The gold corpus contains normalized/sanitized text, tokens, entity token spans,
and entity-to-entity relations. The current evaluator audits this structure.
M0 has no narrative extractor, so no extraction/model/agent performance is
reported. The larger silver corpus is not used as independent gold labels.

## Use and limitations

The baseline dictionary was frozen before these files were obtained. The
supplied results evaluate the nominal test files and a supplementary exact
overlap-filtered test subset. No training, fine-tuning, or prompt optimization
was performed. Near-duplicate and cross-corpus leakage checks remain necessary
before a future model evaluation. Preserve these notices when redistributing
the snapshots and cite the original papers in any published benchmark.
