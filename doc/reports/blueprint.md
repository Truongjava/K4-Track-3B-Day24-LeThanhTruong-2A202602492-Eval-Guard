# Blueprint CI/CD cho RAG và guardrails

Nhóm: T3B-Solo-LeThanhTruong

Người phụ trách: Lê Thanh Trường - 2A202602492

Đây là **đề xuất CI/CD**, không phải workflow đã được triển khai/chạy.
Nguồn kết quả: artifacts/ragas_50q.json, judge_results.json, guard_results.json.

Run timestamps (UTC): Phase A `2026-10-12T06:43:39Z`, Phase B `2026-10-12T06:47:25Z`,
Phase C `2026-10-12T06:51:31Z`. Guard models (từ `config.models` của NeMo instance thật):
`qwen3.8-flash`. Models theo vai trò: generation `qwen3.8-flash` (Phase A/B),
evaluator `qwen3.8-flash` + `text-embedding-v4` (Phase A, lấy từ m4), judge
`qwen3.8-flash` (Phase B), guard `qwen3.8-flash` (Phase C). Gateway của lớp không có kênh
`gpt-4o-mini` nên mọi vai trò dùng model khả dụng; ID ghi trong từng report là ID thật của
lượt chạy, không phải model mặc định của đề bài.

## Kiến trúc và failure action

Input → Presidio → NeMo input → RAG → NeMo output → response.
Request thực dừng sớm khi bị chặn; khác phép đo input layers chạy đủ hai tầng.

**Data flow khi chạy thật.** Câu hỏi đi vào Presidio trước vì đây là tầng rẻ nhất và
đồng bộ (regex + spaCy NER, không gọi mạng): phát hiện CCCD/CMND, số điện thoại VN và
email thì chặn ngay, không tốn lượt gọi LLM. Chỉ khi Presidio sạch mới gọi NeMo input
rail — một lượt self-check hỏi LLM "câu này có nên chặn không" theo policy trong
`guardrails/config.yml`: off-topic, jailbreak, mạo danh quyền hạn, yêu cầu lấy system
prompt, hoặc hỏi dữ liệu cá nhân của người khác. Qua được hai tầng này thì truy vấn vào
RAG (BM25 + dense BGE-M3 + RRF → cross-encoder rerank top-3 → generation), rồi câu trả
lời đi qua NeMo output rail để chặn PII, lương cá nhân, mật khẩu, hồ sơ nhân viên.
Điểm đáng chú ý: output rail chạy trong ngữ cảnh hội thoại nên answer sạch phải được
**giữ nguyên**, chỉ answer bị chặn mới thay bằng câu từ chối — điều này được kiểm tra
bằng 4 output case (2 sạch, 2 nhạy cảm) chứ không chỉ đếm số block.

**Failure action.** Chặn ở Presidio: trả câu từ chối + ghi nhãn `blocked_by="presidio"`
kèm offset entity để audit, **không** log nguyên văn PII. Chặn ở NeMo input: trả câu từ
chối trong `rails.co`, ghi `blocked_by="nemo_input"`. Chặn ở output: thay answer bằng
câu từ chối, giữ nguyên answer gốc trong log nội bộ đã redact để điều tra. Không có nhánh
"chặn rồi vẫn trả lời" — mỗi quyết định đều là terminal.

**Log/redact và secrets.** `blocked_reason`, `blocked_by`, id và entity type được ghi;
giá trị PII thô không vào log/report. API key chỉ nằm trong `.env` (đã `.gitignore`),
không commit, không đưa vào JSON artifact hay báo cáo; `.env.example` chỉ có tên biến.

**Fallback.** Nếu NeMo không khởi động được, tuyệt đối không "cho qua hết": Presidio vẫn
chạy như tầng độc lập và pipeline trả lỗi cấu hình thay vì phục vụ không guard. Ngược lại
nếu Presidio lỗi, coi như fail-closed và vẫn gọi NeMo input rail (đắt hơn nhưng không bỏ
guard). Về generation, `run_query` rơi về `extractive_fallback` khi không có key/contexts
hoặc API lỗi; tỉ lệ và điều kiện rơi được ghi trong `answers_50q.json` để Phase A không
đọc nhầm điểm của câu trả lời extractive như câu trả lời LLM.

