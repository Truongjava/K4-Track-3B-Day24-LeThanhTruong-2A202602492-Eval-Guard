from __future__ import annotations

"""Phase B: LLM-as-Judge — pairwise, swap-and-average, Cohen κ, bias analysis."""

import json
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OPENAI_API_KEY, JUDGE_MODEL, HUMAN_LABELS_PATH


@dataclass
class JudgeResult:
    question: str
    answer_a: str
    answer_b: str
    winner_pass1: str       # "A" | "B" | "tie"  (original order)
    winner_pass2: str       # "A" | "B" | "tie"  (after swap, ALREADY converted back)
    final_winner: str       # consensus after swap-and-average
    reasoning_pass1: str
    reasoning_pass2: str
    position_consistent: bool  # True if both passes agree on same answer
    scores_pass1: dict = field(default_factory=dict)  # {"A": float, "B": float}
    scores_pass2: dict = field(default_factory=dict)


# ─── Task 5: Pairwise Judge ───────────────────────────────────────────────────

PAIRWISE_PROMPT = '''Bạn là expert đánh giá chất lượng câu trả lời RAG về chính sách công ty.

Câu hỏi: {question}

Chính sách/đáp án tham chiếu: {reference}

Answer A:
{answer_a}

Answer B:
{answer_b}

Đánh giá dựa trên 3 tiêu chí: độ chính xác so với reference, độ đầy đủ của câu trả lời,
tính súc tích. Khác diễn đạt hoặc độ dài không tự là lý do trừ điểm.
Trả về JSON (chỉ JSON, không text khác):
{{"winner": "A" hoặc "B" hoặc "tie", "reasoning": "giải thích ngắn gọn", "scores": {{"A": 0.0-1.0, "B": 0.0-1.0}}}}
'''


def pairwise_judge(question: str, answer_a: str, answer_b: str, reference: str = "") -> dict:
    """Task 5: Gọi LLM để chọn answer tốt hơn (A hoặc B) theo 3 tiêu chí.

    Returns:
        {"winner": "A"|"B"|"tie", "reasoning": str, "scores": {"A": float, "B": float}}
    """
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Bạn là expert đánh giá RAG. Chỉ trả lời JSON."},
            {"role": "user", "content": PAIRWISE_PROMPT.format(
                question=question, answer_a=answer_a, answer_b=answer_b, reference=reference)},
        ],
    )
    return json.loads(resp.choices[0].message.content)


# ─── Task 6: Swap-and-Average ─────────────────────────────────────────────────

def swap_and_average(question: str, answer_a: str, answer_b: str, reference: str = "") -> JudgeResult:
    """Task 6: Chạy pairwise 2 lần (hoán đổi thứ tự), lấy kết quả nhất quán.

    Pass 1: judge(q, A, B) → winner_1 (trong không gian A/B)
    Pass 2: judge(q, B, A) → winner_2_raw (trong không gian B/A), convert về A/B
    Final:  hai lượt đồng ý → giữ; khác nhau → "tie"
    """
    pass1 = pairwise_judge(question, answer_a, answer_b, reference=reference)
    pass2_raw = pairwise_judge(question, answer_b, answer_a, reference=reference)  # SWAP

    swap_map = {"A": "B", "B": "A", "tie": "tie"}
    winner_pass2 = swap_map[pass2_raw["winner"]]

    consistent = pass1["winner"] == winner_pass2
    return JudgeResult(
        question=question, answer_a=answer_a, answer_b=answer_b,
        winner_pass1=pass1["winner"], winner_pass2=winner_pass2,
        final_winner=pass1["winner"] if consistent else "tie",
        reasoning_pass1=pass1["reasoning"], reasoning_pass2=pass2_raw["reasoning"],
        position_consistent=consistent,
        scores_pass1=pass1["scores"],
        scores_pass2={"A": pass2_raw["scores"]["B"], "B": pass2_raw["scores"]["A"]},
    )


# ─── Task 7: Cohen's κ ────────────────────────────────────────────────────────

def cohen_kappa(judge_labels: list[int], human_labels: list[int]) -> float:
    """Task 7: Tính Cohen's κ giữa LLM judge và human labels.

    Thang đo Landis-Koch: <0=poor, 0-0.2=slight, 0.2-0.4=fair,
                           0.4-0.6=moderate, 0.6-0.8=substantial, 0.8-1=almost perfect
    """
    n = len(judge_labels)
    p_o = sum(j == h for j, h in zip(judge_labels, human_labels)) / n
    p_e = (judge_labels.count(1) * human_labels.count(1) +
           judge_labels.count(0) * human_labels.count(0)) / n**2
    return (p_o - p_e) / (1 - p_e) if p_e != 1 else 0.0


# ─── Task 8: Bias Report ──────────────────────────────────────────────────────

def bias_report(judge_results: list[JudgeResult]) -> dict:
    """Task 8: Đo lường position bias và verbosity bias.

    Position bias: hai lượt swap không đồng ý → judge đổi ý theo vị trí.
    Verbosity bias: trong các case decisive, winner có dài hơn không?
    """
    total = len(judge_results)
    if total == 0:
        return {"total_judged": 0, "position_bias_rate": 0.0, "position_bias_count": 0,
                "verbosity_bias": 0.0,
                "verbosity_details": {"a_wins_a_longer": 0, "b_wins_b_longer": 0,
                                      "total_decisive": 0},
                "interpretation": "Không có cặp nào để đánh giá."}

    position_bias_count = sum(1 for r in judge_results if not r.position_consistent)

    a_wins_a_longer = sum(1 for r in judge_results
                          if r.final_winner == "A" and len(r.answer_a) > len(r.answer_b))
    b_wins_b_longer = sum(1 for r in judge_results
                          if r.final_winner == "B" and len(r.answer_b) > len(r.answer_a))
    decisive = sum(1 for r in judge_results if r.final_winner != "tie")
    verbosity_bias = (a_wins_a_longer + b_wins_b_longer) / decisive if decisive else 0.0
    position_bias_rate = position_bias_count / total

    interpretation = (
        f"Position inconsistency {position_bias_count}/{total} cặp "
        f"({position_bias_rate:.0%}): judge đổi kết luận khi hoán đổi thứ tự, "
        f"dấu hiệu position bias; báo cáo dùng final_winner=tie cho các cặp này. "
        f"Verbosity rate {verbosity_bias:.0%} trên {decisive} cặp decisive "
        f"(A thắng và dài hơn: {a_wins_a_longer}, B thắng và dài hơn: {b_wins_b_longer}); "
        f"tỷ lệ này chỉ là dấu hiệu, cần đọc nội dung trước khi kết luận.")
    return {
        "total_judged": total,
        "position_bias_rate": round(position_bias_rate, 3),
        "position_bias_count": position_bias_count,
        "verbosity_bias": round(verbosity_bias, 3),
        "verbosity_details": {"a_wins_a_longer": a_wins_a_longer,
                              "b_wins_b_longer": b_wins_b_longer,
                              "total_decisive": decisive},
        "interpretation": interpretation,
    }



# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from scripts.run_experiments import main
    raise SystemExit(main(["--phase", "b", *sys.argv[1:]]))
