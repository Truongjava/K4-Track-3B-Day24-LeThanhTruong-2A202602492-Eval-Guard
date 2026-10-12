# Đánh giá LLM Judge Phase B

Nhóm: T3B-Solo-LeThanhTruong

Người phụ trách: Lê Thanh Trường - 2A202602492

Nguồn: `artifacts/judge_results.json`; run timestamp: 2026-10-12T06:47:25Z (UTC).
Models: generation là `qwen3.8-flash` (đọc từ `answers_50q.json`), judge là `qwen3.8-flash`
cho cả pairwise lẫn binary — khai trong `metadata.models.judge`. Cùng một model đóng hai
vai ở môi trường này vì gateway của lớp không có kênh `gpt-4o-mini`; điều đó không ảnh
hưởng tính đúng của phép đo, nhưng là hạn chế cần nhớ khi diễn giải (xem mục giới hạn).

## Năm cặp A/B và hai lượt

Nguồn cố định: A từ artifacts/answers_50q.json:answer; B từ
fixtures/human_labels_10q.json:model_answer; reference từ fixtures/test_set_50q.json:ground_truth.
Ids: 1, 5, 12, 21, 41. Không đổi nguồn sau khi xem kết quả judge; `pair_sources` trong
JSON ghi đúng ba đường dẫn này.

| id | A (pipeline) | B (human model_answer) | pass1 | pass2 (đã quy về A/B) | final | consistent | scores pass1 / pass2 |
|---|---|---|---|---|---|---|---|
| 1 | "…nghỉ **3 ngày làm việc** khi kết hôn." (52 ký tự) | "…3 ngày làm việc **có lương** khi kết hôn." (57) | B | B | **B** | True | A 0.75 / B 0.90 — pass2 A 0.75 / B 0.90 |
| 5 | "…trên 50 triệu cần **Tổng Giám đốc (CEO)** phê duyệt…" (98) | "Cần Giám đốc phòng ban phê duyệt." (33) | A | A | **A** | True | A 1.00 / B 0.00 — pass2 A 1.00 / B 0.00 |
| 12 | "…thưởng Tết tối thiểu **1 tháng lương** cho nhân viên chính thức từ 6 tháng…" (42) | "Nhân viên được thưởng Tết tối thiểu 1 tháng lương." (50) | A | tie | **tie** | False | A 0.95 / B 0.80 — pass2 A 0.85 / B 0.85 |
| 21 | "…18 ngày phép (15+3). Khung lương Senior 20–35 triệu…" (85) | "18 ngày phép (15+3). Lương Senior 20–35 triệu…" (82) | B | B | **B** | True | A 0.60 / B 1.00 — pass2 A 0.50 / B 1.00 |
| 41 | "…**15 ngày** phép năm (theo v2024)." (108) | "…nghỉ **12 ngày** phép năm." (37) | A | A | **A** | True | A 0.90 / B 0.20 — pass2 A 0.90 / B 0.10 |

Position bias count/rate: 1/5 = 0.200.
Verbosity win rate: 0.750; decisive cases: 4.

Hai lượt cho kết luận khác nhau ở **đúng một cặp, id 12**: lượt 1 chọn A (A súc tích và
bám câu hỏi hơn, B nói "nhân viên" chung chung), lượt 2 khi thứ tự đảo lại thì chấm cả hai
0.85 và cho tie (lý do: cả hai đều chưa nêu điều kiện "từ 6 tháng trở lên"). Đọc kỹ hai
reasoning thì thấy judge **không** đổi ý vì vị trí — nó đổi vì lượt 2 chú ý tới một tiêu
chí khác (điều kiện áp dụng) mà lượt 1 bỏ qua. Đây là dấu hiệu bất ổn định của judge chứ
chưa chắc là position bias; quy tắc swap-and-average vẫn xử lý đúng bằng cách hạ cặp này
xuống `tie`, nên nó không được tính là "decisive" trong thống kê verbosity.

Verbosity rate 0.750 (3/4 cặp decisive) trông cao, nhưng nếu đọc nội dung thì **không phải
judge thiên vị câu dài**: ở cặp 5 và 41, câu A dài hơn thắng vì B sai nội dung (B nêu
"Giám đốc phòng ban" thay vì CEO; B nêu 12 ngày theo policy cũ), đúng theo reference —
đây là thắng vì đúng, không phải vì dài. Cặp 1 là ngoại lệ thật: B dài hơn A đúng 5 ký tự
và thắng chỉ vì có thêm chữ "có lương" — chênh lệch nhỏ tới mức đây có thể là nhiễu hơn là
tín hiệu. Vì vậy tỉ lệ 0.75 chỉ nên đọc như **dấu hiệu cần theo dõi**, và kết luận đúng
phải dựa trên nội dung: với 5 cặp thì 3/4 không đủ để khẳng định verbosity bias tồn tại.

## Calibration đúng model_answer

Helper đánh giá đúng question/model_answer đang có trong fixtures/human_labels_10q.json;
không lấy answer mới của pipeline. Prompt chỉ nhận question, answer, reference (dựng bằng
`json.dumps` trong `judge_binary`), không gửi `human_label`, `human_note` hay phân bố
nhãn human.

