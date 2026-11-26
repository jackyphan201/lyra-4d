# Thiết kế Lyra 4-D

## Mục tiêu
- Lyra nhận mọi lượt trước khi agent chọn skill.
- Đầu ra đúng ý với ít token và ít lượt hỏi nhất.
- Skill upstream được dùng nguyên bản và chỉ được gọi trong phạm vi người dùng đã xác nhận.

## Một nguồn, nhiều adapter

| Nguồn (sửa ở đây) | Sinh ra (bằng `tools/build.py`) |
|---|---|
| `core/LYRA-CORE.md`: quy tắc 4-D, bảng quyết định, định tuyến, ràng buộc | Lõi trong plugin Claude, khối AGENTS.md/GEMINI.md, `project/LYRA-PROJECT.md`, bản sao trong `skills/lyra/` |
| `core/LYRA-TICK.md`: ghi chú mỗi lượt (khoảng 50 token) | Plugin Claude, runtime hook |
| `skills/lyra/SKILL.md`, `EXAMPLES.md`: phần đọc khi cần (tối ưu prompt, chẩn đoán, ví dụ) | Plugin Claude, `~/.agents/skills/lyra`, `lyra.zip` |
| `catalog/catalog.json`: gợi ý định tuyến và tác dụng phụ của 53 skill | `skills/lyra/SKILL-MAP.md` (build dừng nếu thiếu skill có trong lock) |

`python3 tools/build.py --check` (đã nằm trong unittest) bảo đảm adapter không lệch nguồn.

## Ngân sách token

- **Mỗi phiên:** lõi 4.031 ký tự. Lõi được nạp một lần: qua hook `SessionStart` (Claude), AGENTS.md (Codex) hoặc GEMINI.md (Gemini). Phép đo A/B thực tế cho lượt đầu tiên: Claude Code **+1.600** token input (gồm lõi, ghi chú lượt và mô tả skill `lyra`), Codex **+936** (xem [RESULTS](RESULTS.md)).
- **Mỗi lượt:** ghi chú khoảng 220 ký tự, tức khoảng 50 token. Ghi chú này chạy qua hook `UserPromptSubmit` hoặc `BeforeAgent`. Không có lần gọi model riêng để phân loại, vì model chính tự áp dụng lõi.
- **Khi cần:** `skills/lyra/SKILL.md` khoảng 1.100 token, `SKILL-MAP.md` khoảng 2.000 token. Chỉ nạp khi người dùng muốn một prompt, muốn chẩn đoán, hoặc khi định tuyến khó.
- Không đưa danh mục skill dài vào mọi prompt. Host đã liệt kê tên và mô tả skill; Lyra chỉ thêm quy tắc chọn.

## Ba sự kiện cần tách bạch

| Sự kiện | Bằng chứng mạnh | Nguồn |
|---|---|---|
| Lyra đã nhận lượt | Hook chạy và ghi log `prompt`, kèm ghi chú "Lyra intake" trong context | `~/.lyra-4d/metrics.jsonl` |
| Lyra đã chọn skill | Workflow đã hiển thị cho người dùng | Câu trả lời |
| Host đã thực sự gọi skill | Lời gọi `Skill` (Claude) hoặc `activate_skill` (Gemini) được log qua `PostToolUse`/`AfterTool`. Với Codex: lệnh đọc `SKILL.md` trong transcript | Log hook, transcript |

## Thứ tự chạy với upstream

- Superpowers muốn chạy trước mọi phản hồi. Bộ cài không đăng ký hook đó và không hiển thị `using-superpowers`. Lõi Lyra nằm trong instructions của người dùng, là tầng mà `using-superpowers` tự nhận là có quyền ưu tiên cao hơn.
- Skill của Matt có hai loại: model-invoked và user-only. Lyra tôn trọng cách phân loại này: không giả lập lời gọi host cho skill user-only, mà mời người dùng tự gõ lệnh hoặc đọc file và ghi rõ là đọc từ file.
- Codex và Gemini đọc chung `~/.agents/skills`, nên chỉ cần một bản cài. Claude Code dùng plugin để có namespace (`mattpocock-skills:`, `superpowers:`). Cách này tránh trùng tên với skill có sẵn của Claude Code, ví dụ `code-review`.

## Toàn vẹn upstream

- `upstream.lock.json` lưu commit, tag, ngày commit, license, danh sách skill (kèm cờ user-only), SHA-256 của mọi file và tree digest.
- Bộ cài tải đúng commit từ codeload, giải nén an toàn (chặn path traversal và link trỏ ra ngoài), so từng file và từ chối nếu thiếu, thừa hoặc lệch.
- Bản copy cho host được so lại bằng `verify`. Gỡ cài đặt chỉ xoá bản copy còn khớp hash; bản bạn đã sửa được giữ lại.
