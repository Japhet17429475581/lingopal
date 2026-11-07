"""Idempotent, transactional CSV vocabulary import."""
import csv
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from src import database as db

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def detect_delimiter(filepath):
    with open(filepath, encoding="utf-8-sig") as stream:
        header = stream.readline()
    return ";" if header.count(";") > header.count(",") else ","


def import_file(filepath):
    with open(filepath, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=detect_delimiter(filepath))
        required = {"level", "item_type", "word", "translation"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Missing CSV columns in {Path(filepath).name}")
        rows = list(reader)
    added = skipped = 0
    with db.get_db() as session:
        identities = set(session.execute(select(db.Word.level, db.Word.item_type, db.Word.word)).all())
        for row in rows:
            level, kind = row["level"].strip(), row["item_type"].strip()
            word, translation = row["word"].strip(), row["translation"].strip()
            identity = (level, kind, word)
            if level not in {"A1", "A2", "B1", "B2"} or kind not in {"word", "sentence"} or not word or not translation:
                raise ValueError(f"Invalid vocabulary row in {Path(filepath).name}: {identity}")
            if identity in identities:
                skipped += 1
                continue
            session.add(db.Word(level=level, item_type=kind, word=word, translation=translation,
                                example=(row.get("example") or "").strip() or None))
            identities.add(identity)
            added += 1
        session.commit()
    return added, skipped


def main():
    db.init_db()
    for filename in ["espanol_words_final.csv", "sentences.csv"]:
        added, skipped = import_file(DATA_DIR / filename)
        print(f"{filename}: added {added}, existing {skipped}")


if __name__ == "__main__":
    main()
