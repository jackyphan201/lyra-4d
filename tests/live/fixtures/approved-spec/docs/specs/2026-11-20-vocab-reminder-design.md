# Vocabulary reminder CLI: design

Status: **Approved** by the product owner on 2026-11-21. No open questions.

## Intent
Learners forget new words. A small command-line tool reminds them daily with spaced repetition.

## Scope
- `vocab add <word> <meaning>` stores a card in `~/.vocab/cards.json`.
- `vocab review` shows due cards; the learner answers y/n; intervals follow SM-2 (1, 3, 7, 14, 30 days).
- `vocab stats` prints counts of due, learned, and total cards.

## Tech
- Python 3.11, standard library only, `argparse`, tests with `pytest`.
- Package layout: `vocab/` with `cli.py`, `store.py`, `scheduler.py`.

## Non-goals
- No GUI, no sync, no audio.

## Acceptance
- Unit tests for scheduler intervals and store round-trips; `vocab review` handles an empty deck.
