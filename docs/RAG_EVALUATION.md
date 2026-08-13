# RAG evaluation report

This report is generated from the fictional demo library FAQ. It uses the
same chunking, OpenAI embeddings, FAISS Top-3 retrieval and chat model as
the Streamlit application. Raw model answers are intentionally not committed.

## Summary

| Metric | Result |
| --- | ---: |
| Cases | 16 |
| Retrieval hit rate (12 answerable cases) | 100% |
| Grounded answer pass rate | 94% |
| Index build | 1.786 s |
| Average answer latency | 2.35 s |
| p95 answer latency | 14.11 s |
| Total evaluation tokens | 8202 |

## Cases

| ID | Retrieval | Answer | Latency (s) | Tokens |
| --- | --- | --- | ---: | ---: |
| zh-weekday-hours | pass | pass | 2.306 | 534 |
| zh-weekend-hours | pass | pass | 1.608 | 533 |
| zh-borrow-limit | pass | pass | 1.485 | 495 |
| zh-loan-period | pass | pass | 1.617 | 484 |
| zh-renewal | pass | pass | 1.605 | 513 |
| zh-computers | pass | pass | 1.4 | 500 |
| zh-food | pass | pass | 2.149 | 532 |
| zh-journal | pass | pass | 1.368 | 498 |
| en-borrow-method | pass | fail | 14.11 | 503 |
| en-overdue | pass | pass | 1.577 | 515 |
| en-reserve | pass | pass | 1.285 | 503 |
| en-lost-card | pass | pass | 1.281 | 515 |
| zh-out-of-scope-tuition | pass | pass | 1.463 | 513 |
| zh-out-of-scope-weather | pass | pass | 1.502 | 530 |
| en-out-of-scope-parking | pass | pass | 1.408 | 515 |
| en-out-of-scope-grades | pass | pass | 1.441 | 519 |

## Interpretation

- Retrieval checks whether expected evidence appears in the Top-3 chunks
  for answerable cases; out-of-scope fallback cases are excluded.
- Answer checks require explicit facts for in-scope cases and a polite
  unsupported-information fallback for out-of-scope cases.
- Keyword scoring is transparent and repeatable, but does not measure every
  aspect of fluency or factual equivalence. A larger production system should
  add human review and semantic or model-based evaluation.
- Latency is a one-run observation from a local client and is not an SLA.

Regenerate with:

```powershell
.\.venv\Scripts\python.exe rag_evaluation.py
```