## Phạm vi và số đo latency

Bắt buộc Task 12: **input_layers_sequential**, Presidio + NeMo input, không
short-circuit. Engines tạo trước đo; có hai warm-up thật không tính vào mẫu.
Percentile nội suy tuyến tính từ raw samples; tổng từ tổng từng sample.

Số mẫu timed: 20; warm-up: 2;
phương pháp: linear.

| Layer / scope | P50 ms | P95 ms | P99 ms | Tình trạng |
|---|---|---|---|---|
| Presidio | 18.709 | 25.188 | 25.481 | Đã đo Task 12 |
| NeMo input | 2088.167 | 4249.106 | 4557.755 | Đã đo Task 12 |
| Input guard sequential | 2104.414 | 4271.927 | 4576.921 | Đã đo Task 12 |
| RAG | chưa đo | chưa đo | chưa đo | Ngoài phạm vi bắt buộc |
| NeMo output | chưa đo | chưa đo | chưa đo | Ngoài phạm vi bắt buộc |
| Full guard / short-circuit request | chưa đo | chưa đo | chưa đo | Không suy từ input_guard_ms |

Input-layer budget target: 500ms; kết quả thực tế/budget_ok: **P95 4271.927 ms > 500 ms →
`latency_budget_ok = false`**. Số đo vượt budget và được ghi đúng, không sửa số cho đạt.

**Bottleneck là NeMo input rail, không phải Presidio.** Presidio ổn định ở mức 19–25 ms
(P50→P99 chỉ chênh 6.8 ms), tức ~0.6% tổng thời gian và hoàn toàn trong ngân sách. NeMo
input rail chiếm 99.4% còn lại và dao động rất rộng: mẫu nhanh nhất 1.371 ms, chậm nhất
4.653 ms — biên độ 3.4×. Nguyên nhân là self-check gọi LLM qua mạng cho **mỗi** câu (một
lượt chat completion), nên độ trễ bị chi phối bởi gateway chứ không bởi xử lý cục bộ. Với
bộ 20 mẫu này, P95 gấp 8.5× ngân sách.

Ba hướng giảm, xếp theo chi phí/lợi ích:
1. **Chạy Presidio và NeMo song song** thay vì tuần tự — nhưng lưu ý điều này chỉ tiết kiệm
   được ~19 ms (thời gian Presidio), vì NeMo là tầng áp đảo. Không đủ để đưa P95 về 500 ms;
   muốn vậy phải cắt chính NeMo.
2. **Cache kết quả self-check** theo câu hỏi đã chuẩn hoá: trong production, câu hỏi HR lặp
   lại nhiều, cache sẽ hạ P95 về mức Presidio cho phần lớn traffic. Rủi ro: prompt injection
   biến thể nhẹ sẽ trượt cache — cần chuẩn hoá thận trọng hoặc chỉ cache theo hash chính xác.
3. **Thay self-check LLM bằng classifier cục bộ** (ví dụ model nhỏ chạy on-device phân loại
   jailbreak/off-topic) để bỏ hẳn round-trip mạng. Đây là cách duy nhất có cơ hội đưa P95
   xuống dưới 500 ms một cách ổn định, nhưng cần dữ liệu huấn luyện và đánh giá lại độ chính
   xác trên chính bộ 28 inputs này trước khi thay.

Ngân sách 500 ms vì thế nên được đọc là **mục tiêu cho tầng cục bộ (Presidio)**, còn NeMo
input rail cần ngân sách riêng hoặc phải được đưa ra khỏi đường tới hạn (ví dụ chạy bất đồng
bộ và chặn ở output thay vì chặn ở input).

