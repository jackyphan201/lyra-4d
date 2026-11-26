# Kết quả kiểm thử, phiên bản 0.1.0 (26/11/2026)

## Phạm vi và cách chạy

| Hạng mục | Cách kiểm | Trạng thái |
|---|---|---|
| Unit test offline (25 test) | `cd tests && python3 -m unittest`, với upstream giả trong HOME tạm; GitHub Actions trên Ubuntu và macOS × Python 3.12/3.13, cùng Python hệ thống của macOS | **Đã chạy: đạt 25/25, CI 5/5 job xanh** |
| Claude Code CLI 2.1.331, model `claude-opus-5-5` | `tests/live/run_live.py --host claude`, chế độ `-p`, chỉ cho phép Read/Glob/Grep/Skill (ghi file bị từ chối và được ghi nhận) | **Đã chạy thật** |
| Codex CLI 0.171.0-alpha.13.2, model mặc định của tài khoản | `tests/live/run_live.py --host codex`, sandbox `read-only` | **Đã chạy thật** (2 lượt toàn bộ, ca 2 và 3 thêm lượt thứ 3). Hook của Lyra **chưa được trust**, nên lõi chỉ đến qua AGENTS.md |
| Gemini CLI | Cài vào HOME tạm, kiểm tra `settings.json`, `GEMINI.md`, hook `BeforeAgent`, idempotency và gỡ cài đặt | **Chỉ xác minh cấu hình.** Máy thử chưa cài Gemini CLI |
| Tab Code của Claude desktop | Một phiên tương tác đang mở từ trước khi cài: hook log ghi lượt 1 nhận lõi qua cơ chế dự phòng (4.256 ký tự), lượt 2 và 3 chỉ nhận ghi chú (222 ký tự); ghi chú Lyra xuất hiện trong context của phiên | **Đã chạy thật** (hook và cơ chế dự phòng). Chưa chạy lại 9 ca trong desktop |
| Cài "chỉ Lyra" từ GitHub cho Claude Code | `claude plugin marketplace add jackyphan201/lyra-4d` rồi `plugin install lyra-4d@lyra-4d`, trong thư mục cấu hình Claude tạm | **Đã chạy thật**: plugin cài được, có đủ 3 hook và skill `lyra` |
| Cài từ repo công khai | Clone mới từ GitHub, `build.py --check`, unittest, `install --hosts codex,gemini` vào HOME tạm (tải upstream thật, kiểm 411 file), `verify` | **Đã chạy thật**: đạt |
| ChatGPT / Claude / Gemini Projects | Không có API tự động hoá | **Chưa kiểm tra được.** Có file và hướng dẫn để kiểm tra tay |

**Phương pháp chấm.** Mỗi ca chạy một lần (n=1) trên mỗi host, trong một bản sao mới của fixture. Kết quả được chấm bằng cách đọc transcript và so với tiêu chí nghiệm thu; không dùng model thứ hai để chấm. Bằng chứng host:
- Lời gọi tool lấy từ stream của host: `Skill` của Claude, lệnh `cat …/SKILL.md` của Codex.
- Sự kiện hook lấy từ `~/.lyra-4d/metrics.jsonl`.
- Lần ghi file bị từ chối lấy từ `permission_denials`.

Kết quả thô nằm trong `tests/live/results/` và không được đưa lên git vì có đường dẫn máy cục bộ.

**Giới hạn.**
- n=1 mỗi ca: kết quả cho thấy hành vi điển hình, không phải tỷ lệ thống kê.
- Phiên thử dùng môi trường thật của người dùng: có thêm plugin và memory khác. Ví dụ, Codex đôi khi nhắc tới bối cảnh tổ chức lấy từ memory.
- Hook log dùng chung cho cả máy. Nếu người dùng mở phiên khác cùng lúc, sự kiện có thể lẫn vào ca đang chạy.

## Kết quả theo ca

Ký hiệu: ✅ đạt, ⚠️ đạt nhưng có ghi chú, ❌ không đạt. "Vòng hỏi" là số lượt trả lời có câu hỏi làm rõ trước khi giao đầu ra đích.

