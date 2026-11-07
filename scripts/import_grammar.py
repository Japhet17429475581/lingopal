"""Validate and upsert grammar content without deleting learning progress."""
import ast
import csv
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database as db

DATA = Path(__file__).resolve().parent.parent / "data"


def parse(raw):
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = ast.literal_eval(raw)
    if not isinstance(value, dict):
        raise ValueError("Question payload must be an object")
    return value


def import_grammar():
    db.init_db()
    tables = [("grammar_blocks.csv", db.GrammarBlock), ("grammar_lessons.csv", db.GrammarLesson),
              ("grammar_questions.csv", db.GrammarQuestion)]
    with db.get_db() as session:
        for filename, model in tables:
            with (DATA / filename).open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                for key in ("order_num", "pass_percent", "exp_reward"):
                    if key in row:
                        row[key] = int(row[key])
                if "payload" in row:
                    payload = parse(row["payload"])
                    kind = row["question_type"]
                    if kind not in {"choice", "boolean", "constructor"}:
                        raise ValueError(f"Unsupported question type: {kind}")
                    if kind == "boolean":
                        if isinstance(payload.get("correct"), str):
                            payload["correct"] = payload["correct"].lower() == "true"
                        if type(payload.get("correct")) is not bool:
                            raise ValueError(f"Invalid boolean answer: {row['id']}")
                    if kind == "choice" and payload.get("correct") not in payload.get("options", []):
                        raise ValueError(f"Answer missing from options: {row['id']}")
                    if kind == "constructor" and sorted(payload.get("words", [])) != sorted(payload.get("correct_order", [])):
                        raise ValueError(f"Invalid word bank: {row['id']}")
                    row["payload"] = json.dumps(payload, ensure_ascii=False)
                current = session.get(model, row["id"])
                if current is None:
                    session.add(model(**row))
                else:
                    for key, value in row.items():
                        setattr(current, key, value)
            session.flush()
        session.commit()
    print("Grammar content synchronized; progress preserved.")


if __name__ == "__main__":
    import_grammar()
