# Lyra 4-D

Lyra 4-D là lớp tiếp nhận (intake) chạy **trước khi agent chọn skill**. Bạn viết tự nhiên bằng tiếng Việt hoặc tiếng Anh, không cần `$`, `@`, slash command hay tên skill. Ở mỗi lượt, Lyra tự quyết định một trong bốn cách xử lý:

- **Làm ngay** nếu yêu cầu đơn giản và đã rõ (BASIC).
- **Hỏi một câu** nếu yêu cầu ngắn nhưng có nhiều cách hiểu.
- **Đề xuất workflow ngắn rồi chờ xác nhận** nếu yêu cầu phức tạp (DETAIL).
- **Chạy tiếp các bước** nếu bạn đã duyệt workflow.

Lyra điều phối toàn bộ skill của [mattpocock/skills](https://github.com/mattpocock/skills) và [obra/superpowers](https://github.com/obra/superpowers). Bộ cài lấy các skill này từ repo gốc ở commit được ghim, kiểm tra hash và giữ nguyên từng file.

```
prompt ──► Lyra 4-D (Deconstruct → Diagnose → Develop → Deliver)
             ├─ BASIC: trả kết quả ngay
             ├─ mơ hồ: 1 câu hỏi có sức phân biệt nhất
             ├─ DETAIL: "Tôi hiểu bạn muốn… / Workflow đề xuất… / Cần bạn xác nhận…"
             └─ đã duyệt: gọi 0, 1 hoặc nhiều skill theo thứ tự đã chốt
```

- Nguồn chính thức của Lyra: [`core/LYRA-CORE.md`](core/LYRA-CORE.md), khoảng 4.000 ký tự. Phần chỉ đọc khi cần nằm trong [`skills/lyra/`](skills/lyra/SKILL.md).
- Mọi adapter được sinh từ hai nguồn trên bằng `python3 tools/build.py`.
- Kết quả kiểm thử: [`docs/RESULTS.md`](docs/RESULTS.md). Thiết kế: [`docs/DESIGN.md`](docs/DESIGN.md).

## Cài nhanh

Cần `git` và Python 3.8 trở lên. Không cần Node hay pip.

```bash
git clone https://github.com/jackyphan201/lyra-4d.git && cd lyra-4d
```

```bash
python3 installer/lyra4d.py install
```

```bash
python3 installer/lyra4d.py status
```

`install` tự nhận diện host có trên máy (Claude Code, Codex, Gemini CLI). Muốn chỉ định host thì thêm `--hosts claude,codex,gemini`. Thêm `--dry-run` để xem trước thay đổi mà không ghi gì.

Bộ cài thực hiện các việc sau:
1. Tải hai upstream ở commit trong [`upstream.lock.json`](upstream.lock.json) từ `codeload.github.com`, đối chiếu SHA-256 của từng file (175 + 236 file), rồi lưu vào `~/.lyra-4d/store/`. File nào lệch hash thì dừng lại.
2. Cài cho từng host như bảng dưới. Sao lưu mọi file cấu hình trước khi sửa (`~/.lyra-4d/backups/`). Giữ nguyên hook và instructions khác của bạn. Chạy lại nhiều lần không sinh mục trùng.
3. Ghi trạng thái vào `~/.lyra-4d/state.json` để `update`, `uninstall` và `rollback` làm đúng phần của Lyra.

## Bảng tương thích

| Host | Cơ chế | Lyra nhận mọi lượt? | Gọi skill local? | Trạng thái kiểm chứng |
|---|---|---|---|---|
| **Claude Code** (CLI, app desktop tab Code) | Plugin `lyra-4d`: hook `SessionStart` (lõi, mỗi phiên) + `UserPromptSubmit` (ghi chú ngắn, mỗi lượt) + `PostToolUse:Skill` (ghi log) | **Có, bằng hook thật** | Có: 27 skill Matt + 14 skill superpowers (plugin cục bộ) | Chạy thật, xem RESULTS |
| **Codex** (CLI, app) | Khối Lyra ở đầu `~/.codex/AGENTS.md` (lõi, luôn nạp) + hook `UserPromptSubmit` trong `~/.codex/hooks.json` | Lõi: có (AGENTS.md). Hook: chỉ chạy sau khi bạn **trust** | Có: 41 skill + `lyra` trong `~/.agents/skills` | Chạy thật, xem RESULTS |
| **Gemini CLI** | Khối Lyra ở đầu `~/.gemini/GEMINI.md` + hook `BeforeAgent` và `AfterTool:activate_skill` trong `~/.gemini/settings.json` | Có (hook thật, theo tài liệu) | Có: dùng chung `~/.agents/skills` | **Chỉ xác minh cấu hình** (máy thử chưa cài Gemini CLI) |
| **ChatGPT Projects** | Đoạn dán vào Project instructions + file `LYRA-PROJECT.md` | Theo instructions, không có hook | Không. Chỉ skill do ChatGPT hỗ trợ tải lên (tuỳ gói) | Chưa thể kiểm tra tự động |
| **Claude Projects** (claude.ai) | Như trên. Có thể tải `lyra.zip` lên mục Skills | Theo instructions, không có hook | Không. Chỉ skill đã tải lên claude.ai | Chưa thể kiểm tra tự động |
| **Gemini app** (gemini.google.com) | Tải thư mục skill `lyra` lên mục Skills, hoặc đính kèm `LYRA-PROJECT.md` vào cuộc chat | Không có hook. Skill chỉ kích hoạt khi khớp mô tả | Không. Chỉ skill đã tải lên | Chưa thể kiểm tra tự động |

Ba nhóm khác nhau về bản chất:
- **Hook thật mỗi lượt** (Claude Code, Codex sau khi trust, Gemini CLI): host chạy script của Lyra trước khi model nhận prompt. Có log để đối chiếu.
- **Hướng dẫn thường trực** (AGENTS.md, GEMINI.md, Project instructions): luôn nằm trong context, nhưng việc tuân thủ phụ thuộc model.
- **Chỉ có văn bản** (Project trên web, file đính kèm): áp dụng được phương pháp Lyra nhưng không gọi được skill local.

## Hướng dẫn theo nền tảng

### 1. Codex (CLI, app) và ChatGPT, bao gồm ChatGPT Projects

**Codex CLI và Codex app**
- Cài: `python3 installer/lyra4d.py install --hosts codex`.
  - Khối Lyra được đặt ở đầu `~/.codex/AGENTS.md`, phần cũ giữ nguyên bên dưới.
  - Hook `UserPromptSubmit` được ghép vào `~/.codex/hooks.json`.
  - Skill được chép vào `~/.agents/skills/<tên>/`, giữ nguyên từng byte.
  - Nếu đặt `CODEX_HOME` thì bộ cài dùng thư mục đó.
- Kích hoạt không cần gọi tên: AGENTS.md toàn cục luôn được Codex nạp, nên Lyra chạy ở mọi phiên.
- **Trust hook (bắt buộc với hook):** Codex chỉ chạy hook mới hoặc hook đã đổi sau khi bạn duyệt. Trong CLI gõ `/hooks`. Trong app vào **Settings → Hooks** (hoặc **Review hooks** ở ô soạn tin), rồi trust hook "Lyra intake". Chưa trust thì Lyra vẫn chạy qua AGENTS.md, chỉ thiếu ghi chú mỗi lượt và log bằng chứng.
- Xác nhận đã nạp:
  - Gõ `lyra diag` ở cuối một prompt. Câu trả lời kết thúc bằng dòng `lyra: intake=… mode=… chosen=… invoked=… basis=…`. `intake=yes` cùng `host-evidence` nghĩa là hook đã chạy.
  - Ngoài terminal: chạy `python3 installer/lyra4d.py diag`.
- Kiểm tra skill thực tế khả dụng: gõ `/skills` hoặc `$` trong CLI để xem danh sách. Skill user-only của Matt (`grill-me`, `to-spec`, `to-tickets`…) chỉ chạy khi bạn tự gõ `$tên`; Lyra sẽ nhắc bạn khi cần.
- Tắt tạm: `python3 installer/lyra4d.py disable`. Lệnh này gỡ khối AGENTS.md, cho hook im lặng và giữ nguyên skill. Bật lại bằng `enable`.
- Gỡ: `python3 installer/lyra4d.py uninstall --hosts codex`.

**ChatGPT và ChatGPT Projects**
- Mở Project → **Project settings → Instructions**, dán đoạn trong [`project/PROJECT-INSTRUCTIONS.md`](project/PROJECT-INSTRUCTIONS.md), rồi thêm file [`project/LYRA-PROJECT.md`](project/LYRA-PROJECT.md) vào **Files** của Project.
- Project đã có instructions riêng: chèn dòng "Step 0" lên đầu theo mẫu trong `PROJECT-INSTRUCTIONS.md`, giữ nguyên quy ước nghiệp vụ.
- Skill trong ChatGPT: theo [trợ giúp của OpenAI](https://help.openai.com/en/articles/20001066-skills-in-chatgpt), mức hỗ trợ tuỳ gói và cấu hình workspace. Nếu tài khoản có mục Skills, có thể tải `dist/web-skills/lyra.zip` lên (tạo bằng `python3 tools/build.py --zips`). Cấu hình Codex local **không** tự có mặt trong ChatGPT Project.
- Xác nhận: hỏi "lyra diag". Trên web, kết quả chỉ là tự báo (`basis=self-report`).
- Tắt hoặc gỡ: xoá đoạn instructions và file khỏi Project.

### 2. Claude Code và Claude, bao gồm Claude Projects

**Claude Code (CLI và tab Code trong app desktop)**
- Cài: `python3 installer/lyra4d.py install --hosts claude`.
  - Bộ cài dựng marketplace cục bộ `~/.lyra-4d/claude-marketplace` (tên `lyra-4d-local`).
  - Rồi chạy `claude plugin marketplace add` và `claude plugin install` cho ba plugin: `lyra-4d`, `mattpocock-skills` (27 skill) và `superpowers` (14 skill).
  - Không thấy CLI `claude` thì bộ cài in sẵn các lệnh `/plugin …` để bạn dán vào Claude Code.
- Chỉ muốn Lyra, không cần upstream: trong Claude Code chạy `/plugin marketplace add jackyphan201/lyra-4d` rồi `/plugin install lyra-4d@lyra-4d`.
- Kích hoạt không cần gọi tên: plugin có hook `SessionStart` (nạp lõi một lần mỗi phiên, và lại sau `/clear` hoặc compact) và `UserPromptSubmit` (ghi chú khoảng 50 token mỗi lượt). Nếu phiên bắt đầu trước khi cài, lượt đầu tiên sẽ nạp lõi qua hook prompt.
- Xác nhận đã nạp:
  - `claude plugin list` phải có `lyra-4d@lyra-4d-local`.
  - Trong phiên, `/hooks` liệt kê ba hook của Lyra.
  - Gõ `lyra diag` để nhận dòng chẩn đoán kèm `host-evidence`. `python3 installer/lyra4d.py diag` cho biết số lượt hook đã chạy và skill nào host đã thực sự gọi (qua `PostToolUse:Skill`).
- Kiểm tra skill khả dụng: `claude plugin details mattpocock-skills@lyra-4d-local` (hoặc `superpowers@…`), hoặc `/skills` trong phiên.
- Tắt: `claude plugin disable lyra-4d@lyra-4d-local`. Gỡ: `python3 installer/lyra4d.py uninstall --hosts claude`.
- Đã cài `superpowers` hoặc `mattpocock-skills` từ marketplace chính thức: bộ cài sẽ cảnh báo vì skill sẽ bị nạp hai lần. Tắt bản cũ bằng `claude plugin disable <id>`.

**Claude (claude.ai) và Claude Projects**
- Project: dán đoạn trong `PROJECT-INSTRUCTIONS.md` vào **Project instructions**, rồi thêm `LYRA-PROJECT.md` vào **Project knowledge**.
- Skill trên claude.ai: cần bật Code execution ([trợ giúp Anthropic](https://support.claude.com/en/articles/12512180-using-skills-in-claude)). Vào **Customize → Skills → Upload a skill**, tải `dist/web-skills/lyra.zip`. Skill upstream cũng có ZIP riêng trong `dist/web-skills/<repo>/`. Lưu ý: claude.ai giới hạn mô tả skill ở 200 ký tự, nên 12 skill upstream (liệt kê trong `LIMITS.txt`) có thể bị từ chối. Lyra không sửa file upstream để lách giới hạn này.
- Tài liệu chưa nói rõ skill tải lên có hoạt động bên trong Project hay không. Hãy tự kiểm tra bằng "lyra diag".
- Tắt hoặc gỡ: tắt skill trong Customize → Skills, xoá instructions và file khỏi Project.

### 3. Gemini CLI và giao diện Gemini

**Gemini CLI**
- Cài: `python3 installer/lyra4d.py install --hosts gemini`.
  - Khối Lyra được đặt ở đầu `~/.gemini/GEMINI.md`.
  - Hook `BeforeAgent` (ghi chú mỗi lượt) và `AfterTool` với matcher `activate_skill` (log skill) được ghép vào `~/.gemini/settings.json`.
  - Skill dùng chung `~/.agents/skills` với Codex.
  - Nếu `settings.json` có comment (không phải JSON thuần), bộ cài không sửa file và in hướng dẫn thêm tay.
- Kích hoạt không cần gọi tên: GEMINI.md toàn cục được nạp mỗi phiên. Hook `BeforeAgent` chạy trước mỗi lượt.
- Xác nhận:
  - `/hooks` liệt kê `lyra-intake` và `lyra-skill-log`.
  - `/memory show` hiển thị khối Lyra.
  - Gõ `lyra diag` trong prompt.
  - Gemini hỏi đồng ý mỗi lần `activate_skill`. Đó là bước của host, không phải của Lyra.
- Kiểm tra skill: `gemini skills list` hoặc `/skills list`.
- Tắt: `python3 installer/lyra4d.py disable`, hoặc `/hooks disable lyra-intake`. Gỡ: `python3 installer/lyra4d.py uninstall --hosts gemini`.
- Đã cài extension `superpowers` của Gemini: extension đó nạp `using-superpowers` vào mọi phiên và nhân đôi skill. Tắt bằng `gemini extensions disable superpowers`.

**Gemini app (gemini.google.com)**
- Gems đang được chuyển sang Skills: với tài khoản cá nhân, Gems chỉ còn đọc từ 17/11/2026 ([trợ giúp Google](https://support.google.com/gemini/answer/18560919)). Vì vậy hãy dùng Skills.
- Giải nén `lyra.zip` rồi tải **thư mục** `lyra` lên mục Skills trên web hoặc app Mac. Gemini không nhận file nén cho skill.
- Gemini app không có hook. Skill chỉ kích hoạt khi model thấy prompt khớp mô tả, nên **không bảo đảm Lyra chạy ở mọi lượt**. Muốn Lyra áp dụng cho cả cuộc chat thì đính kèm `LYRA-PROJECT.md` và mở đầu bằng: "Áp dụng Lyra trong file đính kèm cho mọi lượt."

## Skill upstream: nguồn, phạm vi và thứ tự chạy

| | mattpocock/skills | obra/superpowers |
|---|---|---|
| Ghim | `v1.3.2` → `d1478fc…` | `v7.0.2` → `22f0b46…` |
| License | MIT, © 2026 Matt Pocock | MIT, © 2025 Jesse Vincent |
| Trong repo upstream | 38 skill | 15 skill |
| Mặc định hiển thị cho host | 27 skill "promoted" (đúng danh sách trong `plugin.json` của Matt) | 14 skill (trừ `using-superpowers`) |
| Có trong store, bật khi cần | 7 `in-progress` + 4 `misc`, dùng cờ `--matt-extra` | `using-superpowers` và hook `SessionStart`, dùng cờ `--superpowers-bootstrap` (không khuyến nghị) |

**Xung đột thứ tự chạy và cách xử lý.** Superpowers tự khởi động bằng hook `SessionStart` (Claude Code), file `GEMINI.md` của extension (Gemini) và mô tả của skill `using-superpowers`. Skill này yêu cầu gọi skill trước mọi phản hồi, kể cả câu hỏi làm rõ. Điều đó trái với việc Lyra phải chạy trước và chờ xác nhận. Lyra xử lý ở lớp tích hợp, không sửa file upstream:
- Không đăng ký hook và không hiển thị `using-superpowers`. File vẫn nằm nguyên trong store và vẫn được kiểm tra hash.
- Lõi Lyra là instructions của người dùng. Chính `using-superpowers` ghi rằng instructions của người dùng (CLAUDE.md, AGENTS.md, GEMINI.md) được ưu tiên hơn skill.

**Skill bọc của Matt.** `grill-me` và `grill-with-docs` là entry point chỉ dành cho người dùng (`disable-model-invocation: true` và `allow_implicit_invocation: false`). Logic nằm trong `grilling` và `domain-modeling`. Lyra gọi thẳng các skill thành phần để không làm một việc hai lần. `domain-modeling` ghi GLOSSARY.md và ADR, nên Lyra xin xác nhận trước khi gọi.

**Skill user-only khác** (`to-spec`, `to-tickets`, `triage`, `wayfinder`, `implement`…): host không cho model tự gọi. Sau khi bạn duyệt, Lyra mời bạn gõ `/tên` (Claude) hoặc `$tên` (Codex), hoặc đọc SKILL.md và ghi rõ "loaded from file".

Danh mục định tuyến đầy đủ, kèm tác dụng phụ của từng skill: [`skills/lyra/SKILL-MAP.md`](skills/lyra/SKILL-MAP.md), sinh từ [`catalog/catalog.json`](catalog/catalog.json).

## Cập nhật, kiểm tra toàn vẹn, rollback, gỡ

```bash
git pull && python3 installer/lyra4d.py update
```

```bash
python3 installer/lyra4d.py verify
```

```bash
python3 installer/lyra4d.py rollback
```

```bash
python3 installer/lyra4d.py uninstall --purge
```

- `update` áp dụng lại lock hiện tại: giữ cấu hình và hook khác của bạn, không tạo hook trùng, tải lại upstream nếu store bị sửa.
- `verify` so mọi file upstream trong store, trong `~/.agents/skills` và trong cache plugin Claude với hash của lock. Lệch hash thì trả mã thoát 1.
- `rollback` khôi phục các file đã sao lưu của lần install hoặc uninstall gần nhất. Plugin Claude cần chạy lại install hoặc uninstall cho Claude.
- `uninstall --purge` gỡ toàn bộ phần của Lyra, kể cả store.
- Đổi phiên bản upstream (dành cho người bảo trì): `python3 installer/lyra4d.py lock mattpocock=mattpocock/skills@<tag> superpowers=obra/superpowers@<tag>`, rồi `python3 tools/build.py` và chạy test. Bước build dừng lại nếu lock có skill mà `catalog/catalog.json` chưa có.

## Chẩn đoán và đo lường

- `lyra diag` trong prompt: Lyra kết thúc câu trả lời bằng một dòng gồm bước tiếp nhận, mode, skill đã chọn, skill đã gọi và căn cứ (`hook`, `transcript` hoặc `self-report`). Dòng này tách ba sự kiện: Lyra đã nhận lượt, Lyra đã chọn skill, host đã thực sự gọi skill.
- `python3 installer/lyra4d.py diag`: đọc log của hook, gồm số lượt hook chạy, số lần lõi được nạp và skill host đã gọi.
- `python3 installer/lyra4d.py metrics`: đếm số ký tự Lyra chèn thêm theo host và sự kiện.
- Log chỉ chứa thời điểm, host, sự kiện, mã phiên đã băm, số ký tự và tên skill. **Không lưu nội dung prompt.** Tắt bằng `metrics off`.

## Kiểm thử

```bash
cd tests && python3 -m unittest
```

```bash
python3 tests/live/run_live.py --host codex --baseline 1-translate,5b-quick-lookup
```

- `unittest`: kiểm thử offline với upstream giả trong HOME tạm (hook, idempotency, giữ cấu hình người dùng, phát hiện sửa file, rollback, build).
- `run_live.py`: chạy các ca trong [`tests/live/cases.json`](tests/live/cases.json) trên host thật, dùng quota tài khoản của bạn. Đổi `--host claude` để chạy trên Claude Code.

## License

Phần do dự án viết: MIT ([LICENSE](LICENSE)). Repo này không chứa bản sao skill upstream. Nghĩa vụ license khi phân phối lại skill upstream được ghi trong [NOTICE.md](NOTICE.md).
