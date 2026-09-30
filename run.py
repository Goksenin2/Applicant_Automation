"""180DC Screener: score applicants on the monday.com board and write the results back.

Examples:
  python run.py --dry-run --limit 2     # try it on 2 applicants, write nothing to monday
  python run.py --dry-run               # score everyone, results only in output/*.csv
  python run.py                         # score everyone not yet scored and write to monday
  python run.py --item 1234567890       # (re)score one applicant
  python run.py --rescore               # re-score applicants that were already scored
"""

import argparse
import csv
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from screener import cv
from screener.config import ROOT, load_config, monday_token
from screener.monday import MondayClient, column_map, file_asset_ids
from screener.scorer import CRITERIA, Scorer, notes, total


def build_updates(cfg: dict, assessment) -> dict:
    values = {cfg["score_columns"][k]: str(getattr(assessment, k).score) for k in CRITERIA}
    if cfg.get("total_column"):
        values[cfg["total_column"]] = str(total(assessment))
    values[cfg["notes_column"]] = {"text": notes(assessment)}
    label = cfg["status_review_label"] if assessment.needs_human_review else cfg["status_done_label"]
    values[cfg["status_column"]] = {"label": label}
    return values


def load_cv(client: MondayClient, cols: dict, cfg: dict, workdir: Path, item_id: str) -> tuple[dict | None, str]:
    """Returns (content block or None, problem description)."""
    asset_ids = file_asset_ids(cols.get(cfg["cv_column"]))
    if not asset_ids:
        return None, "no CV uploaded"
    asset = client.get_asset(asset_ids[0])  # fetch right before download: the link expires
    ext = "." + (asset.get("file_extension") or Path(asset["name"]).suffix).lstrip(".").lower()
    path = cv.download(asset["public_url"], workdir / f"{item_id}{ext}")
    try:
        return cv.to_content_block(path), ""
    except cv.UnreadableCV as e:
        return None, str(e)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="don't write anything to monday.com")
    parser.add_argument("--limit", type=int, help="only score this many applicants")
    parser.add_argument("--item", help="only score the applicant with this item ID")
    parser.add_argument("--rescore", action="store_true", help="also score applicants already scored")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    board = int(cfg["board_id"])
    client = MondayClient(monday_token())
    scorer = Scorer((ROOT / "rubric.md").read_text(), cfg["score_min"], cfg["score_max"], cfg["model"])
    processed_labels = {cfg["status_done_label"], cfg["status_review_label"]}

    items = client.get_items(board)
    if args.item:
        items = [i for i in items if i["id"] == str(args.item)]
    elif not args.rescore:
        items = [i for i in items if (column_map(i).get(cfg["status_column"]) or {}).get("text") not in processed_labels]
    if args.limit:
        items = items[: args.limit]
    print(f"{len(items)} applicant(s) to score{' (dry run)' if args.dry_run else ''}.")

    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"scores_{datetime.now():%Y%m%d_%H%M%S}.csv"
    fields = ["item_id", "name", *CRITERIA, "total", "needs_human_review", "notes", "error"]
    failures = 0

    # CVs only ever live in this temp folder, which is deleted when the run ends.
    with tempfile.TemporaryDirectory() as tmp, out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for n, item in enumerate(items, 1):
            row = {"item_id": item["id"], "name": item["name"]}
            try:
                cols = column_map(item)
                answers = {q: (cols.get(cid) or {}).get("text") or "" for cid, q in cfg["questions"].items()}
                cv_block, cv_problem = load_cv(client, cols, cfg, Path(tmp), item["id"])
                assessment = scorer.score(item["name"], answers, cv_block)
                if cv_problem and not assessment.needs_human_review:
                    assessment.needs_human_review = True
                    assessment.review_reason = f"CV problem: {cv_problem}"
                row |= {k: getattr(assessment, k).score for k in CRITERIA}
                row |= {"total": total(assessment), "needs_human_review": assessment.needs_human_review,
                        "notes": notes(assessment)}
                if not args.dry_run:
                    client.update_columns(board, item["id"], build_updates(cfg, assessment))
                flag = "  [REVIEW]" if assessment.needs_human_review else ""
                print(f"[{n}/{len(items)}] {item['name']}: total {row['total']}{flag}")
            except Exception as e:  # one bad applicant must not stop the run
                failures += 1
                row["error"] = f"{type(e).__name__}: {e}"
                print(f"[{n}/{len(items)}] {item['name']}: FAILED ({row['error']})", file=sys.stderr)
                if not args.dry_run:
                    try:
                        client.update_columns(board, item["id"], {
                            cfg["status_column"]: {"label": cfg["status_review_label"]},
                            cfg["notes_column"]: {"text": f"Automatic scoring failed, score manually. {row['error']}"},
                        })
                    except Exception:
                        pass
            writer.writerow(row)

    print(f"\nDone. {len(items) - failures} scored, {failures} failed. Results: {out_path}")


if __name__ == "__main__":
    main()