Kế hoạch đo phần ngoài phạm vi: (1) RAG latency — bọc `search → rerank → generate`
bằng `perf_counter` tại đúng ba điểm, lấy ≥50 mẫu cycling test set, tách riêng thời gian
model load khỏi thời gian suy luận; (2) NeMo output — cùng cách với Task 12 nhưng đặt
sau generation, lưu mẫu thô; (3) full guard/short-circuit — đo end-to-end theo **tỉ lệ
chặn thực tế** (không padding bằng request bị chặn sớm) và báo cáo riêng P95 của nhánh
blocked vs allowed, vì gộp chung sẽ che mất chi phí nhánh tốn nhất. Cả ba phần cần
warm-up thật và timestamp ISO để đối chiếu, không dùng input_guard_ms thay thế.

## CI gates đề xuất

Đối chiếu với kết quả lượt chạy này (cột "Lượt này"):

| Gate đề xuất | Ngưỡng | Lượt này | Đạt? |
|---|---|---|---|
| RAGAS faithfulness (trung bình 50 câu) | ≥0.75 | 0.852 | ✓ |
| RAGAS avg_score (trung bình 50 câu) | ≥0.65 | 0.776 | ✓ |
| RAGAS avg_score của nhóm yếu nhất | ≥0.50 | 0.560 (multi_hop) | ✓ |
| Attacks bị chặn | ≥18/20 (bonus/CI) | 20/20 | ✓ |
| Clean controls được cho qua | 8/8, FPR = 0 | 8/8, FPR 0.000 | ✓ |
| Output cases đúng quyết định | 4/4 | 4/4 | ✓ |
| Cohen's κ | >0.6 | 1.000 | ✓ |
| Full guard P95 | <500ms | chưa đo | — |

Mốc bắt buộc lab vẫn attacks ≥15/20; bonus ≥18/20 kèm clean controls đạt.

Hai lưu ý về bảng trên. Thứ nhất, `faithfulness` và `avg_score` trung bình toàn bộ 50 câu
bị **kéo lên bởi nhóm factual** (0.929); nếu chỉ nhìn hai dòng đầu sẽ tưởng pipeline khỏe,
trong khi nhóm multi_hop chỉ đạt 0.560. Vì vậy gate thứ ba (avg_score của nhóm yếu nhất)
mới là gate có ý nghĩa — nó chặn trường hợp một nhóm tụt sâu bị che bởi các nhóm khác. Thứ
hai, dòng "full guard P95" cố ý để **chưa đo** thay vì điền số của input layers: dùng
input_guard_ms làm full-guard latency là suy diễn sai phạm vi, và gate này chỉ được kích
hoạt sau khi đo thật.

Đề xuất job (chưa triển khai): một workflow chạy ba bước tuần tự, mỗi bước trả exit code
khác 0 khi không đạt để chặn merge — nhưng bước `--live` (gọi API, tốn phí) chỉ chạy khi
có secret trong môi trường, còn pull request thường chỉ chạy `check_lab.py` + pytest
offline rồi so artifacts đã commit. Ngưỡng nên đọc từ biến môi trường (`MIN_FAITHFULNESS`,
`MIN_ATTACKS`) và script phải **thực sự so sánh** — khai biến mà không kiểm tra thì không
tạo quality gate. Cụ thể, `check_lab.py` hiện đã chặn cứng 15/20 và clean 8/8; muốn nâng
lên mốc CI 18/20 thì phải sửa chính script đó, không chỉ ghi ngưỡng vào tài liệu.
Ngoài ra nên ghim phiên bản model ở tầng CI vì điểm số phụ thuộc model: đổi model gateway
sẽ làm lệch cả RAGAS lẫn κ mà không có dấu hiệu nào ngoài việc gate đỏ.

## Monitoring và cải tiến

Metric cần theo dõi và ngưỡng cảnh báo: (1) **block rate** theo từng tầng (presidio/nemo_input)
— lệch bất thường về 0 thường là guard chết chứ không phải người dùng ngoan hơn;
(2) **false-positive rate trên clean inputs** — bộ 8 câu sạch là mẫu canary, chạy lại
định kỳ và cảnh báo khi có bất kỳ câu nào bị chặn; (3) **P95 input_guard_ms** so với
budget 500ms, tách theo tầng để biết Presidio hay NeMo là bottleneck; (4) **tỉ lệ
extractive_fallback** khi chạy batch answers — tăng đột biến nghĩa là generation đang lỗi
âm thầm và điểm RAGAS sẽ tụt giả, phải điều tra trước khi kết luận chất lượng RAG giảm;
(5) **κ của judge** chạy lại trên bộ nhãn người định kỳ — κ tụt là dấu hiệu calibration
trôi. Cách lấy mẫu: log mỗi quyết định guard kèm id/latency/blocked_by (không log PII
thô), và giữ một bộ canary tách khỏi test set để tránh overfit.

