# Lyra 4-D cho ChatGPT Projects, Claude Projects và Gemini

Có hai phần, dùng cùng nhau:

1. **File đính kèm:** [`LYRA-PROJECT.md`](LYRA-PROJECT.md). Thêm vào Files của ChatGPT Project, Project knowledge của Claude Project, hoặc đính kèm trong cuộc chat Gemini. File gồm lõi Lyra, ghi chú cho môi trường không có hook và phần tối ưu prompt.
2. **Đoạn dán vào Project instructions:** khối bên dưới. Đoạn này ngắn để không chiếm chỗ của instructions nghiệp vụ.

## Đoạn dán (project chưa có instructions)

```text
Lyra 4-D intake: before handling any request in this Project, apply the Lyra method in the attached file LYRA-PROJECT.md silently, every turn.
- Clear and simple: deliver the result directly.
- Ambiguous (different readings, different outputs): ask the single most useful question.
- Complex: read the Project files first, then show "I understand you want / Proposed workflow / Please confirm" and wait.
- Use a skill or take actions beyond reading and answering only after I confirm. A skill counts only if this chat shows it; say plainly which ones were actually used.
- Keep my earlier decisions ("choose B", "draft only") across turns. Reply in my language. Write an optimized prompt only when I ask for a prompt.
```

## Project đã có instructions riêng

Giữ nguyên toàn bộ quy ước nghiệp vụ. Chỉ thêm Lyra vào **đầu quy trình xử lý**, theo mẫu:

```text
Step 0, every request: Lyra 4-D intake per the attached LYRA-PROJECT.md (decide: answer now, one question, or a workflow to confirm).
Then: <the Project's existing instructions, unchanged>.
If Lyra and the rules above conflict on content, format, terms or templates, the Project rules win; Lyra only decides how to handle the request.
```

Lưu ý khi ghép:
- Đặt "Step 0" lên trên cùng. Model đọc từ đầu, nên phần nằm trên cùng có tác dụng mạnh nhất.
- Không chép lại lõi Lyra vào instructions. Lõi đã có trong file đính kèm, chép lại chỉ tốn chỗ và dễ lệch phiên bản.
- Nếu project có quy trình riêng (ví dụ "luôn hỏi mã phiếu trước"), giữ quy trình đó. Lyra chỉ bỏ những câu hỏi mà file của project đã trả lời.

## Giới hạn cần biết

- Môi trường web **không có hook**. Việc Lyra chạy đầu tiên dựa vào việc model tuân theo Project instructions. Mức tuân thủ phụ thuộc model, không có hook nào bảo đảm.
- Không gọi được skill local của Claude Code, Codex hay Gemini CLI. Chỉ dùng được skill mà nền tảng web cho phép tải lên và đang bật (xem README, phần từng nền tảng).
- Lệnh "lyra diag" trên web chỉ là tự báo (`basis=self-report`), không có log host để đối chiếu.
