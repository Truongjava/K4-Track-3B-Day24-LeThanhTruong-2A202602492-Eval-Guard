# Nhóm thực hiện K4 Track 3B

Tên nhóm: T3B-Solo-LeThanhTruong

Repo chung: https://github.com/Truongjava/K4-L3-DAY24-T3B-LeThanhTruong-Eval-Guard

Trưởng nhóm/người nộp: Lê Thanh Trường - 2A202602492

Ngày lab/deadline áp dụng: 13/10/2026 11:59 (UTC+07:00) — Asia/Ho_Chi_Minh

Commit dùng để chấm: `3b1b21a4037ae0350aed9e2e23c32b7ebaa789c8` (bản hoàn thành bài lab)

Nhóm chỉ có một thành viên; mục INDIVIDUAL bên dưới khai toàn bộ phần việc thực tế.

## Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò / công việc thật | Bằng chứng |
|---|---|---|---|---|
| 1 | Lê Thanh Trường | 2A202602492 | Toàn bộ Phase A/B/C, tích hợp pipeline m1–m5, chạy batch, viết báo cáo | commits trong repo, `artifacts/*.json`, `doc/reports/*.md` |

Người tích hợp/chạy batch/nộp link: Lê Thanh Trường — chép m1–m5 từ Day 18, sửa adapter
`m2_search` cho qdrant-client 1.9.2, chạy `scripts/setup_answers.py --live`, ba runner
`--phase a|b|c --live`, `scripts/check_lab.py`; bằng chứng là `artifacts/answers_50q.json`,
`artifacts/ragas_50q.json`, `artifacts/judge_results.json`, `artifacts/guard_results.json`
và lịch sử git.

## Môi trường và chuẩn bị trước lớp

OS/Python/compiler: Windows 11 Home Single Language (10.0.26200), Python 3.11.8
(`py -3.11`), Microsoft Visual Studio Build Tools 2022 17.14.41 với workload
Desktop development with C++ (MSVC 14.44.35207), cài bằng winget để build `annoy==1.17.3`.

Virtualenv/dependencies/imports: `.venv` (Python 3.11.8) cài
`requirements/requirements.txt -c requirements/constraints-core.txt`; `annoy==1.17.3`
build từ source; bổ sung `pyarrow==16.1.0` vì pyarrow 26 (bản resolve mặc định) đòi
NumPy ≥ 2 trong khi core pin `numpy==1.26.4`. Kết quả:
`pip check` → "No broken requirements found"; import được `ragas 0.1.22`,
`nemoguardrails 0.10.0`, `presidio_analyzer 2.2.364`, `spacy 3.8.16`, `torch 2.14.1+cpu`,
`sentence-transformers 5.7.0`, `qdrant-client 1.9.2`, `annoy`.
Môi trường unit test offline tách riêng: `.venv-tests` với
`requirements/requirements-test.lock.txt`, `pytest tests/ -q` → 86 passed.

Models/Qdrant/50 answers đã chuẩn bị: model cache HuggingFace đã có sẵn
`BAAI/bge-m3` (embedding) và `BAAI/bge-reranker-v2-m3` (cross-encoder); Qdrant
`qdrant/qdrant:v1.9.7` chạy bằng `infra/docker-compose.yml` trên port 6333;
`artifacts/answers_50q.json` sinh bằng `python scripts/setup_answers.py --live`
(50 id, 20 factual / 20 multi_hop / 10 adversarial, answer/contexts tách khỏi
ground_truth, `generation_mode`/`generation_model` đúng).

Giới hạn/fallback thực tế: gateway OpenAI-compatible của lớp (ai-box) không có kênh
cho `gpt-4o-mini`, nên generation/evaluator/judge/guard dùng `qwen3.8-flash` cùng
`text-embedding-v4` cho embeddings; đã ghi đúng model ID thật vào metadata từng report
theo bốn vai trò. Model reasoning của gateway từ chối `n>1` khi thinking bật, nên
`m4_eval` và `m5_enrichment` gọi với `enable_thinking=False` (cần cho `answer_relevancy`).
Hai PDF trong `data/` (`BCTC.pdf`, `Nghi_dinh_so_13-2023...pdf`) là bản scan ảnh không có
text layer nên bị bỏ qua khi load — không OCR trong phạm vi bài này.

Kết quả chạy thật (đã lưu trong `artifacts/`): answers 50/50 ở `generation_mode=llm`,
không có fallback nào; Phase A factual 0.929 / multi_hop 0.560 / adversarial 0.838
(nhóm yếu nhất multi_hop, bottom 10 toàn multi_hop); Phase B κ = 1.000 (10/10 khớp nhãn
người), position inconsistency 1/5, verbosity 3/4 cặp decisive; Phase C attacks 20/20,
clean 8/8 với false-positive rate 0.000, output 4/4 đúng quyết định, latency input-layer
P95 4271.9 ms (vượt budget 500 ms, ghi đúng số thật và phân tích trong blueprint).

