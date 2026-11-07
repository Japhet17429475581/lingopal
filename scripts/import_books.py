"""
scripts/import_books.py — загружает книги для LinguaPlay из CSV.
 
Ожидаемый файл: data/books.csv
Колонки: level,title,author,content
 
Дедуп по (level, title) — как и в остальных импортёрах проекта.
 
Запуск: python -m scripts.import_books
"""
import csv
import sys
from pathlib import Path
 
sys.path.insert(0, str(Path(__file__).parent.parent))
 
from src import database as db
 
DATA_DIR = Path(__file__).parent.parent / "data"
BOOKS_FILE = DATA_DIR / "books.csv"
 
 
def import_books():
    db.init_db()
 
    if not BOOKS_FILE.exists():
        print(f"❌ Не найден файл: {BOOKS_FILE}")
        return
 
    added, skipped = 0, 0
    with open(BOOKS_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {"level", "title", "content"} - set(reader.fieldnames or [])
        if missing:
            print(f"❌ books.csv: отсутствуют колонки {missing}")
            return
 
        for row in reader:
            level = row["level"].strip()
            title = row["title"].strip()
            author = (row.get("author") or "").strip() or None
            content = row["content"].strip()
 
            if not level or not title or not content:
                skipped += 1
                continue
 
            if db.upsert_book(level, title, author, content):
                added += 1
            else:
                skipped += 1
 
    print(f"Книг добавлено: {added}, пропущено (дубли/пустые): {skipped}")
 
 
if __name__ == "__main__":
    import_books()
