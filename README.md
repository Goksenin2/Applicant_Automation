# 180DC Screener

AI-assisted initial screening for 180 Degrees Consulting recruitment. It reads each applicant
on the monday.com recruitment board, scores their CV and application answers against the
five screening criteria with Claude, and writes the scores, a total, and a short
justification back to the board.

**It ranks applicants. It does not decide.** A person makes every interview/reject decision,
reviews the borderline zone around the cut-off, and checks LinkedIn manually for those
applicants. LinkedIn is not scraped (that breaks LinkedIn's terms).

## What it does per applicant

1. Reads the item from the board (answers + CV file).
2. Downloads the CV to a temp folder (deleted at the end of the run).
3. Sends CV + answers + `rubric.md` to Claude and gets a 1–5 score and a one-line reason
   for each criterion, plus a "needs human review" flag.
4. Writes the 5 scores, Total (unless it's a formula column), the notes and a status
   (`AI scored` / `Needs human review`) back to monday.
5. Saves everything to `output/scores_<timestamp>.csv` (personal data, don't share or commit).

Applicants whose status is already `AI scored` / `Needs human review` are skipped on
re-runs. If one applicant fails, the run carries on and that applicant gets marked for
manual scoring.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # add MONDAY_API_TOKEN and ANTHROPIC_API_KEY
cp config.example.yaml config.yaml
```

- **monday token:** avatar → Developers → **API token** (left sidebar) → Show → Copy. It acts as you; keep it secret.
- **Anthropic key:** console.anthropic.com → API keys (needs a card; it costs a few pounds per round).
- **Board ID:** the number in the board URL (`.../boards/<id>`).

On the board, add a **Long Text** column (e.g. "AI notes") and a **Status** column
(e.g. "AI status"). Then list the column IDs:

```bash
python list_columns.py <board_id>
```

and fill in `config.yaml`: CV column, question columns, the 5 score columns, Total,
notes and status columns, and the scoring scale.

## Running

```bash
python run.py --dry-run --limit 2   # test on 2 applicants, nothing written to monday
python run.py --dry-run             # everyone, results only in output/*.csv (use this to calibrate)
python run.py                       # for real
python run.py --item <item_id>      # one applicant
python run.py --rescore             # re-score people already scored (e.g. after changing the rubric)
```

## Calibrate before trusting it

1. The team scores about 10 applicants by hand, without seeing the AI scores.
2. `python run.py --dry-run` and compare the CSV with the hand scores.
3. Where they disagree, tighten the wording in `rubric.md` and repeat until scores are
   mostly within 1 point and the ranking roughly matches.

## Data protection

- Tell applicants that applications may be assessed with AI assistance (form/privacy notice).
- Human review before any rejection (UK GDPR Art. 22). Never reject on the score alone.
- CVs are only held in a temp folder during the run. Delete `output/` after the round.
- If a human changes a score (e.g. after checking LinkedIn), note it in the AI notes column.

## Tests

```bash
python -m pytest -q
```