## INDIVIDUAL

### LeThanhTruong-2A202602492

- Phần được giao và phần thực tế đã làm: làm toàn bộ bài với tư cách nhóm một người.
  Phase A: Tasks 1–4 trong `src/phase_a_ragas.py` (group 20/20/10, adapter
  `run_ragas_50q` gọi `m4.evaluate_ragas` và lấy `metadata.evaluator_models`,
  `bottom_10` theo avg_score tăng dần kèm diagnosis/fix, `cluster_analysis` matrix
  worst_metric × distribution và chọn nhóm yếu theo mean thấp nhất, không theo cỡ nhóm).
  Phase B: Tasks 5–8 trong `src/phase_b_judge.py` (pairwise JSON judge dùng reference,
  swap-and-average hai lượt có convert về hệ A/B gốc, Cohen κ tính tay, bias report
  position/verbosity kèm diễn giải). Phase C: Tasks 9a–12 trong `src/phase_c_guard.py`
  (Presidio detect/anonymize CCCD/CMND–VN phone–email, input/output rail async đọc
  `result.log.activated_rails`, adversarial suite 28 inputs một batch, P95 latency
  scope `input_layers_sequential` có 2 warm-up thật và ≥20 mẫu timed).
  Tích hợp: chép m1–m5 từ Day 18 vào `src/`, thêm các biến gateway vào `config.py`,
  sửa `m2_search` cho tương thích qdrant-client 1.9.2 (`search` thay `query_points`).
- Bằng chứng: `artifacts/answers_50q.json`, `artifacts/ragas_50q.json`,
  `artifacts/judge_results.json`, `artifacts/guard_results.json`,
  `doc/reports/failure_clusters.md`, `doc/reports/bias_report.md`,
  `doc/reports/blueprint.md`; commit trong lịch sử git.
- Cách kiểm tra: `python -m pytest tests/ -q` (mock, không API) → 86 passed;
  `.venv-tests` chạy `-m support` → 60 passed. Live: `scripts/setup_answers.py --live`,
  `scripts/run_experiments.py --phase a|b|c --live`, rồi `python scripts/check_lab.py`
  đọc lại artifact và đối chiếu counts/id/means/percentiles.
- Điều đã học: (1) matrix worst_metric thống kê mọi câu nên tổng cột là 20/20/10, không
  phải bằng chứng chất lượng — nhóm yếu phải chọn bằng mean; (2) A/B winner và nhãn
  0/1 là hai câu hỏi khác nhau, không được chuyển máy móc, và nhãn 0/1 phải đánh giá
  đúng `model_answer` nguồn với reference, không đưa `human_label` vào prompt;
  (3) chỉ dùng attacks sẽ thưởng cho hàm always-block, clean controls mới phát hiện
  false positive; (4) output rail chạy trong ngữ cảnh hội thoại, output sạch phải được
  giữ nguyên chứ không thay bằng câu của rail.
- Giới hạn/cách xử lý: `annoy` không có wheel sẵn cho Windows nên phải cài MSVC Build
  Tools mới build được; `pyarrow` bản mới đòi NumPy 2 nên phải hạ về 16.1.0 để khớp
  `numpy==1.26.4`; gateway từ chối `n>1` khi bật thinking nên phải tắt thinking trong
  `m4_eval`/`m5_enrichment`. Cả ba vấn đề đều kiểm chứng lại bằng import/pip check và
  lần chạy thật, không suy đoán.
- Nguồn/AI hỗ trợ nếu có: năm module `m1`–`m5` là mã Day 18 của chính sinh viên
  (`K4-Track3A-...-Production-RAG`), đưa vào theo yêu cầu lab; hướng dẫn của starter
  (`PIPELINE_INTERFACE.md`, `REPORT_SCHEMAS.md`) dùng để viết adapter. Có dùng Claude
  Code hỗ trợ đọc đề, sửa lỗi tương thích môi trường và diễn đạt báo cáo; mọi số liệu
  trong artifacts/reports đều lấy từ lần chạy thật đã lưu, không có số tự điền.

## Cập nhật sau khi nộp

Bản nộp đầu tiên theo deadline 13/10/2026 11:59 (UTC+07:00); commit dùng để chấm ghi tại
mục "Commit dùng để chấm" ở trên. Nếu phải sửa sau deadline sẽ ghi rõ commit/thời điểm/lý do
tại đây và thông báo coach theo quy ước.