| Ca | Kỳ vọng | Claude Code | Codex |
|---|---|---|---|
| 1. Dịch, giữ 3 bullet | Làm ngay, đúng định dạng | ✅ 3 bullet tiếng Anh, không workflow, 0 vòng hỏi | ✅ như Claude (2/2 lượt) |
| 2. Công cụ cho PO, không có tài liệu | Lyra chạy trước, xem ngữ cảnh, chọn làm rõ hoặc thiết kế, không viết code | ✅ chạy `ls`, đề xuất workflow `brainstorming → writing-plans → prototype`, hỏi 1 câu, không tạo file. Có xét thêm một skill xếp ưu tiên từ plugin khác thực sự có trong môi trường người dùng | ⚠️ Lượt 1 (lõi cũ): không xem workspace, đề xuất kèm 1 câu hỏi. ✅ Lượt 2 và 3 (lõi đã sửa): xem workspace, đề xuất kèm 1 câu hỏi |
| 3. Như ca 2, có brief | Không hỏi lại người dùng, mục tiêu, tiêu chí | ✅ đọc `docs/po-priority-brief.md`, tóm tắt brief, chỉ hỏi chỗ brief còn thiếu (CSV chưa có số lượt yêu cầu, điểm OKR) | ❌ Lượt 1 (lõi cũ): không đọc brief, hỏi lại phạm vi. ✅ Lượt 2 và 3: đọc brief, giữ đúng các tiêu chí, hỏi 1 câu về dữ liệu còn thiếu |
| 4. "Phỏng vấn tôi thật kỹ" | Nhánh grilling, câu sau dựa trên câu trước | ✅ host gọi `mattpocock-skills:grilling` (có `PostToolUse` log). Vòng 2 dựa trên câu trả lời (người đi làm, 10 phút, chuỗi 30 ngày) và chỉ ra chỗ mâu thuẫn với giả định vòng 1 | ✅ đọc `grilling/SKILL.md`. Vòng 2 dựa trên câu trả lời |
| 5a. Báo cáo nghiên cứu có nguồn | DETAIL, trình workflow, chờ xác nhận | ✅ workflow với skill `research` (agent nền, ghi 1 file), hỏi 1 câu xác nhận phạm vi, chưa gọi skill | ✅ như Claude |
| 5b. Tra cứu nhanh | Trả lời ngay | ✅ "5432" | ✅ "5432/TCP" |
| 6. "Chọn B, chỉ làm bản nháp" | Tiếp nhánh B, giữ giới hạn | ✅ bản nháp giọng B, không ghi file, có chỗ trống để điền | ✅ như Claude |
| 7. Spec đã duyệt → kế hoạch | Dùng `writing-plans`, không brainstorming lại | ⚠️ đọc spec, host gọi `superpowers:writing-plans`, không brainstorming. Skill định ghi `docs/superpowers/plans/…` nhưng bị chế độ thử từ chối, nên trình bày kế hoạch trong chat và liệt kê các quyết định model tự chốt | ✅ đọc `writing-plans/SKILL.md`, không brainstorming. Kế hoạch trình bày trong chat vì sandbox chỉ đọc |
| 8. Project có quy tắc riêng, thiếu skill | Vẫn áp dụng Lyra, báo trung thực skill đã gọi | ✅ theo đúng quy tắc project ("Quý phụ huynh", tên ≤ 4 từ, "[sẽ cập nhật]", "Người phụ trách"). Dòng chẩn đoán `intake=yes … invoked=none … basis=hook+transcript` | ✅ theo đúng quy tắc. Lượt 1 báo `intake=no` (đúng, vì hook chưa trust) và ghi rõ đã đọc file skill `lyra`. Lượt 2 `invoked=không basis=transcript` |
| 9. Chạy lại hoặc cập nhật bộ cài | Giữ cấu hình, không trùng hook, upstream nguyên vẹn | ✅ trên máy thật: sau 4 lần `install/update`, có 1 hook Lyra trong `~/.codex/hooks.json`, 1 khối trong AGENTS.md, quy tắc Scrapling của người dùng vẫn giữ, `verify` báo nguyên vẹn. Unit test kiểm cả Gemini, rollback và trường hợp file bị sửa | ✅ (dùng chung) |

