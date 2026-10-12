from __future__ import annotations

"""
Module 5: Enrichment Pipeline
==============================
Làm giàu chunks TRƯỚC khi embed: Summarize, HyQA, Contextual Prepend, Auto Metadata.

Test: pytest tests/test_m5.py
"""

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from dataclasses import dataclass
from functools import lru_cache

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OPENAI_API_KEY, OPENAI_MODEL, REASONING_TOKEN_BUDGET as _REASONING_TOKEN_BUDGET


@lru_cache(maxsize=1)
def _client():
    """OpenAI client dùng chung; None nếu chưa cấu hình API key."""
    if not OPENAI_API_KEY:
        return None
    from openai import OpenAI
    return OpenAI()


def _llm(messages: list[dict], max_tokens: int = 400) -> str:
    """Gọi LLM 1 lần, trả về content string. Raise nếu chưa có key/API lỗi.

    ⚠️ max_tokens phải tính CẢ reasoning tokens (model reasoning tiêu hết budget
    trước khi sinh content → content rỗng, finish_reason="length").
    enable_thinking=False: enrichment là tác vụ trích xuất ngắn, không cần suy luận;
    tắt để tránh content rỗng và giảm chi phí/thời gian.
    """
    client = _client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY chưa được cấu hình")
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        max_tokens=max_tokens + _REASONING_TOKEN_BUDGET,
        extra_body={"enable_thinking": False},
    )
    return (resp.choices[0].message.content or "").strip()



