# Phân tích lỗi Phase A

Nhóm: T3B-Solo-LeThanhTruong

Người phụ trách: Lê Thanh Trường - 2A202602492

Nguồn: `artifacts/ragas_50q.json`; run timestamp: 2026-10-12T06:43:39Z (UTC).
Generation dùng `qwen3.8-flash` qua gateway OpenAI-compatible của lớp; evaluator lấy trực
tiếp từ `metadata.evaluator_models` của `m4.evaluate_ragas` (LLM `qwen3.8-flash` +
embedding `text-embedding-v4`), không lấy `JUDGE_MODEL` thay. Cả 50 answers ở
`generation_mode = "llm"` với `generation_model = "qwen3.8-flash"` — không có câu nào rơi
vào `extractive_fallback`, nên toàn bộ điểm dưới đây là điểm của câu trả lời do LLM sinh,
không lẫn câu trả lời trích nguyên văn context.

## Điểm theo distribution

| Metric | factual (20) | multi_hop (20) | adversarial (10) |
|---|---|---|---|
| faithfulness | 1.000 | 0.586 | 0.969 |
| answer_relevancy | 0.856 | 0.549 | 0.825 |
| context_precision | 1.000 | 0.517 | 0.900 |
| context_recall | 0.858 | 0.587 | 0.658 |
| avg_score | 0.929 | 0.560 | 0.838 |

Khoảng cách giữa factual (0.929) và multi_hop (0.560) là 0.369 — lớn hơn nhiều so với
khoảng cách factual – adversarial (0.091). Nghĩa là khó khăn chính của pipeline không nằm
ở việc bị đánh lửa bởi câu hỏi đối kháng, mà ở việc **ghép nhiều mẩu chính sách rời rạc
thành một câu trả lời**. Riêng `context_recall` của adversarial (0.658) thấp hơn rõ rệt so
với ba metric còn lại của chính nhóm đó (0.969 / 0.825 / 0.900): retrieval lấy thiếu chunk
cho các câu hỏi bẫy phiên bản, dù khi đã có context thì generator vẫn trả lời trung thực
(faithfulness 0.969).

## Bottom 10 và nguyên nhân

| rank | id | distribution | câu hỏi (rút gọn) | avg_score | worst_metric |
|---|---|---|---|---|---|
| 1 | 27 | multi_hop | Thâm niên 7 năm theo v2024 được nghỉ bao nhiêu ngày? | 0.1833 | faithfulness |
| 2 | 39 | multi_hop | So sánh yêu cầu mật khẩu policy v1.0 và v2.0 | 0.2031 | faithfulness |
| 3 | 33 | multi_hop | Manager thâm niên 12 năm: tổng phụ cấp và phép | 0.2500 | answer_relevancy |
| 4 | 40 | multi_hop | Manager thử việc 90 ngày có được hưởng phép năm? | 0.2500 | answer_relevancy |
| 5 | 21 | multi_hop | Senior 9 năm thâm niên: số ngày phép và khung lương | 0.3750 | answer_relevancy |
| 6 | 35 | multi_hop | Junior P1 lương 12 triệu: phụ cấp và lương gross | 0.4015 | context_precision |
| 7 | 22 | multi_hop | Mua laptop 30 triệu cho nhân viên mới cần ai duyệt? | 0.5309 | context_precision |
| 8 | 37 | multi_hop | Tự ý xóa malware rồi chia sẻ file — vi phạm gì? | 0.5765 | context_recall |
| 9 | 25 | multi_hop | Lương thử việc Junior mức cao nhất kèm phụ cấp | 0.5894 | faithfulness |
| 10 | 24 | multi_hop | Tạm ứng 15 triệu thanh toán sau 20 ngày bị phạt gì? | 0.6126 | faithfulness |

Cả 10 câu đều là `multi_hop` — không có câu factual nào lọt vào bottom, khớp với bảng
điểm ở trên. Diagnosis/suggested_fix trong JSON được giữ nguyên từ Task 3 (lấy từ
`DIAGNOSTIC_TREE` theo `worst_metric` của từng câu), không bị exporter tính lại.

Đọc nội dung ba câu đại diện để phân biệt lỗi retrieval và lỗi generation:

**Câu 27 (avg 0.183, worst = faithfulness).** Hỏi số ngày phép của người thâm niên 7 năm
theo v2024 — cần 15 ngày cơ bản cộng số ngày thâm niên làm tròn theo "1 ngày mỗi 3 năm".
Contexts lấy về chứa quy tắc và bảng lương nhưng không chứa đủ câu quy đổi 7 năm, nên câu
trả lời tự suy diễn ra con số không được context hỗ trợ → faithfulness sập xuống mức thấp
nhất trong cả 50 câu. Đây là lỗi **retrieval thiếu mẩu**, không phải generator bịa hoàn
toàn.

**Câu 39 (0.203, faithfulness).** So sánh mật khẩu giữa v1.0 và v2.0 — hai văn bản nằm ở
hai file khác nhau (`mat_khau_v1.md`, `mat_khau_v2.md`). Truy vấn không nêu rõ cần cả hai
phiên bản nên hybrid search trả về chủ yếu một phía; thiếu vế thứ hai thì phần so sánh
trong câu trả lời không có căn cứ trong context. Đây là dạng lỗi mà tăng `HYBRID_TOP_K`
có thể vá, nhưng cách chắc hơn là tách câu hỏi so sánh thành hai truy vấn con.