| question_id | nhãn judge | nhãn human | agree | lý do judge (rút gọn) |
|---|---|---|---|---|
| 1 | 1 | 1 | ✓ | Khớp ý chính "3 ngày làm việc có lương khi kết hôn" |
| 5 | 0 | 0 | ✓ | 55 triệu > 50 triệu → cần CEO, không phải Giám đốc phòng ban |
| 12 | 1 | 1 | ✓ | Đúng mức thưởng Tết tối thiểu 1 tháng lương cho đúng đối tượng |
| 21 | 1 | 1 | ✓ | Đúng v2024: 18 ngày phép (15+3) và lương Senior 20–35 triệu |
| 23 | 1 | 1 | ✓ | Đúng số tiền hoàn trả 25 triệu và lý do nghỉ trước hạn cam kết |
| 29 | 0 | 0 | ✓ | Thiếu ý phê duyệt bắt buộc (Trưởng phòng + Kế toán trưởng) |
| 33 | 1 | 1 | ✓ | Đúng phụ cấp Manager 1.500.000 VNĐ/tháng và 19 ngày phép v2024 |
| 41 | 0 | 0 | ✓ | Dùng chính sách v2023 đã bị thay thế (12 ngày) thay vì v2024 |
| 46 | 1 | 1 | ✓ | Đúng: thử việc không được nghỉ phép năm, cần thì xin nghỉ không lương |
| 50 | 0 | 0 | ✓ | Reference cấm VPN cá nhân/NordVPN, bắt buộc WireGuard công ty |

Cohen's κ: **1.000**.
Observed agreement = 10/10 = 1.000. Phân bố nhãn: judge `[1,0,1,1,1,0,1,0,1,0]` và human
`[1,0,1,1,1,0,1,0,1,0]` — cùng 6 nhãn 1 và 4 nhãn 0. Chance agreement
p_e = (6×6 + 4×4) / 10² = (36 + 16)/100 = 0.520, nên
κ = (1.000 − 0.520) / (1 − 0.520) = **1.000**.

Diễn giải theo thang Landis-Koch: κ = 1.0 nằm ở mức "almost perfect". Nhưng với n = 10 và
p_e = 0.52, κ = 1.0 nghĩa là judge khớp người **trên toàn bộ 10 mẫu** — đây là kết quả rất
tốt, đồng thời là trường hợp mà κ dễ đạt cực đại một cách may mắn: chỉ cần lệch một nhãn là
κ tụt xuống khoảng 0.79. Vì vậy κ = 1.0 nên được đọc là "trên 10 câu này judge không lệch
người", chứ không phải "judge đáng tin tuyệt đối". Đáng chú ý là các ca khó đều được xử lý
đúng lý do: id 41 và 50 đều bị chấm 0 vì **phiên bản/phạm vi chính sách**, đúng loại bẫy
mà đề bài cài vào corpus.

## Giới hạn và cách dùng judge

Bốn giới hạn cần nói rõ:

1. **Cỡ mẫu nhỏ.** 5 cặp và 10 nhãn là mức tối thiểu để thấy lệch lớn, không đủ để ước
   lượng độ ổn định. Với κ, khoảng tin cậy quanh 1.0 trên 10 quan sát rất rộng; muốn kết
   luận judge dùng được cho production thì cần mở rộng bộ nhãn người lên cỡ vài chục câu.

2. **Judge và generation cùng một model.** Ở môi trường này `qwen3.8-flash` vừa sinh
   answers vừa làm judge. Self-preference bias (model ưu tiên văn phong giống nó sinh ra)
   là rủi ro có thật và **không thể đo bằng bộ dữ liệu hiện có** vì không có nhánh đối
   chứng dùng judge khác họ. Trước khi tin κ = 1.0 như bằng chứng chất lượng judge độc
   lập, cần chạy lại calibration với một model khác làm judge và so κ.

3. **Bất ổn định ở cặp 12 cho thấy judge nhạy với thứ tự và cách diễn giải tiêu chí.**
   Quy tắc swap-and-average phát hiện và hạ nó xuống `tie`, nhưng nếu chỉ chạy một lượt
   thì cặp đó đã được ghi nhận là "A thắng" một cách tự tin (0.95 vs 0.80). Kết luận thực
   dụng: **không dùng kết quả một lượt của judge này để ra quyết định**, luôn chạy swap.

4. **Case lệch với human và cách kiểm chứng.** Trong lượt chạy này không có case nào lệch
   (10/10). Nếu có, cách kiểm chứng đề xuất là: đọc reference và model_answer gốc trước,
   xác định answer có bỏ sót ý thiết yếu/đảo phủ định/dùng sai phiên bản hay không, rồi
   mới kết luận bên nào sai — không lấy nhãn human làm chân lý mặc định, vì chính bộ nhãn
   người cũng chỉ có 10 mẫu do một người gán.

Vì bốn lý do trên, judge ở đây được dùng như **công cụ sàng lọc và tạo tín hiệu**, không
phải nguồn chân lý: kết quả của nó cần được đối chiếu với RAGAS (Phase A) và với quyết
định guard (Phase C) trước khi dùng để chặn phát hành.
