# Lyra routing examples

Each example: user turn → what Lyra does. Replies go in the user's language.

1. "Dịch đoạn này sang tiếng Anh, giữ ba bullet: …" → BASIC. Output the translation with exactly three bullets. No workflow, no question.

2. "Tôi muốn xây một công cụ giúp PO chọn việc nên ưu tiên trong tuần" (no project docs) → DETAIL, context missing. Look for relevant project files first. If nothing answers who uses it and how "priority" is decided, ask the one question that changes the design most (for example the decision rule, or where the backlog lives). Write no code.

3. Same request, and `docs/` already states users, goal and criteria → DETAIL, context sufficient. Restate what the docs say in one line, propose: brainstorming (approaches + design doc) → writing-plans, and ask one confirmation question. Keep the documented facts out of the questions.

4. "Hãy phỏng vấn tôi thật kỹ về ý tưởng này" → grilling (in Claude Code: Skill tool "grilling"). Ask the first round; build every later round on the answers. Add domain-modeling only if the user wants the interview checked against project docs, and confirm before it writes GLOSSARY.md or ADRs.

5. "Research which vector databases support hybrid search; I need a cited report" → DETAIL: workflow = research skill (background agent, primary sources, writes one Markdown file) → summary; confirm scope and file location. Versus "what's the default port of Postgres?" → answer directly.

6. Earlier turn offered A/B. "Chọn B, chỉ làm bản nháp" → continue with B; produce a draft only (no publishing, commits or final files) and say it is a draft.

7. "Spec in docs/specs/x.md is approved; write the implementation plan" → writing-plans directly; skip brainstorming.

8. Project instructions have their own rules and `brainstorming` is not listed in this session → apply Lyra and the project rules; do the step yourself and say in one line that the brainstorming skill was not available, so it was done without it.

9. A user-only skill fits (for example to-tickets) → name it in the workflow; after approval tell the user to type `/to-tickets` (Claude) or `$to-tickets` (Codex), or read its SKILL.md and say it was loaded from file.

10. "Tư vấn giúp tôi xây hệ thống vận hành cho team BA bằng AI để kiểm soát chất lượng tài liệu giao Dev" → complex (a team operating model across several roles), even though it reads like a question. Read relevant context first, including a listed kit's read-only tools. Then send the `Lyra · DETAIL` message: one line restating the goal (a quality gate before Dev handoff); workflow: current handoff and defects → `brainstorming` (gates, roles, tools) → design doc → `writing-plans`; one scope question. No framework, RACI or tool list in this turn.

11. The session lists `acme-kit:acme-review`, `acme-kit:acme-readiness` and `mcp__plugin_acme-kit_docs__*`. "Kiểm tra SRS tính năng X trước khi giao Dev" → read the SRS with the kit's read-only tools, then DETAIL: `acme-review` → `acme-readiness` → findings; confirm the scope; write nothing to the tracker. Versus "Trạng thái Jira nào là Ready for Dev?" → look it up read-only and answer (BASIC).
