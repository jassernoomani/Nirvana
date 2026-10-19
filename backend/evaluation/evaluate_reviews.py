"""Measure the review-analysis model on the labelled set (review_dataset.json).

Run from backend, with Ollama running:

    .venv/Scripts/python.exe evaluation/evaluate_reviews.py                     # the app's current approach (v5)
    .venv/Scripts/python.exe evaluation/evaluate_reviews.py --prompt v4         # a reference prompt
    .venv/Scripts/python.exe evaluation/evaluate_reviews.py --model llama3.2:3b # another local model

Every review goes through the same redaction and output checks as the application
(app/ai/reviews.py). "current" uses the application's own classify(); the reference
prompts v3 and v4 ask the model for the sentiment directly, as the app did before.
Results are printed and saved to evaluation/results/<label>.json.
"""
import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

from app.ai import llm, prompts  # noqa: E402
from app.ai.reviews import INJECTION, Batch, ClassifiedReview, classify, redact, validate  # noqa: E402

DATASET = Path(__file__).with_name("review_dataset.json")
RESULTS = Path(__file__).with_name("results")
SENTIMENTS = ["positive", "neutral", "negative", "mixed"]


def without_examples(prompt: str) -> str:
    """The same instructions without the worked examples (zero-shot instead of few-shot)."""
    lines = prompt.splitlines()
    return "\n".join(line for line in lines if not line.startswith(("Example:", '"')) and line != "Examples:")


# Reference prompts: the model returns the sentiment itself (schema with complaints listed first).
REFERENCE_PROMPTS = {
    "v3": ("nirvana-ai-v3", prompts.REVIEW_CLASSIFICATION_V3),
    "v4": ("nirvana-ai-v4", prompts.REVIEW_CLASSIFICATION_V4),
    "v4-no-examples": ("nirvana-ai-v4 without examples", without_examples(prompts.REVIEW_CLASSIFICATION_V4)),
}


def classify_with_reference(prompt: str, review_id: int, text: str) -> ClassifiedReview:
    result = llm.generate(prompt, {"reviews": [{"id": review_id, "text": text}]}, Batch)
    if len(result.reviews) != 1 or result.reviews[0].id != review_id:
        raise llm.LocalModelError("Review IDs did not match the requested sample.")
    return result.reviews[0]


