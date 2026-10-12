from __future__ import annotations

"""Phase C: Production Guardrails — Presidio PII + NeMo Guardrails + P95 Latency."""

import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ADVERSARIAL_SET_PATH, GUARDRAILS_CONFIG_DIR, LATENCY_BUDGET_P95_MS, PRESIDIO_LANGUAGE


# ─── Task 9a: Presidio PII Detection ─────────────────────────────────────────

def setup_presidio():
    """Khởi tạo Presidio engine với custom Vietnamese PII recognizers. (Đã implement sẵn)

    Custom recognizers thêm vào:
        VN_CCCD  — số CCCD 12 chữ số hoặc CMND 9 chữ số
        VN_PHONE — số điện thoại Việt Nam (0[3-9]xxxxxxxx)
    Ngoài ra chỉ giữ EmailRecognizer.

    Registry cố ý KHÔNG gọi load_predefined_recognizers(): bộ mặc định kéo theo
    NER tiếng Anh (spaCy en_core_web_lg), và trên văn bản tiếng Việt nó trả
    PERSON/… sai (ví dụ "Khung lương chung của cấp" → PERSON 0.85) khiến mọi câu
    sạch bị chặn. Guard chỉ cần đúng ba loại entity theo hợp đồng Task 9a.
    """
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, Pattern, PatternRecognizer
    from presidio_analyzer.predefined_recognizers import EmailRecognizer
    from presidio_anonymizer import AnonymizerEngine

    cccd_recognizer = PatternRecognizer(
        supported_entity="VN_CCCD",
        patterns=[
            Pattern("CCCD 12 digits", r"\b\d{12}\b", 0.9),
            Pattern("CMND 9 digits",  r"\b\d{9}\b",  0.7),
        ],
    )
    phone_recognizer = PatternRecognizer(
        supported_entity="VN_PHONE",
        patterns=[Pattern("VN mobile", r"\b0[3-9]\d{8}\b", 0.9)],
    )

    registry = RecognizerRegistry()
    registry.add_recognizer(cccd_recognizer)
    registry.add_recognizer(phone_recognizer)
    registry.add_recognizer(EmailRecognizer())

    analyzer  = AnalyzerEngine(registry=registry)
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer


def pii_scan(text: str, analyzer=None, anonymizer=None) -> dict:
    """Task 9a: Quét PII trong văn bản bằng Presidio.

    Returns:
        {
          "has_pii":    bool,
          "entities":   [{"type": str, "text": str, "score": float, "start": int, "end": int}],
          "anonymized": str,   # text với PII được thay bằng <TYPE>
        }
    """
    if analyzer is None or anonymizer is None:
        analyzer, anonymizer = setup_presidio()

    results = analyzer.analyze(text=text, language=PRESIDIO_LANGUAGE)
    if not results:
        return {"has_pii": False, "entities": [], "anonymized": text}

    anonymized = anonymizer.anonymize(text=text, analyzer_results=results).text
    entities = [
        {"type": r.entity_type, "text": text[r.start:r.end],
         "score": round(r.score, 3), "start": r.start, "end": r.end}
        for r in results
    ]
    return {"has_pii": True, "entities": entities, "anonymized": anonymized}


# ─── Task 9b + 11: NeMo Guardrails ───────────────────────────────────────────

def setup_nemo_rails():
    """Khởi tạo NeMo Guardrails từ guardrails/config.yml. (Đã implement sẵn)

    Config directory: guardrails/
        config.yml  — model + rails config
        rails.co    — câu từ chối Colang 1.0; built-in self-check flows được bật trong YAML

    NeMo chỉ chọn ChatOpenAI khi tên model chứa "gpt-3.5"/"gpt-4"; gateway của lớp
    không có model đó nên engine "openai" sẽ rơi vào completions API (404). Đăng ký
    provider "openai_chat" trỏ thẳng ChatOpenAI để guard self-check dùng chat API.
    """
    from langchain_openai.chat_models import ChatOpenAI
    from nemoguardrails import RailsConfig, LLMRails
    from nemoguardrails.llm.providers import register_llm_provider

    register_llm_provider("openai_chat", ChatOpenAI)
    config = RailsConfig.from_path(GUARDRAILS_CONFIG_DIR)
    rails  = LLMRails(config)
    return rails


async def check_input_rail(text: str, rails=None) -> dict:
    """Task 9b: Kiểm tra input qua NeMo input rails (topic guard + jailbreak guard).

    Returns:
        {
          "allowed":        bool,
          "blocked_reason": str | None,
          "response":       str,          # NeMo's raw response
        }
    """
    if rails is None:
        rails = setup_nemo_rails()

    result = await rails.generate_async(
        messages=[{"role": "user", "content": text}],
        options={"rails": ["input"], "log": {"activated_rails": True}},
    )
    # Đọc quyết định rail; không suy ra blocked từ từ khóa có thể nằm trong input sạch.
    blocked = any(rail.stop for rail in result.log.activated_rails)
    return {
        "allowed":        not blocked,
        "blocked_reason": "nemo_input_rail" if blocked else None,
        "response":       result.response[0]["content"],
    }