Xử lý false positives: mọi clean input bị chặn phải được đọc nội dung trước khi sửa —
nếu prompt self-check đang quá rộng thì thu hẹp theo chủ đề thay vì hạ ngưỡng toàn cục,
vì hạ ngưỡng sẽ mở lại đường tấn công. Drift: theo dõi phân bố category của input bị
chặn và độ dài câu hỏi; khi corpus/HR policy đổi phiên bản (v2023 → v2024) phải re-index
và chạy lại bộ 50 câu vì context cũ làm context_recall tụt giả. Privacy: PII chỉ giữ
dạng entity type + offset, không giữ nguyên văn. Người xử lý: ca trực đọc cảnh báo block
rate và fallback rate; thay đổi prompt/policy phải review như code.

RAGAS mean/worst distribution: factual 0.929 / multi_hop 0.560 / adversarial 0.838 — nhóm
yếu nhất là multi_hop (thấp hơn factual 0.369); bottom 10 toàn câu multi_hop.
Cohen's κ: 1.000 (10/10 khớp nhãn người).
Attacks passed: 20/20; clean false_positive_rate: 0.000.

Ba đến năm cải tiến có thể kiểm tra, gắn với bằng chứng của nhóm:
1. **Nâng độ phủ retrieval cho câu multi-hop** — nhóm yếu nhất là multi_hop (0.560) và cả
   10 câu bottom đều thuộc nhóm này, với `context_recall` là worst metric ở 7/10 câu
   adversarial và 2/10 multi_hop. Tăng `HYBRID_TOP_K` lên 30 và `RERANK_TOP_K` lên 5 rồi
   chạy lại Phase A, so `context_recall` của 20 câu multi_hop (mục tiêu > 0.70).
2. **Tách truy vấn so sánh nhiều phiên bản** — câu 39 (`mat_khau_v1` vs `mat_khau_v2`) có
   avg 0.203 vì một truy vấn không kéo về đủ cả hai văn bản; sinh hai truy vấn con rồi hợp
   nhất context và đo lại riêng câu này.
3. **Siết prompt generation theo trọng tâm câu hỏi** — `answer_relevancy` là worst metric
   nhiều nhất (20 câu), tập trung 14/20 ở factual, tức câu trả lời lan man hơn câu hỏi;
   yêu cầu bám đúng điều được hỏi rồi đo lại `answer_relevancy` trung bình factual
   (mục tiêu > 0.90).
4. **Đo full guard thật và tách nhánh blocked/allowed** — hiện chỉ có input layers; cần
   số end-to-end trước khi áp gate 500 ms, và phải báo riêng P95 của hai nhánh vì gộp chung
   sẽ che chi phí nhánh tốn nhất.
5. **Mở rộng bộ nhãn người lên ~40 câu** — κ = 1.0 trên 10 mẫu là kết quả tốt nhưng khoảng
   tin cậy rộng; một nhãn lệch đã kéo κ xuống ~0.79, nên 10 mẫu không đủ để kết luận judge
   ổn định cho production.
6. **Mở rộng clean controls** — bộ 8 câu hiện chỉ phủ leave/salary/VPN/password và lượt này
   đạt 8/8, nhưng đó là mức trần có thể đạt; thêm câu sạch chứa từ ngữ dễ kích hoạt guard
   (nói tới "mật khẩu", "CCCD" trong ngữ cảnh hỏi quy định chứ không hỏi dữ liệu) để bắt
   false positive trước khi lên production. Lưu ý bài học từ lượt chạy này: lỗi chặn nhầm
   7/8 câu sạch ban đầu đến từ NER tiếng Anh của Presidio chứ không từ prompt NeMo, cho nên
   khi thêm clean controls cần kiểm tra lại cả tầng Presidio.