def _strip_json_fence(raw: str) -> str:
    """Bỏ ```json ... ``` nếu LLM trả về kèm code fence."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    return raw.strip()


@dataclass
class EnrichedChunk:
    """Chunk đã được làm giàu."""
    original_text: str
    enriched_text: str
    summary: str
    hypothesis_questions: list[str]
    auto_metadata: dict
    method: str  # "contextual", "summary", "hyqa", "full"


# ─── Technique 1: Chunk Summarization ────────────────────


def summarize_chunk(text: str) -> str:
    """
    Tạo summary ngắn cho chunk.
    Embed summary thay vì (hoặc cùng với) raw chunk → giảm noise.
    """
    try:
        return _llm([
            {"role": "system", "content": "Tóm tắt đoạn văn sau trong 2-3 câu ngắn gọn bằng tiếng Việt."},
            {"role": "user", "content": text},
        ], max_tokens=150)
    except Exception as e:
        print(f"  ⚠️  OpenAI summarize failed: {e}")

    # Extractive fallback (không cần API): lấy 2 câu đầu.
    sentences = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    return ". ".join(sentences[:2]) + "." if sentences else text


# ─── Technique 2: Hypothesis Question-Answer (HyQA) ─────


def generate_hypothesis_questions(text: str, n_questions: int = 3) -> list[str]:
    """
    Generate câu hỏi mà chunk có thể trả lời.
    Index cả questions lẫn chunk → query match tốt hơn (bridge vocabulary gap).
    """
    try:
        raw = _llm([
            {"role": "system", "content": f"Dựa trên đoạn văn, tạo {n_questions} câu hỏi mà đoạn văn có thể trả lời. Trả về mỗi câu hỏi trên 1 dòng."},
            {"role": "user", "content": text},
        ], max_tokens=200)
        questions = [q.strip().lstrip("0123456789.-) ") for q in raw.split("\n") if q.strip()]
        return questions[:n_questions]
    except Exception as e:
        print(f"  ⚠️  OpenAI HyQA failed: {e}")

    # Extractive fallback: biến mệnh đề thành câu hỏi.
    import re
    sentences = [s.strip() for s in re.split(r'[.!?\n]', text) if len(s.strip()) > 10]
    return [f"{s.rstrip('.')}?" for s in sentences[:n_questions]]


# ─── Technique 3: Contextual Prepend (Anthropic style) ──


def contextual_prepend(text: str, document_title: str = "") -> str:
    """
    Prepend context giải thích chunk nằm ở đâu trong document.
    Anthropic benchmark: giảm 49% retrieval failure (alone).
    """
    try:
        context = _llm([
            {"role": "system", "content": "Viết 1 câu ngắn mô tả đoạn văn này nằm ở đâu trong tài liệu và nói về chủ đề gì. Chỉ trả về 1 câu."},
            {"role": "user", "content": f"Tài liệu: {document_title}\n\nĐoạn văn:\n{text}"},
        ], max_tokens=80)
        return f"{context}\n\n{text}"
    except Exception as e:
        print(f"  ⚠️  OpenAI contextual failed: {e}")

    prefix = f"Trích từ {document_title}. " if document_title else ""
    return f"{prefix}{text}"


# ─── Technique 4: Auto Metadata Extraction ──────────────


def extract_metadata(text: str) -> dict:
    """
    LLM extract metadata tự động: topic, entities, date_range, category.
    """
    import json as _json
    try:
        raw = _strip_json_fence(_llm([
            {"role": "system", "content": 'Trích xuất metadata từ đoạn văn. Trả về JSON: {"topic": "...", "entities": ["..."], "category": "policy|hr|it|finance", "language": "vi|en"}'},
            {"role": "user", "content": text},
        ], max_tokens=150))
        return _json.loads(raw)
    except Exception as e:
        print(f"  ⚠️  OpenAI metadata failed: {e}")

    return {"topic": "general", "entities": [], "category": "policy", "language": "vi"}


# ─── Combined Single-Call Mode ───────────────────────────


def _enrich_single_call(text: str, source: str) -> dict:
    """Single LLM call to get summary + questions + context + metadata.

    ⚠️ Cost optimization: 1 API call thay vì 4 calls riêng lẻ.
    """
    import json as _json
    try:
        raw = _strip_json_fence(_llm([
            {"role": "system", "content": """Phân tích đoạn văn và trả về JSON:
{
  "summary": "tóm tắt 2-3 câu",
  "questions": ["câu hỏi 1", "câu hỏi 2", "câu hỏi 3"],
  "context": "1 câu mô tả đoạn văn nằm ở đâu trong tài liệu",
  "metadata": {"topic": "...", "entities": ["..."], "category": "policy|hr|it|finance", "language": "vi|en"}
}"""},
            {"role": "user", "content": f"Tài liệu: {source}\n\nĐoạn văn:\n{text}"},
        ], max_tokens=400))
        result = _json.loads(raw)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        print(f"  ⚠️  Enrichment API failed: {e}")
        return {}


# ─── Full Enrichment Pipeline ────────────────────────────


def enrich_chunks(
    chunks: list[dict],
    methods: list[str] | None = None,
    cache_path: str | None = None,
) -> list[EnrichedChunk]:
    """
    Chạy enrichment pipeline trên danh sách chunks. (Đã implement sẵn — dùng functions ở trên)

    Có 2 chế độ:
    - methods cụ thể (["summary"], ["contextual"]...): gọi từng function riêng (tốt cho học/debug)
    - methods=["combined"] hoặc None: 1 API call duy nhất cho tất cả (tốt cho production)

    Args:
        chunks: List of {"text": str, "metadata": dict}
        methods: Default None → combined mode (1 call/chunk).
                 Options: "summary", "hyqa", "contextual", "metadata", "combined"
        cache_path: Cache kết quả ra JSON (enrichment tốn ~40 phút cho 106 chunks).
                    Mặc định None (không cache) — người gọi tự chỉ định đường dẫn,
                    tránh việc test/corpus nhỏ ghi đè cache của corpus lớn.
    """
    if methods is None:
        methods = ["combined"]

    use_combined = "combined" in methods

    # Cache: enrichment là bước đắt nhất và idempotent → không nên trả tiền 2 lần.
    if cache_path and os.path.exists(cache_path):
        try:
            import json as _json
            from dataclasses import asdict
            with open(cache_path, encoding="utf-8") as f:
                cached = _json.load(f)
            if cached.get("methods") == methods and cached.get("texts") == [c["text"] for c in chunks]:
                print(f"  ✓ Dùng cache enrichment: {cache_path}", flush=True)
                return [EnrichedChunk(**e) for e in cached["enriched"]]
        except Exception as e:
            print(f"  ⚠️  Cache không đọc được ({e}), chạy lại enrichment.", flush=True)

    enriched = []
    for i, chunk in enumerate(chunks):
        text = chunk["text"]
        source = chunk.get("metadata", {}).get("source", "")

        if use_combined:
            result = _enrich_single_call(text, source)
            summary = result.get("summary", "")
            questions = result.get("questions", [])
            context_line = result.get("context", "")
            enriched_text = f"{context_line}\n\n{text}" if context_line else text
            auto_meta = result.get("metadata", {})
        else:
            summary = summarize_chunk(text) if "summary" in methods else ""
            questions = generate_hypothesis_questions(text) if "hyqa" in methods else []
            enriched_text = contextual_prepend(text, source) if "contextual" in methods else text
            auto_meta = extract_metadata(text) if "metadata" in methods else {}

        enriched.append(EnrichedChunk(
            original_text=text,
            enriched_text=enriched_text,
            summary=summary,
            hypothesis_questions=questions,
            auto_metadata={**chunk.get("metadata", {}), **auto_meta},
            method="+".join(methods),
        ))

        if (i + 1) % 10 == 0 or (i + 1) == len(chunks):
            print(f"  Enriched {i + 1}/{len(chunks)} chunks...", flush=True)

    if cache_path:
        import json as _json
        from dataclasses import asdict
        try:
            os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                _json.dump({"methods": methods, "texts": [c["text"] for c in chunks],
                            "enriched": [asdict(e) for e in enriched]},
                           f, ensure_ascii=False, indent=2)
            print(f"  ✓ Cache enrichment → {cache_path}", flush=True)
        except Exception as e:
            print(f"  ⚠️  Không ghi được cache: {e}", flush=True)

    return enriched


# ─── Main ────────────────────────────────────────────────

if __name__ == "__main__":
    sample = "Nhân viên chính thức được nghỉ phép năm 12 ngày làm việc mỗi năm. Số ngày nghỉ phép tăng thêm 1 ngày cho mỗi 5 năm thâm niên công tác."

    print("=== Enrichment Pipeline Demo ===\n")
    print(f"Original: {sample}\n")

    s = summarize_chunk(sample)
    print(f"Summary: {s}\n")

    qs = generate_hypothesis_questions(sample)
    print(f"HyQA questions: {qs}\n")

    ctx = contextual_prepend(sample, "Sổ tay nhân viên VinUni 2024")
    print(f"Contextual: {ctx}\n")

    meta = extract_metadata(sample)
    print(f"Auto metadata: {meta}")