async def check_output_rail(question: str, answer: str, rails=None) -> dict:
    """Task 11: Kiểm tra LLM output qua NeMo output rails trước khi trả về user.

    NeMo output rails hoạt động trong context của cả cuộc hội thoại (input + output).
    Kiểm tra PII và nội dung nhạy cảm. Self-check này không thay RAGAS faithfulness
    hoặc kiểm tra factual accuracy với retrieved contexts.

    Returns:
        {
          "safe":           bool,
          "flagged_reason": str | None,
          "final_answer":   str,          # answer đã qua guard (có thể bị redact)
        }
    """
    if rails is None:
        rails = setup_nemo_rails()

    # Cung cấp context đầy đủ để output rail hoạt động trong ngữ cảnh hội thoại.
    result = await rails.generate_async(
        messages=[
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
        options={"rails": ["output"], "log": {"activated_rails": True}},
    )
    response = result.response[0]["content"]
    flagged = any(rail.stop for rail in result.log.activated_rails)
    return {
        "safe":           not flagged,
        "flagged_reason": "nemo_output_rail" if flagged else None,
        # Output sạch giữ nguyên answer gốc; output bị chặn trả câu thay thế của rail.
        "final_answer":   response if flagged else answer,
    }


# ─── Task 10: Adversarial Test Suite ─────────────────────────────────────────

def run_adversarial_suite(adversarial_set: list[dict], rails=None,
                           analyzer=None, anonymizer=None) -> list[dict]:
    """Task 10: Chạy inputs qua full guard stack, so sánh với expected.

    Guard stack order:
        1. pii_scan()         → block nếu has_pii
        2. check_input_rail() → block nếu jailbreak / off-topic / prompt injection

    `expected` chỉ dùng để chấm passed, không tham gia quyết định actual.
    """
    if analyzer is None or anonymizer is None:
        analyzer, anonymizer = setup_presidio()
    if rails is None:
        rails = setup_nemo_rails()

    async def _run_all():
        rows = []
        for item in adversarial_set:
            blocked_by = None

            # Layer 1: Presidio PII (synchronous, fast)
            if pii_scan(item["input"], analyzer, anonymizer)["has_pii"]:
                blocked_by = "presidio"

            # Layer 2: NeMo input rail (async — await, không dùng asyncio.run())
            if blocked_by is None and not (await check_input_rail(item["input"], rails))["allowed"]:
                blocked_by = "nemo_input"

            actual = "blocked" if blocked_by else "allowed"
            rows.append({
                "id":         item["id"],
                "category":   item["category"],
                "input":      item["input"],
                "expected":   item["expected"],
                "actual":     actual,
                "blocked_by": blocked_by,
                "passed":     actual == item["expected"],
            })
        return rows

    results = asyncio.run(_run_all())   # một event loop duy nhất
    passed = sum(1 for r in results if r["passed"])
    print(f"Adversarial suite: {passed}/{len(results)} passed")
    return results



# ─── Task 12: P95 Latency Measurement ────────────────────────────────────────

def measure_p95_latency(test_inputs: list[str], n_runs: int = 20,
                         rails=None, analyzer=None, anonymizer=None) -> dict:
    """Task 12: measure INPUT layers sequentially, not end-to-end guard/RAG latency.

    Reuse engines. Inside ONE event loop, execute two real warm-up calls per layer,
    excluded from samples. Then collect exactly n_runs timed samples (cycle clean
    inputs), always measuring BOTH PII and NeMo input even if PII blocks.
    Use perf_counter; keep raw milliseconds. summarize_latency() supplies linear
    percentiles at (n - 1) * q. Submission requires n_runs >= 20.
    Short-circuit request timing, RAG and output timing are outside this scope.
    """
    from src.experiment_support import summarize_latency

    if not test_inputs or n_runs < 1:
        raise ValueError("Need inputs and n_runs >= 1")
    if analyzer is None or anonymizer is None:
        analyzer, anonymizer = setup_presidio()
    if rails is None:
        rails = setup_nemo_rails()

    async def _measure():
        # Warm-up thật 2 lượt, loại khỏi samples.
        for i in range(2):
            text = test_inputs[i % len(test_inputs)]
            pii_scan(text, analyzer, anonymizer)
            await check_input_rail(text, rails)

        samples = []
        for i in range(n_runs):
            text = test_inputs[i % len(test_inputs)]
            # Luôn đo cả hai tầng; không short-circuit theo quyết định block.
            t0 = time.perf_counter()
            pii_scan(text, analyzer, anonymizer)
            t1 = time.perf_counter()
            await check_input_rail(text, rails)
            t2 = time.perf_counter()
            presidio_ms = (t1 - t0) * 1000
            nemo_ms = (t2 - t1) * 1000
            samples.append({"presidio_ms": presidio_ms, "nemo_input_ms": nemo_ms,
                            "input_guard_ms": presidio_ms + nemo_ms})
        return samples

    return summarize_latency(asyncio.run(_measure()), warmup_runs=2)



# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from scripts.run_experiments import main
    raise SystemExit(main(["--phase", "c", *sys.argv[1:]]))
