from __future__ import annotations

"""Module 4: RAGAS Evaluation — 4 metrics + failure analysis."""

import os, sys, json, math
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TEST_SET_PATH, OPENAI_MODEL, OPENAI_EMBEDDING_MODEL, RAGAS_MAX_WORKERS, RAGAS_TIMEOUT, RAGAS_MAX_TOKENS


def _ragas_llm():
    """RAGAS judge LLM. Tách riêng để test/debug không phải chạy full evaluate.

    max_tokens lớn vì: (a) RAGAS cần output dài (trích statement + verify từng cái),
    (b) model reasoning còn tiêu thêm reasoning tokens trước khi sinh content.

    enable_thinking=False qua extra_body: gateway OpenAI-compatible từ chối
    tham số n>1 khi thinking bật ("The n parameter must be 1 when
    enable_thinking is true"), mà answer_relevancy cần n=3 generations.
    """
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0, max_tokens=RAGAS_MAX_TOKENS,
                     extra_body={"enable_thinking": False})
    return LangchainLLMWrapper(llm)



def _ragas_embeddings():
    """RAGAS embeddings. check_embedding_ctx_length=False vì gateway
    OpenAI-compatible chỉ nhận str/list[str], không nhận token-id arrays
    (mặc định của langchain sẽ tokenize trước khi gửi)."""
    from langchain_openai import OpenAIEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper
    return LangchainEmbeddingsWrapper(OpenAIEmbeddings(
        model=OPENAI_EMBEDDING_MODEL, check_embedding_ctx_length=False))


@dataclass
class EvalResult:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


def load_test_set(path: str = TEST_SET_PATH) -> list[dict]:
    """Load test set from JSON. (Đã implement sẵn)"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evaluate_ragas(questions: list[str], answers: list[str],
                   contexts: list[list[str]], ground_truths: list[str]) -> dict:
    """Run RAGAS evaluation.

    Trả về dict có `per_question` (list EvalResult) và `metadata.evaluator_models`
    ghi model IDs thực sự dùng trong lượt evaluation này (LLM + embedding),
    theo hợp đồng PIPELINE_INTERFACE.md.
    """
    evaluator_models = [OPENAI_MODEL, OPENAI_EMBEDDING_MODEL]
    zero = {"faithfulness": 0.0, "answer_relevancy": 0.0,
            "context_precision": 0.0, "context_recall": 0.0, "per_question": [],
            "metadata": {"evaluator_models": evaluator_models}}
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
        from ragas.run_config import RunConfig
        from datasets import Dataset

        dataset = Dataset.from_dict({
            "question": questions, "answer": answers,
            "contexts": contexts, "ground_truth": ground_truths,
        })
        result = evaluate(dataset, metrics=[faithfulness, answer_relevancy,
                                            context_precision, context_recall],
                          llm=_ragas_llm(), embeddings=_ragas_embeddings(),
                          raise_exceptions=False,
                          run_config=RunConfig(max_workers=RAGAS_MAX_WORKERS,
                                               timeout=RAGAS_TIMEOUT, max_retries=10))
        df = result.to_pandas()
        # RAGAS >= 0.2 đổi tên cột: question → user_input, answer → response,
        # contexts → retrieved_contexts, ground_truth → reference.
        df = df.rename(columns={"user_input": "question", "response": "answer",
                                "retrieved_contexts": "contexts", "reference": "ground_truth"})

        def _score(row, key) -> float:
            value = row.get(key, 0.0)
            try:
                value = float(value)
            except (TypeError, ValueError):
                return 0.0
            return 0.0 if math.isnan(value) else value  # RAGAS trả NaN khi metric fail

        per_question = [EvalResult(
            question=row["question"], answer=row["answer"],
            contexts=list(row["contexts"]), ground_truth=row["ground_truth"],
            faithfulness=_score(row, "faithfulness"),
            answer_relevancy=_score(row, "answer_relevancy"),
            context_precision=_score(row, "context_precision"),
            context_recall=_score(row, "context_recall"),
        ) for _, row in df.iterrows()]

        out = {m: (sum(getattr(e, m) for e in per_question) / len(per_question)
                   if per_question else 0.0)
               for m in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]}
        out["per_question"] = per_question
        out["metadata"] = {"evaluator_models": evaluator_models}
        return out
    except Exception as e:
        print(f"  ⚠️  RAGAS evaluation failed: {e}")
        return zero


def failure_analysis(eval_results: list[EvalResult], bottom_n: int = 10) -> list[dict]:
    """Analyze bottom-N worst questions using Diagnostic Tree."""
    diagnostic_tree = {
        "faithfulness": ("LLM hallucinating", "Tighten prompt, lower temperature"),
        "context_recall": ("Missing relevant chunks", "Improve chunking or add BM25"),
        "context_precision": ("Too many irrelevant chunks", "Add reranking or metadata filter"),
        "answer_relevancy": ("Answer doesn't match question", "Improve prompt template"),
    }
    metrics = list(diagnostic_tree)

    rows = []
    for e in eval_results:
        # RAGAS trả NaN khi metric fail → quy về 0.0 để sort và JSON hợp lệ
        # (NaN phá sort của Python và tạo JSON không đọc được bằng parser strict).
        scores = {m: (0.0 if math.isnan(v) else v) for m, v in
                  ((m, getattr(e, m)) for m in metrics)}
        worst_metric = min(scores, key=scores.get)
        diagnosis, suggested_fix = diagnostic_tree[worst_metric]
        rows.append({
            "question": e.question,
            "answer": e.answer,
            "ground_truth": e.ground_truth,
            "worst_metric": worst_metric,
            "score": round(scores[worst_metric], 4),
            "avg_score": round(sum(scores.values()) / len(scores), 4),
            "all_scores": {m: round(v, 4) for m, v in scores.items()},
            "diagnosis": f"{worst_metric} thấp nhất ({scores[worst_metric]:.2f}): {diagnosis}",
            "suggested_fix": suggested_fix,
        })

    rows.sort(key=lambda r: r["avg_score"])
    return rows[:bottom_n]


def save_report(results: dict, failures: list[dict], path: str = "reports/ragas_report.json"):
    """Save evaluation report to JSON. (Đã implement sẵn)"""
    parent_dir = os.path.dirname(path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    report = {
        "aggregate": {k: v for k, v in results.items() if k != "per_question"},
        "num_questions": len(results.get("per_question", [])),
        "failures": failures,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved to {path}")


if __name__ == "__main__":
    test_set = load_test_set()
    print(f"Loaded {len(test_set)} test questions")
    print("Run pipeline.py first to generate answers, then call evaluate_ragas().")
