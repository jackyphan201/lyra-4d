# Weekly priority helper: brief

Status: agreed with the product team on 2026-11-18.

## Users
- Product Owners (3 people) of one internal web product. They plan every Monday.
- Secondary: the delivery lead, who reads the result but does not edit it.

## Goal
Every Monday each PO picks the 5 backlog items to start this week, in under 15 minutes, and can explain the choice.

## Inputs
- Backlog export (CSV) from the issue tracker: id, title, type, estimate (points), due date, requester, linked OKR.

## Decision criteria (agreed)
1. Items with a due date inside 10 days come first.
2. Then weighted score = 0.5 * OKR impact (1-5, set by the PO) + 0.3 * customer requests count (normalized 1-5) + 0.2 * (6 - estimate bucket).
3. At most 2 items above 8 points per week.

## Out of scope
- No automatic changes to the issue tracker. Read-only.
- No mobile app.

## Constraints
- Runs locally; data stays on the PO's laptop.
