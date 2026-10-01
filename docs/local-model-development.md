# Local model development evidence

Model: Qwen3.5-4B Q4_K_M, llama.cpp alias qwen35-4b, reasoning off.
Synthetic company demo, PUMP-001, question: Review bearing vibration history and proposed actions.

| Run | Status | Calls | Seconds | Observed failure |
| --- | --- | ---: | ---: | --- |
| 01 | failed | 3 | 3.938 | Aggregate called with unsupported arguments |
| 02 | failed | 4 | 7.562 | Missing extraction status and wrong span keys |
| 03 | failed | 7 | 17.218 | Whole narrative reused across roles; incorrect offsets; action-prefixed component |
| 04 | failed | 7 | 15.765 | Incorrect offsets, then output-only source_column sent as input |
| 05 | failed | 7 | 14.610 | Valid field/quote inputs; unsupported attempted status repeated twice |
| 06 | ready_for_review | 7 | 13.391 | No tool errors; workflow requirements met; source retains repair-outcome qualification |

Run 04 improved WO-01 field selection and proposed planned status. WO-02 still confused repair outcome with the work performed. Run 05 selected the replacement action correctly but proposed attempted rather than performed-work status. Runs 01–05 did not finish; run 06 finished for review. These are successive development attempts with changed prompts, not repeated benchmark trials. They establish neither model accuracy nor comparative superiority. Source-span validity does not establish semantic classification accuracy.

## Tool-contract correction

The local backend requests llama.cpp response_format={type:json_object,schema:...} and locally checks the same restricted schema subset. Unknown properties and missing extraction status are rejected. Model spans use either field/quote or field/start/end. Computed metadata stays in stored reports and is excluded from extraction observations sent to the model. Source validators retain strict source matching and return recovery guidance. Prompt distinguishes work performed from repair outcome. Replay mechanics remain separate from model evaluation.

Validation: 125 Python 3.11 tests passed locally; Ruff lint passed. Eleven added regression tests cover the contract, evidence separation, explicit status definitions, corrected-status recovery, and identical invalid retry detection. No live model run was possible against the user's Windows localhost from this execution environment. The patch does not establish that semantic extraction is fixed. Run 06 passed the demo smoke test; synthetic release acceptance is pending, followed by a frozen evaluation set and repeated trials without further prompt tuning on holdout data.

Reference API example: https://github.com/ggml-org/llama.cpp/blob/master/examples/json_schema_pydantic_example.py

## Status and retry correction after run 05

Shared status definitions appear in the model prompt and schema description. Execution of work is separate from repair outcome. Unsupported status feedback names the proposed status, selected action quote and missing explicit support; it does not automatically relabel the model proposal. Rejected decisions and correction instructions are included in observations. Identical invalid retries are marked in the trace. The original two-error bound remains. Replay tests establish recovery mechanics, not the live model ability to follow feedback.
