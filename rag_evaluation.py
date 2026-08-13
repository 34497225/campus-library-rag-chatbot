"""Reproducible evaluation for the portfolio RAG pipeline.

The evaluator uses the same loader, splitter, embeddings, FAISS retrieval and
answer function as the Streamlit application.  It deliberately stores only
aggregate pass/fail evidence in the report, so model responses cannot leak
uploaded documents into Git.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable, Sequence

from app import DEMO_LIBRARY_PATH, answer_question, build_vector_store, load_csv


@dataclass(frozen=True)
class EvaluationCase:
    """One expected behavior expressed as language-independent keyword groups."""

    case_id: str
    question: str
    expected_source_terms: tuple[str, ...]
    answer_keyword_groups: tuple[tuple[str, ...], ...]
    expects_fallback: bool = False


def load_cases(path: Path) -> list[EvaluationCase]:
    """Load and validate the version-controlled evaluation dataset."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for raw in payload:
        case_id = str(raw["id"]).strip()
        if not case_id or case_id in seen_ids:
            raise ValueError(f"Duplicate or empty case id: {case_id!r}")
        seen_ids.add(case_id)
        cases.append(
            EvaluationCase(
                case_id=case_id,
                question=str(raw["question"]).strip(),
                expected_source_terms=tuple(raw.get("expected_source_terms", [])),
                answer_keyword_groups=tuple(
                    tuple(group) for group in raw.get("answer_keyword_groups", [])
                ),
                expects_fallback=bool(raw.get("expects_fallback", False)),
            )
        )
    if not cases:
        raise ValueError("Evaluation dataset must contain at least one case.")
    return cases


def contains_all_groups(text: str, groups: Iterable[Sequence[str]]) -> bool:
    """Return true when at least one alias from every required group appears."""

    normalized = text.casefold()
    return all(any(alias.casefold() in normalized for alias in group) for group in groups)


def score_case(case: EvaluationCase, source_text: str, answer: str) -> tuple[bool, bool]:
    """Score retrieval evidence and grounded-answer behavior separately."""

    retrieval_passed = contains_all_groups(
        source_text, ((term,) for term in case.expected_source_terms)
    )
    answer_passed = contains_all_groups(answer, case.answer_keyword_groups)
    return retrieval_passed, answer_passed


def percentile(values: Sequence[float], fraction: float) -> float:
    """Return a nearest-rank percentile without adding a statistics dependency."""

    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999) - 1))
    return ordered[index]


def run_evaluation(cases: Sequence[EvaluationCase]) -> dict[str, object]:
    """Run real embeddings/retrieval/answers against the fictional demo FAQ."""

    documents = load_csv(DEMO_LIBRARY_PATH, DEMO_LIBRARY_PATH.name)
    index_started = time.perf_counter()
    vector_store = build_vector_store(documents)
    index_seconds = time.perf_counter() - index_started

    results: list[dict[str, object]] = []
    for case in cases:
        started = time.perf_counter()
        answer, sources, tokens = answer_question(vector_store, case.question, [])
        latency = time.perf_counter() - started
        source_text = "\n".join(source.page_content for source in sources)
        retrieval_passed, answer_passed = score_case(case, source_text, answer)
        results.append(
            {
                "id": case.case_id,
                "retrieval_passed": retrieval_passed,
                "answer_passed": answer_passed,
                "latency_seconds": round(latency, 3),
                "tokens": int(tokens),
            }
        )

    latencies = [float(result["latency_seconds"]) for result in results]
    retrieval_results = [
        result
        for case, result in zip(cases, results)
        if not case.expects_fallback
    ]
    retrieval_passes = sum(
        bool(result["retrieval_passed"]) for result in retrieval_results
    )
    answer_passes = sum(bool(result["answer_passed"]) for result in results)
    return {
        "model": "gpt-4o-mini",
        "embedding_model": "text-embedding-3-small",
        "dataset_cases": len(results),
        "retrieval_cases": len(retrieval_results),
        "index_seconds": round(index_seconds, 3),
        "retrieval_passes": retrieval_passes,
        "answer_passes": answer_passes,
        "retrieval_hit_rate": round(retrieval_passes / len(retrieval_results), 4),
        "answer_pass_rate": round(answer_passes / len(results), 4),
        "average_latency_seconds": round(mean(latencies), 3),
        "p95_latency_seconds": round(percentile(latencies, 0.95), 3),
        "total_tokens": sum(int(result["tokens"]) for result in results),
        "results": results,
    }


def render_markdown(report: dict[str, object]) -> str:
    """Render a compact, reviewable report without raw prompts or answers."""

    lines = [
        "# RAG evaluation report",
        "",
        "This report is generated from the fictional demo library FAQ. It uses the",
        "same chunking, OpenAI embeddings, FAISS Top-3 retrieval and chat model as",
        "the Streamlit application. Raw model answers are intentionally not committed.",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Cases | {report['dataset_cases']} |",
        f"| Retrieval hit rate ({report['retrieval_cases']} answerable cases) | {float(report['retrieval_hit_rate']):.0%} |",
        f"| Grounded answer pass rate | {float(report['answer_pass_rate']):.0%} |",
        f"| Index build | {report['index_seconds']} s |",
        f"| Average answer latency | {report['average_latency_seconds']} s |",
        f"| p95 answer latency | {report['p95_latency_seconds']} s |",
        f"| Total evaluation tokens | {report['total_tokens']} |",
        "",
        "## Cases",
        "",
        "| ID | Retrieval | Answer | Latency (s) | Tokens |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for result in report["results"]:
        lines.append(
            "| {id} | {retrieval} | {answer} | {latency} | {tokens} |".format(
                id=result["id"],
                retrieval="pass" if result["retrieval_passed"] else "fail",
                answer="pass" if result["answer_passed"] else "fail",
                latency=result["latency_seconds"],
                tokens=result["tokens"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Retrieval checks whether expected evidence appears in the Top-3 chunks",
            "  for answerable cases; out-of-scope fallback cases are excluded.",
            "- Answer checks require explicit facts for in-scope cases and a polite",
            "  unsupported-information fallback for out-of-scope cases.",
            "- Keyword scoring is transparent and repeatable, but does not measure every",
            "  aspect of fluency or factual equivalence. A larger production system should",
            "  add human review and semantic or model-based evaluation.",
            "- Latency is a one-run observation from a local client and is not an SLA.",
            "",
            "Regenerate with:",
            "",
            "```powershell",
            ".\\.venv\\Scripts\\python.exe rag_evaluation.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluation/rag_cases.json"),
        help="Path to the version-controlled evaluation cases.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/RAG_EVALUATION.md"),
        help="Markdown report destination.",
    )
    args = parser.parse_args()
    report = run_evaluation(load_cases(args.dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    if report["retrieval_hit_rate"] < 0.9 or report["answer_pass_rate"] < 0.9:
        raise SystemExit("RAG evaluation did not meet the 90% portfolio threshold.")


if __name__ == "__main__":
    main()