def topic_scores(rows):
    tp = sum(len(set(r["expected_topics"]) & set(r["predicted_topics"])) for r in rows)
    fp = sum(len(set(r["predicted_topics"]) - set(r["expected_topics"])) for r in rows)
    fn = sum(len(set(r["expected_topics"]) - set(r["predicted_topics"])) for r in rows)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def summarise(rows):
    if not rows:
        return {}
    return {"n": len(rows),
            "sentiment_accuracy": round(sum(r["predicted_sentiment"] == r["expected_sentiment"] for r in rows) / len(rows), 3),
            "exact_topics": round(sum(set(r["predicted_topics"]) == set(r["expected_topics"]) for r in rows) / len(rows), 3),
            "topics": topic_scores(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate review analysis on the labelled set.")
    parser.add_argument("--model", help="Ollama model tag (default: LLM_MODEL from .env)")
    parser.add_argument("--prompt", default="current", choices=["current", *REFERENCE_PROMPTS])
    parser.add_argument("--limit", type=int, help="only the first N reviews (quick check)")
    parser.add_argument("--label", help="name of the results file (default: <model>-<prompt>)")
    args = parser.parse_args()
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    model = llm.settings()["model"]
    if args.prompt == "current":
        version, run = prompts.PROMPT_VERSION, classify
    else:
        version, prompt = REFERENCE_PROMPTS[args.prompt]
        run = lambda review_id, text: classify_with_reference(prompt, review_id, text)  # noqa: E731
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))[: args.limit]

    # Warm-up call, so loading the model into memory is reported separately from normal latency.
    start = time.perf_counter()
    try:
        run(0, "The food was good.")
    except llm.ModelUnavailable as exc:
        raise SystemExit(f"Model not usable: {exc}")
    except llm.LocalModelError as exc:
        print(f"Warm-up answer unusable ({exc}); continuing, failures are counted per review.")
    cold_start = round(time.perf_counter() - start, 2)

    rows = []
    for index, item in enumerate(dataset, start=1):
        text = redact(item["text"])
        row = {"id": item["id"], "source": item["source"], "text": item["text"],
               "expected_sentiment": item["sentiment"], "expected_topics": item["topics"],
               "predicted_sentiment": None, "predicted_topics": [], "accepted": False, "error": None,
               "flagged_by_injection_filter": bool(INJECTION.search(item["text"]))}
        start = time.perf_counter()
        try:
            review = run(index, text)
            row["predicted_sentiment"] = review.sentiment
            row["predicted_topics"] = sorted({c.topic for c in review.complaints})
            try:
                validate(review, text)
                row["accepted"] = True
            except llm.LocalModelError as exc:
                row["error"] = f"rejected by checks: {exc}"
        except llm.LocalModelError as exc:
            row["error"] = f"model call failed: {exc}"
        row["seconds"] = round(time.perf_counter() - start, 2)
        rows.append(row)
        mark = "ok " if row["predicted_sentiment"] == row["expected_sentiment"] and set(row["predicted_topics"]) == set(row["expected_topics"]) else "-- "
        print(f"{mark}{index:>2}/{len(dataset)} {row['seconds']:>5}s  expected {item['sentiment']:8} {item['topics']}  "
              f"got {row['predicted_sentiment']} {row['predicted_topics']}{'  [' + row['error'] + ']' if row['error'] else ''}")

    latencies = sorted(r["seconds"] for r in rows)
    injections = [r for r in rows if "injection" in next(i["note"] for i in dataset if i["id"] == r["id"])]
    result = {
        "model": model, "prompt_variant": args.prompt, "prompt_version": version,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "temperature": 0,
        "overall": summarise(rows),
        "by_source": {source: summarise([r for r in rows if r["source"] == source]) for source in ["seed", "seed-special", "hand-written"]},
        "accepted_by_checks": round(sum(r["accepted"] for r in rows) / len(rows), 3),
        "rejected_by_checks": sum(1 for r in rows if r["error"] and r["error"].startswith("rejected")),
        "failed_calls": sum(1 for r in rows if r["error"] and r["error"].startswith("model call failed")),
        "sentiment_confusion": {expected: dict(Counter(r["predicted_sentiment"] for r in rows if r["expected_sentiment"] == expected))
                                for expected in SENTIMENTS},
        "injection_cases": {"n": len(injections),
                            "obeyed": sum(1 for r in injections if r["predicted_sentiment"] == "positive" and not r["predicted_topics"])},
        "latency_seconds": {"cold_start": cold_start, "median": statistics.median(latencies),
                            "p95": latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))], "total": round(sum(latencies), 1)},
        "items": rows,
    }
    RESULTS.mkdir(exist_ok=True)
    label = args.label or f"{model.replace(':', '-')}-{args.prompt if args.prompt != 'current' else prompts.PROMPT_VERSION.split('-')[-1]}"
    (RESULTS / f"{label}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    overall = result["overall"]
    print(f"\nModel {model} · prompt {args.prompt} ({version}) · {overall['n']} reviews")
    print(f"Sentiment accuracy {overall['sentiment_accuracy']:.0%} · exact topic set {overall['exact_topics']:.0%} · "
          f"topics P {overall['topics']['precision']:.2f} R {overall['topics']['recall']:.2f} F1 {overall['topics']['f1']:.2f}")
    for source, scores in result["by_source"].items():
        if scores:
            print(f"  {source:13} n={scores['n']:>2}  sentiment {scores['sentiment_accuracy']:.0%}  topic F1 {scores['topics']['f1']:.2f}")
    print(f"Accepted by the output checks {result['accepted_by_checks']:.0%} · rejected {result['rejected_by_checks']} · failed calls {result['failed_calls']}")
    print(f"Injection cases obeyed: {result['injection_cases']['obeyed']}/{result['injection_cases']['n']}")
    lat = result["latency_seconds"]
    print(f"Latency: cold start {lat['cold_start']}s · median {lat['median']}s · p95 {lat['p95']}s · total {lat['total']}s")
    print(f"Saved evaluation/results/{label}.json")


if __name__ == "__main__":
    main()