Ghi chú về ca 7: theo lõi, một yêu cầu "lập kế hoạch" được hiểu là đồng ý tạo tài liệu kế hoạch, nên skill tự ghi file. Nếu muốn mọi lần ghi file đều phải hỏi trước, đây là điểm cần chỉnh.

## Chỉ số

| Chỉ số | Claude Code | Codex | Cách đo |
|---|---|---|---|
| Ký tự Lyra chèn mỗi phiên | 4.031 (lõi qua `SessionStart`) | khoảng 4.200 (khối AGENTS.md, có trong mọi request) | Log hook, kích thước file |
| Ký tự Lyra chèn mỗi lượt | 223 (ghi chú), +khoảng 100 khi `lyra diag` | 0 khi hook chưa trust; 223 sau khi trust | Log hook (`metrics`): trung bình 228 ký tự/lượt trên 16 lượt |
| Token input thêm, A/B cùng prompt 1 lượt, 3 lần mỗi nhánh | Trung vị **+1.600** (28.087–28.246 so với 26.000–26.489) | Trung vị **+936** (25.821–25.823 so với 24.885–24.887) | Token do host báo; Claude: cả hai nhánh tắt 2 plugin upstream để chỉ Lyra khác nhau |
| Lần gọi model bổ sung để phân loại | **0** | **0** | Hook là script Python cục bộ, không gọi model; `num_turns` của ca 1 và 5b bằng baseline |
| Vòng hỏi làm rõ trước khi giao đầu ra (ca 1–8) | 0 ở ca 1, 5b, 6 (lượt 2), 7, 8; 1 ở ca 2, 3, 5a (chờ xác nhận); ca 4 là phỏng vấn có chủ đích | Như Claude (lượt 2) | Đọc transcript |
| Tỷ lệ hỏi thừa (hỏi điều tài liệu đã trả lời, hoặc hỏi khi không cần) | 0/9 | 1/9 ở lượt 1 (ca 3), 0/9 ở lượt 2 sau khi sửa lõi | Đọc transcript |
| Bỏ sót quyết định quan trọng | 0/9. Ca 7: model tự chốt vài điểm spec chưa nói và **liệt kê rõ** để người dùng soát | 0/9 | Đọc transcript |
| So với không có Lyra (ca 2) | Baseline gọi ngay `brainstorming` (khoảng 3,7k token on-invoke) rồi hỏi 1 câu. Lyra đề xuất workflow và chưa gọi skill trước khi người dùng xác nhận | Baseline: đọc `brainstorming/SKILL.md` ngay, input 53.636 so với 25.816 khi có Lyra | Đọc transcript và token do host báo |

Token toàn request giữa các lần chạy đơn lẻ dao động khoảng ±5.000 token do môi trường (danh sách skill, plugin khác, cache). Vì vậy chỉ số token dùng phép đo A/B lặp lại ở trên, không dùng hiệu số của một cặp chạy.

## Điều chỉnh sau kiểm thử
1. Codex lượt 1 bỏ qua tài liệu ở ca 3 → bước Diagnose của lõi giờ yêu cầu liệt kê workspace và đọc tài liệu liên quan trước khi hỏi. Lượt 2 đạt.
2. Claude chạy lại `SessionStart` khi resume, nên lõi bị nạp hai lần (ca 4, ca 6) → hook bỏ bản sao khi `source=resume` và phiên đã có lõi. Đã thêm unit test.
3. Yêu cầu trực tiếp đúng việc của một skill chỉ đọc và hỏi (ví dụ "phỏng vấn tôi") giờ được tính là xác nhận, nên không tốn thêm một lượt hỏi.

## Việc người dùng cần làm để hoàn tất kiểm chứng
- Codex: trust hook "Lyra intake" (`/hooks` trong CLI, hoặc Settings → Hooks trong app), rồi gõ `lyra diag` và kiểm tra `intake=yes`.
- Gemini CLI: cài Gemini CLI, chạy `python3 installer/lyra4d.py install --hosts gemini`, rồi `/hooks` và `lyra diag`.
- Projects trên web: làm theo [`project/PROJECT-INSTRUCTIONS.md`](../project/PROJECT-INSTRUCTIONS.md), rồi thử ca 1, 3 và 6 bằng tay.