**Câu 21 (0.375, answer_relevancy).** Senior 9 năm cần cả số ngày phép và khung lương.
Contexts có cả hai loại thông tin, câu trả lời cũng đúng nội dung, nhưng `answer_relevancy`
thấp vì answer bám sát context hơn là bám câu hỏi (trả lời dàn ra nhiều chi tiết lương
không được hỏi tới). Đây là lỗi **prompt generation**, không phải retrieval — cùng dấu
hiệu với 4 câu còn lại có `worst_metric = answer_relevancy`.

Ba nhóm nguyên nhân rút ra: (a) retrieval thiếu mẩu cho câu cần ghép nhiều file (27, 39,
37), (b) generator trả lời lan man so với câu hỏi (33, 40, 21), (c) context lấy về có
nhiều chunk nhiễu làm precision thấp (35, 22). Không có câu nào thất bại vì generator phản
bội context một cách tùy tiện — faithfulness của factual và adversarial đều trên 0.96.

## Matrix và nhóm yếu nhất

| worst_metric | factual | multi_hop | adversarial | tổng |
|---|---|---|---|---|
| faithfulness | 0 | 8 | 0 | 8 |
| answer_relevancy | 14 | 5 | 1 | 20 |
| context_precision | 1 | 5 | 2 | 8 |
| context_recall | 5 | 2 | 7 | 14 |
| **cột (cỡ nhóm)** | **20** | **20** | **10** | 50 |

Nhóm yếu theo mean thấp nhất: multi_hop; mean: 0.560 (vs factual 0.929, adversarial 0.838).
Worst metric xuất hiện nhiều nhất: answer_relevancy; số câu: 20.

Matrix đếm **mọi** câu theo metric thấp nhất của chính câu đó, không định nghĩa tất cả là
failure — nên cột 20/20/10 chỉ là cỡ nhóm và không dùng để chọn nhóm yếu. Nếu chọn theo
cột lớn nhất thì sẽ luôn ra factual hoặc multi_hop chỉ vì chúng có 20 câu, trong khi thực
tế factual đạt 0.929 — cao nhất. Nhóm yếu được chọn bằng mean: multi_hop, đúng như bottom
10 toàn câu multi_hop.

Đáng chú ý là **hai metric dẫn đầu hai chiều ngược nhau**: `answer_relevancy` là worst
metric nhiều nhất (20 câu) nhưng tập trung ở factual (14/20), còn `context_recall` đứng
nhì (14 câu) lại tập trung ở adversarial (7/10). Với factual, vấn đề là câu trả lời dài
dòng hơn câu hỏi; với adversarial, vấn đề là retrieval lấy thiếu văn bản — hai bệnh khác
nhau, cần hai cách sửa khác nhau, và đây chính là lý do không nên gộp bốn metric thành một
kết luận nguyên nhân duy nhất trước khi đọc từng câu.

Đề xuất sửa, kèm cách chạy lại để biết có hiệu quả:
1. **Tăng độ phủ retrieval cho câu ghép** — nâng `RERANK_TOP_K` từ 3 lên 5 và
   `HYBRID_TOP_K` lên 30, chạy lại Phase A, so `context_recall` của 20 câu multi_hop
   (mục tiêu > 0.70). Đây là thay đổi rẻ nhất và đo được ngay.
2. **Tách truy vấn so sánh nhiều phiên bản** — với câu dạng "so sánh v1.0 và v2.0", sinh
   hai truy vấn con rồi hợp nhất context, đo lại riêng câu 39.
3. **Siết prompt generation theo câu hỏi** — yêu cầu trả lời đúng trọng tâm được hỏi thay
   vì liệt kê mọi thông tin trong context; đo lại `answer_relevancy` trung bình của nhóm
   factual (mục tiêu > 0.90), vì đây là 14/20 câu có worst metric này.

## Bẫy adversarial và giới hạn

Adversarial có mean 0.838, **thấp hơn factual 0.929** nhưng cao hơn multi_hop 0.560.
Việc một nhóm đối kháng đạt điểm cao cho thấy pipeline không bị lừa hoàn toàn: câu bẫy
phiên bản số 41 (hỏi "nghỉ bao nhiêu ngày phép năm" mà không nêu phiên bản, trong khi
corpus còn cả `nghi_phep_nam_v2023.md`) được trả lời đúng theo v2024 hiện hành với
faithfulness cao, nghĩa là retriever đã ưu tiên đúng văn bản mới.

Tuy vậy, **điểm thấp hơn không tự chứng minh pipeline nhận ra bẫy**. Chỉ số duy nhất chỉ
về phía đó là `context_recall` của nhóm adversarial (0.658) thấp hơn ba metric còn lại
của chính nhóm; nghĩa là có những câu mà retriever lấy thiếu văn bản, và ta chưa tách bạch
được đâu là "chọn đúng phiên bản" và đâu là "bỏ sót phiên bản cũ nên câu trả lời thiếu vế
đối chiếu". Muốn khẳng định pipeline thực sự xử lý version conflict, cần đọc thủ công cả
10 câu adversarial và đối chiếu context với cả hai phiên bản — việc này chưa làm trong
phạm vi 50 câu của lab.

Giới hạn của kết luận: bộ đo chỉ có 50 câu (10 adversarial), đủ để thấy khác biệt lớn giữa
các nhóm nhưng không đủ để kết luận thống kê về từng dạng lỗi; cả 50 answers đều do một
model sinh trong một lượt nên số đo gắn với model đó; hai PDF trong corpus là bản scan ảnh
không có text layer nên bị `load_documents()` bỏ qua — mọi câu hỏi rơi vào nội dung hai
file này sẽ luôn có `context_recall` thấp vì thông tin không tồn tại trong index, và đây
là nguyên nhân hệ thống chứ không phải lỗi từng câu.
