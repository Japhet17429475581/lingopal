"""SQLAlchemy persistence for LingoPal. Schema upgrades preserve user data."""
import json
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
 
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean, Float,
    DateTime, ForeignKey, UniqueConstraint, func, select, inspect, update, event, delete, BigInteger,
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship
 
from src.config import DATABASE_URL
 
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _sqlite_settings(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
 
 
def _now() -> datetime:
    return datetime.now(timezone.utc)
 
 
# ============================================
# МОДЕЛИ
# ============================================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    registered_at = Column(DateTime, default=_now)
    level = Column(Integer, nullable=False, default=1)
    exp = Column(Integer, nullable=False, default=0)          # прогресс ВНУТРИ текущего уровня
    streak_count = Column(Integer, nullable=False, default=0)
    last_activity_date = Column(String(10), nullable=True)     # 'YYYY-MM-DD', для расчёта стрика
    first_name = Column(String(128), nullable=True)             # для персонализации уведомлений
    grammar_level = Column(String(2), nullable=True)             # A1/A2/B1/B2/C1
    is_public = Column(Boolean, nullable=False, default=True)    # видимость профиля (для будущего поиска друзей)
    packs_completed = Column(Integer, nullable=False, default=0)  # счётчик для ачивки "Марафонец"
 
 
class Word(Base):
    __tablename__ = "words"
    id = Column(Integer, primary_key=True)
    level = Column(String(2), nullable=False, index=True)
    item_type = Column(String(8), nullable=False, default="word")
    word = Column(String(512), nullable=False)
    translation = Column(String(512), nullable=False)
    example = Column(Text, nullable=True)
 
    __table_args__ = (
        UniqueConstraint("level", "item_type", "word", name="uq_word_identity"),
    )
 
 
class UserWord(Base):
    """Словарь пользователя. Удаления больше нет — только добавление
    (свайп 'Знаю') и чтение (для повторения и списка словаря).
 
    box_number/next_review_at — интервальное повторение по Лейтнеру:
    box 1→5, интервалы 1/3/7/14/30 дней. box=5 считается закреплённым
    навсегда (дальше не переспрашиваем)."""
    __tablename__ = "user_words"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    word_id = Column(Integer, ForeignKey("words.id"), nullable=False)
    added_at = Column(DateTime, default=_now)
    box_number = Column(Integer, nullable=False, default=1)
    next_review_at = Column(DateTime, nullable=True)
 
    word = relationship("Word")
 
    __table_args__ = (
        UniqueConstraint("telegram_id", "word_id", name="uq_user_word"),
    )
 
 
class UserPack(Base):
    """
    Пак — цикл невыученных слов.
    word_ids       — исходный полный набор ("было N"), не меняется после создания
    unlearned_ids  — текущее подмножество ещё не выученных слов
    session_queue  — порядок карточек ТЕКУЩЕГО прохода (пересоздаётся на 'Доучить слова')
    session_index  — позиция внутри session_queue
    """
    __tablename__ = "user_packs"
    id = Column(Integer, primary_key=True)
    pack_key = Column(String(32), nullable=False, index=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    level = Column(String(6), nullable=False)
    item_type = Column(String(8), nullable=False, default="word")
    is_repeat = Column(Boolean, nullable=False, default=False)
 
    word_ids = Column(Text, nullable=False)
    unlearned_ids = Column(Text, nullable=False)
    session_queue = Column(Text, nullable=False)
    session_index = Column(Integer, nullable=False, default=0)
 
    created_at = Column(DateTime, default=_now)
 
    __table_args__ = (
        UniqueConstraint("telegram_id", "pack_key", name="uq_user_pack_key"),
    )
 
 
class DailyQuest(Base):
    """Набор из 3-4 заданий на день. Пересоздаётся автоматически при
    первом обращении в новый день (см. get_or_create_today_quests)."""
    __tablename__ = "daily_quests"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    quest_date = Column(String(10), nullable=False)  # 'YYYY-MM-DD'
    quests = Column(Text, nullable=False)         # JSON: список выбранных на сегодня заданий
    progress = Column(Text, nullable=False, default="{}")        # JSON: {metric: count}
    completed_keys = Column(Text, nullable=False, default="[]")  # JSON: список уже награждённых quest_key
 
    __table_args__ = (
        UniqueConstraint("telegram_id", "quest_date", name="uq_daily_quest_date"),
    )
 
 
class GrammarBlock(Base):
    __tablename__ = "grammar_blocks"
    id = Column(String(32), primary_key=True)
    level = Column(String(2), nullable=False, index=True)
    order_num = Column(Integer, nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False, default="")
    pass_percent = Column(Integer, nullable=False, default=80)
    exp_reward = Column(Integer, nullable=False, default=30)

class GrammarLesson(Base):
    __tablename__ = "grammar_lessons"
    id = Column(String(48), primary_key=True)
    block_id = Column(String(32), ForeignKey("grammar_blocks.id"), nullable=False, index=True)
    order_num = Column(Integer, nullable=False)
    title = Column(String(256), nullable=False)
    theory = Column(Text, nullable=False)

class GrammarQuestion(Base):
    __tablename__ = "grammar_block_questions"
    id = Column(String(64), primary_key=True)
    block_id = Column(String(32), ForeignKey("grammar_blocks.id"), nullable=False, index=True)
    question_type = Column(String(16), nullable=False)
    payload = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)

class UserGrammarProgress(Base):
    __tablename__ = "user_grammar_block_progress"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    block_id = Column(String(32), ForeignKey("grammar_blocks.id"), nullable=False)
    is_completed = Column(Boolean, nullable=False, default=False)
    best_score = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    completed_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("telegram_id", "block_id", name="uq_user_grammar_block"),)


class LearningAttempt(Base):
    """Server-owned questions, answers and an idempotent completion receipt."""
    __tablename__ = "learning_attempts"
    id = Column(String(32), primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    block_id = Column(String(32), nullable=True)
    questions = Column(Text, nullable=False)
    answers = Column(Text, nullable=False, default="[]")
    result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)


class Achievement(Base):
    """Статические определения ачивок — засеиваются в init_db() (upsert
    по key, идемпотентно). Не через CSV: список маленький и меняется редко,
    хранить его в БД, а не в коде, смысла не даёт для этого масштаба."""
    __tablename__ = "achievements"
    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)
    title = Column(String(256), nullable=False)
    icon = Column(String(8), nullable=False)
    exp_reward = Column(Integer, nullable=False, default=20)
 
 
class UserAchievement(Base):
    __tablename__ = "user_achievements"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    achievement_key = Column(String(64), nullable=False)
    unlocked_at = Column(DateTime, default=_now)
 
    __table_args__ = (
        UniqueConstraint("telegram_id", "achievement_key", name="uq_user_achievement"),
    )
 
 
class Book(Base):
    """LinguaPlay: интерактивные книги для чтения с кликабельными словами."""
    __tablename__ = "books"
    id = Column(Integer, primary_key=True)
    level = Column(String(2), nullable=False, index=True)
    title = Column(String(256), nullable=False)
    author = Column(String(256), nullable=True)
    content = Column(Text, nullable=False)  # весь текст книги — токенизация на слова делается на фронте
 
 
class UserBookProgress(Base):
    __tablename__ = "user_book_progress"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    progress_ratio = Column(Float, nullable=False, default=0.0)  # 0.0-1.0, позиция скролла
    is_completed = Column(Boolean, nullable=False, default=False)
    last_read_at = Column(DateTime, default=_now)
 
    __table_args__ = (
        UniqueConstraint("telegram_id", "book_id", name="uq_user_book_progress"),
    )
 
 
def _migrate_user_columns() -> None:
    """users уже содержит реальные данные пользователей — в отличие от
    user_packs, эту таблицу не сносим, а аккуратно донастраиваем."""
    with engine.connect() as conn:
        existing = {column["name"] for column in inspect(conn).get_columns("users")}
        migrations = {
            "level": "INTEGER NOT NULL DEFAULT 1",
            "exp": "INTEGER NOT NULL DEFAULT 0",
            "streak_count": "INTEGER NOT NULL DEFAULT 0",
            "last_activity_date": "VARCHAR(10)",
            "first_name": "VARCHAR(128)",
            "grammar_level": "VARCHAR(2)",
            "is_public": "BOOLEAN NOT NULL DEFAULT 1",
            "packs_completed": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in migrations.items():
            if column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {column} {definition}")
        conn.commit()
 
 
def _migrate_user_words_columns() -> None:
    """Добавляет поля Лейтнера в уже существующую таблицу user_words.
    Слова, добавленные ДО этой миграции, получают next_review_at = сейчас
    (сразу попадают в очередь повторения) — иначе они бы никогда не
    предлагались к повторению, т.к. next_review_at был бы NULL навсегда."""
    with engine.connect() as conn:
        existing = {column["name"] for column in inspect(conn).get_columns("user_words")}
        if "box_number" not in existing:
            conn.exec_driver_sql("ALTER TABLE user_words ADD COLUMN box_number INTEGER NOT NULL DEFAULT 1")
        if "next_review_at" not in existing:
            conn.exec_driver_sql("ALTER TABLE user_words ADD COLUMN next_review_at DATETIME")
            conn.exec_driver_sql(
                "UPDATE user_words SET next_review_at = CURRENT_TIMESTAMP WHERE next_review_at IS NULL"
            )
        conn.commit()
 
 
def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_user_columns()
    _migrate_user_words_columns()
    _seed_achievements()
 
 
def get_db() -> Session:
    return SessionLocal()
 
 
# ============================================
# ПОЛЬЗОВАТЕЛИ
# ============================================
def create_user(telegram_id: int) -> User:
    with get_db() as db:
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if user:
            return user
        user = User(telegram_id=telegram_id)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
 
 
def register_user(telegram_id: int) -> dict:
    """Обёртка над create_user для /api/register — возвращает is_new,
    чтобы фронтенд показал онбординг ровно один раз (в момент самой
    первой регистрации, не при каждом открытии Mini App)."""
    with get_db() as db:
        existing = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        is_new = existing is None
    user = create_user(telegram_id)
    return {"telegram_id": user.telegram_id, "is_new": is_new}
 
 
def set_grammar_level(telegram_id: int, level: str) -> None:
    with get_db() as db:
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if not user:
            raise ValueError("Пользователь не найден")
        user.grammar_level = level
        db.commit()
 
 
# ============================================
# ИМПОРТ СЛОВ
# ============================================
def upsert_word(level: str, item_type: str, word: str, translation: str, example: Optional[str]) -> bool:
    with get_db() as db:
        existing = db.execute(
            select(Word).where(Word.level == level, Word.item_type == item_type, Word.word == word)
        ).scalar_one_or_none()
        if existing:
            return False
        db.add(Word(level=level, item_type=item_type, word=word, translation=translation, example=example))
        db.commit()
        return True
 
 
# ============================================
# ПАКИ — ЦИКЛ НЕВЫУЧЕННЫХ СЛОВ
# ============================================
MIN_PACK_SIZE = 5
MAX_PACK_SIZE = 20
 
 
def _words_by_id(db: Session, ids: list) -> dict:
    if not ids:
        return {}
    rows = db.execute(select(Word).where(Word.id.in_(ids))).scalars().all()
    return {w.id: w for w in rows}
 
 
def _pack_to_dict(pack: UserPack, db: Session) -> dict:
    word_ids = json.loads(pack.word_ids)
    unlearned_ids = json.loads(pack.unlearned_ids)
    session_queue = json.loads(pack.session_queue)
 
    words_by_id = _words_by_id(db, session_queue)
    session_cards = [
        {"id": w.id, "es": w.word, "ru": w.translation, "example": w.example}
        for wid in session_queue if (w := words_by_id.get(wid))
    ]
 
    return {
        "pack_key": pack.pack_key,
        "level": pack.level,
        "item_type": pack.item_type,
        "is_repeat": pack.is_repeat,
        "total": len(word_ids),                 # "Было N"
        "unlearned_count": len(unlearned_ids),   # "осталось M невыученных"
        "session_index": pack.session_index,
        "session_total": len(session_queue),
        "session_cards": session_cards,
        "fully_learned": len(unlearned_ids) == 0,
    }
 
 
def _find_pack(db: Session, telegram_id: int, pack_key: str) -> Optional[UserPack]:
    return db.execute(
        select(UserPack).where(UserPack.telegram_id == telegram_id, UserPack.pack_key == pack_key)
    ).scalar_one_or_none()
 
 
def start_pack(telegram_id: int, level: str, item_type: str, size: int) -> dict:
    size = max(MIN_PACK_SIZE, min(MAX_PACK_SIZE, size))
 
    with get_db() as db:
        # Резюмируем существующий незавершённый (не полностью выученный) пак
        existing = db.execute(
            select(UserPack).where(
                UserPack.telegram_id == telegram_id, UserPack.level == level,
                UserPack.item_type == item_type, UserPack.is_repeat.is_(False),
            ).order_by(UserPack.created_at.desc())
        ).scalars().first()
        if existing:
            return _pack_to_dict(existing, db)
 
        learned_ids = set(
            db.execute(
                select(UserWord.word_id).join(Word).where(
                    UserWord.telegram_id == telegram_id, Word.level == level, Word.item_type == item_type
                )
            ).scalars().all()
        )
        busy_ids = set()
        for p in db.execute(
            select(UserPack).where(
                UserPack.telegram_id == telegram_id, UserPack.level == level, UserPack.item_type == item_type,
            )
        ).scalars().all():
            busy_ids.update(json.loads(p.word_ids))
 
        available = db.execute(
            select(Word.id).where(Word.level == level, Word.item_type == item_type)
        ).scalars().all()
        candidates = [wid for wid in available if wid not in learned_ids and wid not in busy_ids]
 
        if not candidates:
            return {"error": "no_words_available"}
 
        random.shuffle(candidates)
        chosen = candidates[:size]  # если свежих слов меньше size — берём сколько есть
 
        pack_key = f"{level}_{item_type}_{uuid.uuid4().hex[:12]}"
 
        session_queue = chosen.copy()
        random.shuffle(session_queue)
 
        pack = UserPack(
            pack_key=pack_key, telegram_id=telegram_id, level=level, item_type=item_type, is_repeat=False,
            word_ids=json.dumps(chosen), unlearned_ids=json.dumps(chosen),
            session_queue=json.dumps(session_queue), session_index=0,
        )
        db.add(pack)
        db.commit()
        db.refresh(pack)
        return _pack_to_dict(pack, db)
 
 
def swipe_pack(telegram_id: int, pack_key: str, word_id: int, knows: bool) -> Optional[dict]:
    newly_learned = False
 
    with get_db() as db:
        pack = _find_pack(db, telegram_id, pack_key)
        if not pack:
            return None
        queue = json.loads(pack.session_queue)
        if pack.session_index >= len(queue) or queue[pack.session_index] != word_id:
            raise ValueError("Карточка уже обработана или не является текущей")
        previous_index = pack.session_index
        changed = db.execute(update(UserPack).where(UserPack.id == pack.id,
            UserPack.session_index == previous_index).values(session_index=previous_index + 1),
            execution_options={"synchronize_session": False}).rowcount
        if not changed:
            raise ValueError("Карточка уже обрабатывается")
 
        unlearned = json.loads(pack.unlearned_ids)
        if knows and word_id in unlearned:
            unlearned.remove(word_id)
            exists = db.execute(
                select(UserWord).where(UserWord.telegram_id == telegram_id, UserWord.word_id == word_id)
            ).scalar_one_or_none()
            if not exists:
                db.add(UserWord(
                    telegram_id=telegram_id, word_id=word_id,
                    box_number=1, next_review_at=_now() + timedelta(days=1),
                ))
                newly_learned = True  # EXP начисляем только за реально новое слово, не за повтор
        # knows=False — слово остаётся в unlearned как есть, дополнительных действий не требуется
 
        pack.unlearned_ids = json.dumps(unlearned)
        pack.session_index = previous_index + 1
        exp_result = streak_result = None
        if newly_learned:
            from src.learning import _award
            exp_result, streak_result = _award(db, telegram_id, 5)
        db.commit()
        db.refresh(pack)
        result = _pack_to_dict(pack, db)
 
    if newly_learned:
        result["exp_result"] = exp_result
        result["streak_result"] = streak_result
 
    quest_events = []
    quest_events += record_quest_progress(telegram_id, "cards_swiped", 1)
    if newly_learned:
        quest_events += record_quest_progress(telegram_id, "words_learned", 1)
    if result["is_repeat"]:
        quest_events += record_quest_progress(telegram_id, "review_swipes", 1)
    if quest_events:
        result["quest_events"] = quest_events
 
    if newly_learned:
        result["unlocked_achievements"] = check_achievements(telegram_id)
 
    return result
 
 
def continue_pack(telegram_id: int, pack_key: str) -> Optional[dict]:
    """'Доучить слова' — новый проход только по всё ещё невыученным."""
    with get_db() as db:
        pack = _find_pack(db, telegram_id, pack_key)
        if not pack:
            return None
 
        unlearned = json.loads(pack.unlearned_ids)
        if not unlearned:
            return _pack_to_dict(pack, db)  # нечего доучивать — уже всё выучено
 
        new_queue = unlearned.copy()
        random.shuffle(new_queue)
        pack.session_queue = json.dumps(new_queue)
        pack.session_index = 0
        db.commit()
        db.refresh(pack)
        return _pack_to_dict(pack, db)
 
 
def delete_pack(telegram_id: int, pack_key: str) -> bool:
    """Полное удаление строки БЕЗ начисления EXP — для явного удаления
    незавершённого пака или пака повторения. Для 'Закончить пак' после
    полного изучения используй finish_pack()."""
    with get_db() as db:
        pack = _find_pack(db, telegram_id, pack_key)
        if not pack:
            return False
        db.delete(pack)
        db.commit()
        return True
 
 
def finish_pack(telegram_id: int, pack_key: str) -> Optional[dict]:
    """Вызывается кнопкой 'Закончить пак' — начисляет +20 EXP и стрик
    ТОЛЬКО если пак реально пройден полностью (unlearned_ids пуст),
    затем удаляет пак. Возвращает None, если пак не найден, или
    {"error": "not_fully_learned"}, если попытались завершить пак
    с ещё не выученными словами (защита от некорректного вызова с фронта)."""
    with get_db() as db:
        pack = _find_pack(db, telegram_id, pack_key)
        if not pack:
            return None
        if json.loads(pack.unlearned_ids):
            return {"error": "not_fully_learned"}
 
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if user and not pack.is_repeat:
            user.packs_completed += 1  # для ачивки "Марафонец"
        reward = 0 if pack.is_repeat else 20
        removed = db.execute(delete(UserPack).where(UserPack.id == pack.id),
                             execution_options={"synchronize_session": False}).rowcount
        if not removed:
            return None
        from src.learning import _award
        exp_result, streak_result = _award(db, telegram_id, reward)
        db.commit()
    unlocked = check_achievements(telegram_id)
    return {"success": True, "exp_result": exp_result, "streak_result": streak_result, "unlocked_achievements": unlocked}
 
 
def list_packs(telegram_id: int, level: Optional[str] = None) -> list:
    with get_db() as db:
        query = select(UserPack).where(UserPack.telegram_id == telegram_id, UserPack.is_repeat.is_(False))
        if level:
            query = query.where(UserPack.level == level)
        packs = db.execute(query.order_by(UserPack.created_at)).scalars().all()
        return [_pack_to_dict(p, db) for p in packs]
 
 
# ============================================
# ПАКИ ПОВТОРЕНИЯ (создаются из словаря, живут в словаре)
# ============================================
def create_review_pack(telegram_id: int, word_ids: list) -> dict:
    with get_db() as db:
        # Оставляем только слова, реально принадлежащие словарю этого пользователя
        owned = set(
            db.execute(
                select(UserWord.word_id).where(UserWord.telegram_id == telegram_id, UserWord.word_id.in_(word_ids))
            ).scalars().all()
        )
        chosen = list(dict.fromkeys(wid for wid in word_ids if wid in owned))
        if not chosen:
            return {"error": "empty_selection"}
 
        pack_key = f"REVIEW_{uuid.uuid4().hex[:16]}"
 
        session_queue = chosen.copy()
        random.shuffle(session_queue)
 
        pack = UserPack(
            pack_key=pack_key, telegram_id=telegram_id, level="MIX", item_type="mixed", is_repeat=True,
            word_ids=json.dumps(chosen), unlearned_ids=json.dumps(chosen),
            session_queue=json.dumps(session_queue), session_index=0,
        )
        db.add(pack)
        db.commit()
        db.refresh(pack)
        return _pack_to_dict(pack, db)
 
 
def list_review_packs(telegram_id: int) -> list:
    with get_db() as db:
        packs = db.execute(
            select(UserPack).where(UserPack.telegram_id == telegram_id, UserPack.is_repeat.is_(True))
            .order_by(UserPack.created_at.desc())
        ).scalars().all()
        return [_pack_to_dict(p, db) for p in packs]
 
 
# ============================================
# СЛОВАРЬ (без удаления — см. ТЗ)
# ============================================
def add_word_to_dictionary(telegram_id: int, word_id: int) -> bool:
    """Ручное добавление слова в словарь — в обход обычного пути через
    свайп в паке. Нужно для LinguaPlay (кнопка 'Добавить в словарь' при
    клике на слово в тексте книги). Возвращает False, если слово уже
    было в словаре (не ошибка, просто no-op)."""
    with get_db() as db:
        word = db.execute(select(Word).where(Word.id == word_id)).scalar_one_or_none()
        if not word:
            raise ValueError("Слово не найдено")
        exists = db.execute(
            select(UserWord).where(UserWord.telegram_id == telegram_id, UserWord.word_id == word_id)
        ).scalar_one_or_none()
        if exists:
            return False
        db.add(UserWord(
            telegram_id=telegram_id, word_id=word_id,
            box_number=1, next_review_at=_now() + timedelta(days=1),
        ))
        db.commit()
        return True
 
 
def get_dictionary(telegram_id: int, level: Optional[str] = None,
                    letter: Optional[str] = None, search: Optional[str] = None) -> list:
    with get_db() as db:
        query = select(UserWord, Word).join(Word).where(UserWord.telegram_id == telegram_id)
        if level:
            query = query.where(Word.level == level)
        if letter:
            query = query.where(func.lower(Word.word).like(f"{letter.lower()}%"))
        if search:
            like = f"%{search.lower()}%"
            query = query.where(func.lower(Word.word).like(like) | func.lower(Word.translation).like(like))
 
        rows = db.execute(query.order_by(Word.word)).all()
        return [
            {
                "word_id": w.id, "level": w.level, "item_type": w.item_type,
                "es": w.word, "ru": w.translation, "added_at": uw.added_at.isoformat(),
            }
            for uw, w in rows
        ]
 
 
def get_word_by_id(word_id: int) -> Optional[dict]:
    with get_db() as db:
        w = db.execute(select(Word).where(Word.id == word_id)).scalar_one_or_none()
        if not w:
            return None
        return {"id": w.id, "es": w.word, "ru": w.translation, "example": w.example}
 
 
# ============================================
# ПРОГРЕСС ПО УРОВНЯМ
# ============================================
def get_level_progress(telegram_id: int, level: str, item_type: str) -> dict:
    with get_db() as db:
        total = db.execute(
            select(func.count()).select_from(Word).where(Word.level == level, Word.item_type == item_type)
        ).scalar()
        learned = db.execute(
            select(func.count()).select_from(UserWord).join(Word).where(
                UserWord.telegram_id == telegram_id, Word.level == level, Word.item_type == item_type
            )
        ).scalar()
        return {"level": level, "learned": learned, "total": total}
 
 
# ============================================
# СТРИК: ОГНЕННЫЕ УРОВНИ
# ============================================
STREAK_TIERS = [
    {"key": "huevo", "emoji": "🥚", "label": "Huevo", "min_days": 0, "max_days": 7, "bonus_pct": 0},
    {"key": "lagarto", "emoji": "🦎", "label": "Lagarto", "min_days": 8, "max_days": 21, "bonus_pct": 5},
    {"key": "toro", "emoji": "🐂", "label": "Toro", "min_days": 22, "max_days": 50, "bonus_pct": 10},
    {"key": "dragon", "emoji": "🐉", "label": "Dragón", "min_days": 51, "max_days": 100, "bonus_pct": 20},
    {"key": "el_cid", "emoji": "👑", "label": "El Cid", "min_days": 101, "max_days": None, "bonus_pct": 30},
]
 
 
def get_streak_tier(streak_count: int) -> dict:
    for tier in STREAK_TIERS:
        if streak_count >= tier["min_days"] and (tier["max_days"] is None or streak_count <= tier["max_days"]):
            return tier
    return STREAK_TIERS[-1]
 
 
def update_streak(telegram_id: int) -> dict:
    """
    Вызывается на любое засчитываемое действие (пак, грамматика, повторение,
    сообщение Хосе). Если пользователь пропустил день целиком — стрик
    сбрасывается до 0, затем сразу засчитывается сегодняшний день (=1).
    Повторный вызов в тот же день — no-op (стрик не растёт от количества
    действий за день, только от факта захода в новый день).
    """
    today = _now().date()
    today_str = today.isoformat()
 
    with get_db() as db:
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if not user:
            raise ValueError("Пользователь не найден")
 
        old_tier = get_streak_tier(user.streak_count)["key"]
 
        if user.last_activity_date == today_str:
            pass  # уже засчитано сегодня
        elif user.last_activity_date == (today - timedelta(days=1)).isoformat():
            user.streak_count += 1
        else:
            user.streak_count = 1  # пропуск дня (или первый визит) — начинаем заново с сегодняшнего дня
 
        user.last_activity_date = today_str
        db.commit()
        db.refresh(user)
 
        new_tier = get_streak_tier(user.streak_count)
        return {
            "streak_count": user.streak_count,
            "tier": new_tier,
            "tier_changed": new_tier["key"] != old_tier,  # триггер анимации на фронте
        }
 
 
# ============================================
# EXP И БЕСКОНЕЧНЫЕ УРОВНИ
# ============================================
EXP_PER_LEVEL = 50  # EXP_NEEDED = level * EXP_PER_LEVEL
 
 
def exp_needed_for_level(level: int) -> int:
    return level * EXP_PER_LEVEL
 
 
def award_exp(telegram_id: int, base_amount: int) -> dict:
    """
    Начисляет EXP с учётом бонуса текущего уровня стрика (см. STREAK_TIERS),
    поднимает уровень (может перепрыгнуть сразу несколько уровней разом —
    цикл на случай крупных начислений). Уровень не ограничен.
    """
    with get_db() as db:
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if not user:
            raise ValueError("Пользователь не найден")
 
        tier = get_streak_tier(user.streak_count)
        bonus_amount = round(base_amount * tier["bonus_pct"] / 100)
        total_amount = base_amount + bonus_amount
 
        user.exp += total_amount
        levels_gained = 0
        while user.exp >= exp_needed_for_level(user.level):
            user.exp -= exp_needed_for_level(user.level)
            user.level += 1
            levels_gained += 1
 
        db.commit()
        db.refresh(user)
 
        return {
            "awarded": total_amount,
            "base": base_amount,
            "bonus": bonus_amount,
            "level": user.level,
            "exp": user.exp,
            "exp_needed": exp_needed_for_level(user.level),
            "leveled_up": levels_gained > 0,
            "levels_gained": levels_gained,
        }
 
 
def get_profile(telegram_id: int) -> Optional[dict]:
    with get_db() as db:
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if not user:
            return None
        streak_count = user.streak_count
        if user.last_activity_date not in {_now().date().isoformat(), (_now().date() - timedelta(days=1)).isoformat()}:
            streak_count = 0
        tier = get_streak_tier(streak_count)
        return {
            "level": user.level,
            "exp": user.exp,
            "exp_needed": exp_needed_for_level(user.level),
            "streak_count": streak_count,
            "streak_tier": tier,
            "grammar_level": user.grammar_level,
            "is_active_today": user.last_activity_date == _now().date().isoformat(),
            "is_public": user.is_public,
        }
 
 
# ============================================
# ДЛЯ УВЕДОМЛЕНИЙ (src/notifications.py)
# ============================================
def set_first_name(telegram_id: int, first_name: Optional[str]) -> None:
    if not first_name:
        return
    with get_db() as db:
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if user and user.first_name != first_name:
            user.first_name = first_name
            db.commit()
 
 
def get_users_inactive_today() -> list:
    """Пользователи, у которых last_activity_date не равен сегодняшней
    дате (в т.ч. те, кто вообще ни разу не заходил — last_activity_date IS NULL)."""
    today_str = _now().date().isoformat()
    with get_db() as db:
        users = db.execute(
            select(User).where((User.last_activity_date != today_str) | (User.last_activity_date.is_(None)))
        ).scalars().all()
        return [{"telegram_id": u.telegram_id, "first_name": u.first_name} for u in users]
 
 
def get_all_users() -> list:
    with get_db() as db:
        users = db.execute(select(User)).scalars().all()
        return [{"telegram_id": u.telegram_id, "first_name": u.first_name} for u in users]
 
 
# ============================================
# ЕЖЕДНЕВНЫЕ КВЕСТЫ
# ============================================
QUEST_POOL = {
    "learn_10_words": {"title": "Выучи 10 слов", "metric": "words_learned", "target": 10, "exp": 15},
    "swipe_20_cards": {"title": "Пройди 20 карточек", "metric": "cards_swiped", "target": 20, "exp": 15},
    "ask_jose_3": {"title": "Спроси у Хосе 3 вопроса", "metric": "jose_questions", "target": 3, "exp": 15},
    "review_5_words": {"title": "Повтори 5 слов из словаря", "metric": "review_swipes", "target": 5, "exp": 15},
}
QUESTS_PER_DAY_MIN = 3
QUESTS_PER_DAY_MAX = 4
 
 
def _today_str() -> str:
    return _now().date().isoformat()
 
 
def get_or_create_today_quests(telegram_id: int) -> DailyQuest:
    """Возвращает ORM-объект DailyQuest на сегодня — создаёт новый набор
    (случайные 3-4 задания из QUEST_POOL), если его ещё нет."""
    today = _today_str()
    with get_db() as db:
        existing = db.execute(
            select(DailyQuest).where(DailyQuest.telegram_id == telegram_id, DailyQuest.quest_date == today)
        ).scalar_one_or_none()
        if existing:
            return existing
 
        count = random.randint(QUESTS_PER_DAY_MIN, QUESTS_PER_DAY_MAX)
        chosen_keys = random.sample(list(QUEST_POOL.keys()), min(count, len(QUEST_POOL)))
 
        quest_row = DailyQuest(
            telegram_id=telegram_id, quest_date=today,
            quests=json.dumps(chosen_keys), progress=json.dumps({}), completed_keys=json.dumps([]),
        )
        db.add(quest_row)
        db.commit()
        db.refresh(quest_row)
        return quest_row
 
 
def get_quests_view(telegram_id: int) -> dict:
    row = get_or_create_today_quests(telegram_id)
    quest_keys = json.loads(row.quests)
    progress = json.loads(row.progress)
    completed = set(json.loads(row.completed_keys))
 
    items = []
    for key in quest_keys:
        definition = QUEST_POOL[key]
        current = progress.get(definition["metric"], 0)
        items.append({
            "key": key,
            "title": definition["title"],
            "target": definition["target"],
            "current": min(current, definition["target"]),
            "exp": definition["exp"],
            "completed": key in completed,
        })
    return {"quest_date": row.quest_date, "quests": items}
 
 
def record_quest_progress(telegram_id: int, metric: str, amount: int = 1) -> list:
    """
    Вызывается из мест, где происходит засчитываемое действие (swipe_pack,
    /api/ask). Продвигает прогресс ТОЛЬКО тех заданий сегодняшнего набора,
    что используют этот metric, начисляет EXP при достижении цели (один раз).
    Возвращает список только что выполненных заданий (для анимации на фронте).
    """
    row = get_or_create_today_quests(telegram_id)
    quest_keys = json.loads(row.quests)
    relevant_keys = [k for k in quest_keys if QUEST_POOL[k]["metric"] == metric]
    if not relevant_keys:
        return []  # сегодня нет задания с этим metric — ничего не делаем
 
    with get_db() as db:
        fresh = db.execute(select(DailyQuest).where(DailyQuest.id == row.id)).scalar_one()
        progress = json.loads(fresh.progress)
        completed = set(json.loads(fresh.completed_keys))
 
        progress[metric] = progress.get(metric, 0) + amount
 
        newly_completed = []
        for key in relevant_keys:
            if key in completed:
                continue
            definition = QUEST_POOL[key]
            if progress[metric] >= definition["target"]:
                completed.add(key)
                newly_completed.append({"key": key, "title": definition["title"], "exp": definition["exp"]})
 
        fresh.progress = json.dumps(progress)
        fresh.completed_keys = json.dumps(list(completed))
        db.commit()
 
    # EXP начисляем отдельными вызовами ПОСЛЕ закрытия сессии выше —
    # тот же приём, что и в swipe_pack/finish_pack, чтобы не пересекаться
    # блокировками SQLite между вложенными сессиями.
    results = []
    for item in newly_completed:
        exp_result = award_exp(telegram_id, item["exp"])
        results.append({**item, "exp_result": exp_result})
    return results
 
 
# ============================================
# ГРАММАТИКА
# ============================================
def get_grammar_blocks(telegram_id: int, level: str) -> list:
    with get_db() as session:
        blocks = session.execute(select(GrammarBlock).where(GrammarBlock.level == level).order_by(GrammarBlock.order_num)).scalars().all()
        progress = {p.block_id: p for p in session.execute(select(UserGrammarProgress).where(UserGrammarProgress.telegram_id == telegram_id)).scalars()}
        current = False
        result = []
        for block in blocks:
            saved = progress.get(block.id)
            completed = bool(saved and saved.is_completed)
            status = "completed" if completed else "locked" if current else "current"
            if not completed:
                current = True
            result.append({"id": block.id, "title": block.title, "description": block.description,
                           "level": block.level, "order_num": block.order_num, "pass_percent": block.pass_percent,
                           "exp_reward": block.exp_reward, "is_completed": completed, "status": status,
                           "best_score": saved.best_score if saved else 0, "attempts": saved.attempts if saved else 0})
        return result


def get_grammar_block_detail(block_id: str):
    with get_db() as db:
        block=db.get(GrammarBlock,block_id)
        if not block:return None
        lessons=db.execute(select(GrammarLesson).where(GrammarLesson.block_id==block_id).order_by(GrammarLesson.order_num)).scalars().all()
        return {"id":block.id,"level":block.level,"title":block.title,"description":block.description,"pass_percent":block.pass_percent,"lessons":[{"id":l.id,"title":l.title,"theory":l.theory,"order_num":l.order_num} for l in lessons]}

def get_grammar_questions(block_id:str):
    with get_db() as db:
        rows=db.execute(select(GrammarQuestion).where(GrammarQuestion.block_id==block_id)).scalars().all()
        return [{"id":q.id,"question_type":q.question_type,"payload":json.loads(q.payload),"explanation":q.explanation} for q in rows]

GRAMMAR_EXP_PER_CORRECT=10

LEXICON_LEVELS = ["A1", "A2", "B1", "B2"]
GRAMMAR_GURU_LEVELS = ["A1", "A2", "B1", "B2"]  # темы грамматики пока есть только для этих уровней (см. ТЗ)
STREAK_KING_THRESHOLD = 30
MARATHONER_THRESHOLD = 100
 
ACHIEVEMENT_DEFINITIONS = (
    [{"key": f"lexicon_{lvl.lower()}", "title": f"Мастер лексики {lvl}", "icon": "🏅", "exp_reward": 30} for lvl in LEXICON_LEVELS]
    + [{"key": f"grammar_guru_{lvl.lower()}", "title": f"Грамматический гуру {lvl}", "icon": "📘", "exp_reward": 30} for lvl in GRAMMAR_GURU_LEVELS]
    + [
        {"key": "streak_king", "title": "Король стрика", "icon": "👑", "exp_reward": 50},
        {"key": "marathoner", "title": "Марафонец", "icon": "🏃", "exp_reward": 50},
    ]
)
 
 
def _seed_achievements() -> None:
    """Идемпотентно: добавляет только отсутствующие ачивки, не трогает
    уже существующие строки (и тем более не трогает user_achievements)."""
    with get_db() as db:
        existing_keys = set(db.execute(select(Achievement.key)).scalars().all())
        for definition in ACHIEVEMENT_DEFINITIONS:
            if definition["key"] not in existing_keys:
                db.add(Achievement(**definition))
        db.commit()
 
 
def _check_single_condition(telegram_id: int, key: str, user: "User") -> bool:
    """Возвращает True, если условие ачивки key выполнено ПРЯМО СЕЙЧАС.
    'movie_critic' и 'social_butterfly' возвращают False всегда —
    подсистемы (видео-плеер, друзья) ещё не реализованы."""
    if key.startswith("lexicon_"):
        level = key.split("_", 1)[1].upper()
        progress = get_level_progress(telegram_id, level, "word")
        return progress["total"] > 0 and progress["learned"] >= progress["total"]
 
    if key.startswith("grammar_guru_"):
        level = key.split("_", 2)[2].upper()
        with get_db() as db:
            total = db.execute(select(func.count()).select_from(GrammarBlock).where(GrammarBlock.level == level)).scalar()
            if total == 0:
                return False
            completed = db.execute(
                select(func.count()).select_from(UserGrammarProgress).join(
                    GrammarBlock, UserGrammarProgress.block_id == GrammarBlock.id
                ).where(
                    UserGrammarProgress.telegram_id == telegram_id,
                    UserGrammarProgress.is_completed.is_(True),
                    GrammarBlock.level == level,
                )
            ).scalar()
            return completed >= total
 
    if key == "streak_king":
        return user.streak_count >= STREAK_KING_THRESHOLD
 
    if key == "marathoner":
        return user.packs_completed >= MARATHONER_THRESHOLD
 
    return False  # movie_critic, social_butterfly — подсистем ещё нет
 
 
def check_achievements(telegram_id: int) -> list:
    """Проверяет ВСЕ ещё не полученные ачивки, разблокирует выполненные,
    начисляет EXP. Вызывается после действий, которые могут их
    завершить (см. finish_pack/complete_grammar_topic/swipe_pack)."""
    with get_db() as db:
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if not user:
            return []
 
        unlocked_keys = set(
            db.execute(
                select(UserAchievement.achievement_key).where(UserAchievement.telegram_id == telegram_id)
            ).scalars().all()
        )
        all_achievements = {a.key: a for a in db.execute(select(Achievement)).scalars().all()}
 
        newly_unlocked = []
        for key, achievement in all_achievements.items():
            if key in unlocked_keys:
                continue
            if _check_single_condition(telegram_id, key, user):
                db.add(UserAchievement(telegram_id=telegram_id, achievement_key=key))
                newly_unlocked.append({"key": key, "title": achievement.title, "icon": achievement.icon, "exp": achievement.exp_reward})
 
        db.commit()
 
    results = []
    for item in newly_unlocked:
        exp_result = award_exp(telegram_id, item["exp"])
        results.append({**item, "exp_result": exp_result})
    return results
 
 
def get_achievements_view(telegram_id: int) -> list:
    """Сначала докатывает проверку (на случай изменений, случившихся вне
    обычного пути — например, после ручной правки БД), затем отдаёт
    полный список с флагом unlocked."""
    check_achievements(telegram_id)
    with get_db() as db:
        all_achievements = db.execute(select(Achievement).where(
            Achievement.key.in_([item["key"] for item in ACHIEVEMENT_DEFINITIONS])
        )).scalars().all()
        unlocked = {
            row[0]: row[1] for row in db.execute(
                select(UserAchievement.achievement_key, UserAchievement.unlocked_at)
                .where(UserAchievement.telegram_id == telegram_id)
            ).all()
        }
        return [
            {
                "key": a.key, "title": a.title, "icon": a.icon, "exp_reward": a.exp_reward,
                "unlocked": a.key in unlocked,
                "unlocked_at": unlocked[a.key].isoformat() if a.key in unlocked else None,
            }
            for a in all_achievements
        ]
 
 
# ============================================
# СТАТИСТИКА ПРОФИЛЯ
# ============================================
def get_profile_stats(telegram_id: int) -> dict:
    with get_db() as db:
        words_learned = db.execute(
            select(func.count()).select_from(UserWord).where(UserWord.telegram_id == telegram_id)
        ).scalar()
        grammar_topics_completed = db.execute(
            select(func.count()).select_from(UserGrammarProgress).where(
                UserGrammarProgress.telegram_id == telegram_id, UserGrammarProgress.is_completed.is_(True)
            )
        ).scalar()
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        packs_completed = user.packs_completed if user else 0
 
        return {
            "words_learned": words_learned,
            "packs_completed": packs_completed,
            "grammar_topics_completed": grammar_topics_completed,
        }
 
 
def set_user_visibility(telegram_id: int, is_public: bool) -> None:
    with get_db() as db:
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if not user:
            raise ValueError("Пользователь не найден")
        user.is_public = is_public
        db.commit()
 
 
# ============================================
# LINGUAPLAY: КНИГИ
# ============================================
def get_books(level: str, telegram_id: int) -> list:
    with get_db() as db:
        books = db.execute(select(Book).where(Book.level == level)).scalars().all()
        progress_by_book = {
            row.book_id: row for row in db.execute(
                select(UserBookProgress).where(UserBookProgress.telegram_id == telegram_id)
            ).scalars().all()
        }
        return [
            {
                "id": b.id, "title": b.title, "author": b.author, "level": b.level,
                "progress_ratio": progress_by_book[b.id].progress_ratio if b.id in progress_by_book else 0.0,
                "is_completed": progress_by_book[b.id].is_completed if b.id in progress_by_book else False,
            }
            for b in books
        ]
 
 
def get_book_detail(book_id: int, telegram_id: int) -> Optional[dict]:
    with get_db() as db:
        book = db.execute(select(Book).where(Book.id == book_id)).scalar_one_or_none()
        if not book:
            return None
        progress = db.execute(
            select(UserBookProgress).where(
                UserBookProgress.telegram_id == telegram_id, UserBookProgress.book_id == book_id
            )
        ).scalar_one_or_none()
        return {
            "id": book.id, "title": book.title, "author": book.author,
            "level": book.level, "content": book.content,
            "progress_ratio": progress.progress_ratio if progress else 0.0,
        }
 
 
def save_book_progress(telegram_id: int, book_id: int, progress_ratio: float) -> dict:
    progress_ratio = max(0.0, min(1.0, progress_ratio))
    is_completed = progress_ratio >= 0.95
 
    with get_db() as db:
        if not db.get(Book, book_id):
            raise ValueError("Книга не найдена")
        row = db.execute(
            select(UserBookProgress).where(
                UserBookProgress.telegram_id == telegram_id, UserBookProgress.book_id == book_id
            )
        ).scalar_one_or_none()
        if not row:
            row = UserBookProgress(telegram_id=telegram_id, book_id=book_id, progress_ratio=0.0, is_completed=False)
            db.add(row)
 
        # Не даём прогрессу "откатываться назад" от случайного скролла вверх —
        # сохраняем максимум из уже достигнутого и нового значения.
        row.progress_ratio = max(row.progress_ratio, progress_ratio)
        row.is_completed = row.is_completed or is_completed
        row.last_read_at = _now()
        db.commit()
        return {"progress_ratio": row.progress_ratio, "is_completed": row.is_completed}
 
 
def upsert_book(level: str, title: str, author: Optional[str], content: str) -> bool:
    """Дедуп по (level, title) — как и в остальных импортёрах проекта."""
    with get_db() as db:
        existing = db.execute(
            select(Book).where(Book.level == level, Book.title == title)
        ).scalar_one_or_none()
        if existing:
            return False
        db.add(Book(level=level, title=title, author=author, content=content))
        db.commit()
        return True
 
 
# ============================================
# LINGUAPLAY: ПЕРЕВОД СЛОВ/ФРАЗ (клик по тексту книги)
# ============================================
async def translate_word_or_phrase(telegram_id: int, text: str, book_level: str) -> dict:
    """
    Логика "сначала база, потом DeepSeek" — теперь для СЛОВ И ФРАЗ:
    если текст уже переводился раньше (или совпадает с существующей
    карточкой), отдаём из таблицы words мгновенно, без обращения к
    DeepSeek. Если нет — переводим и СОХРАНЯЕМ (слова как item_type='word',
    фразы как item_type='sentence' — таблица уже была на это рассчитана).
 
    Раньше фразы не кэшировались вообще — каждый повторный перевод одной
    и той же выделенной фразы бил в DeepSeek заново. Теперь кэшируются
    точным совпадением текста (без учёта регистра).
    """
    from src.deepseek_client import translate_text  # локальный импорт — иначе цикл database<->deepseek_client
 
    text = text.strip()
    is_phrase = " " in text or len(text.split()) > 1
    item_type = "sentence" if is_phrase else "word"
 
    with get_db() as db:
        existing = db.execute(
            select(Word).where(func.lower(Word.word) == text.lower(), Word.item_type == item_type)
        ).scalars().first()
        if existing:
            return {
                "translation": existing.translation, "word_id": existing.id,
                "from_cache": True, "is_phrase": is_phrase,
            }
 
    translation = await translate_text(text, is_phrase)
 
    upsert_word(book_level, item_type, text, translation, None)
    with get_db() as db:
        word_row = db.execute(
            select(Word).where(Word.level == book_level, Word.item_type == item_type, Word.word == text)
        ).scalar_one_or_none()
        word_id = word_row.id if word_row else None
 
    return {"translation": translation, "word_id": word_id, "from_cache": False, "is_phrase": is_phrase}
 
 
# ============================================
# ПОВТОРЕНИЕ ПО ЛЕЙТНЕРУ
# ============================================
LEITNER_INTERVALS_DAYS = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}
LEITNER_MAX_BOX = 5
REVIEW_SESSION_LIMIT = 15
REVIEW_EXP_PER_CORRECT = 3
 
 
def count_due_review_words(telegram_id: int) -> int:
    with get_db() as db:
        return db.execute(
            select(func.count()).select_from(UserWord).where(
                UserWord.telegram_id == telegram_id, UserWord.next_review_at <= _now()
            )
        ).scalar()
 
 
def get_due_review_words(telegram_id: int, limit: int = REVIEW_SESSION_LIMIT) -> list:
    """Слова к повторению: next_review_at уже наступил, сначала самые
    проблемные (маленький box_number) — так просит ТЗ."""
    with get_db() as db:
        rows = db.execute(
            select(UserWord, Word).join(Word).where(
                UserWord.telegram_id == telegram_id, UserWord.next_review_at <= _now()
            ).order_by(UserWord.box_number.asc(), UserWord.next_review_at.asc()).limit(limit)
        ).all()
        return [
            {
                "word_id": w.id, "es": w.word, "ru": w.translation,
                "example": w.example, "box_number": uw.box_number,
            }
            for uw, w in rows
        ]
 
 
def get_achievement_progress(telegram_id: int, key: str) -> dict:
    """Возвращает {current, target, hint} — сколько уже сделано, сколько
    нужно всего, и человекочитаемое пояснение условия."""
    with get_db() as db:
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if not user:
            raise ValueError("Пользователь не найден")
 
    if key.startswith("lexicon_"):
        level = key.split("_", 1)[1].upper()
        progress = get_level_progress(telegram_id, level, "word")
        return {
            "current": progress["learned"], "target": progress["total"],
            "hint": f"Выучи все слова уровня {level}, чтобы получить эту ачивку.",
        }
 
    if key.startswith("grammar_guru_"):
        level = key.split("_", 2)[2].upper()
        with get_db() as db:
            total = db.execute(select(func.count()).select_from(GrammarBlock).where(GrammarBlock.level == level)).scalar()
            completed = db.execute(
                select(func.count()).select_from(UserGrammarProgress).join(
                    GrammarBlock, UserGrammarProgress.block_id == GrammarBlock.id
                ).where(
                    UserGrammarProgress.telegram_id == telegram_id,
                    UserGrammarProgress.is_completed.is_(True),
                    GrammarBlock.level == level,
                )
            ).scalar()
        return {
            "current": completed, "target": total,
            "hint": f"Пройди все темы грамматики уровня {level}, чтобы получить эту ачивку.",
        }
 
    if key == "streak_king":
        with get_db() as session:
            user_row = session.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        return {
            "current": min(user_row.streak_count, STREAK_KING_THRESHOLD), "target": STREAK_KING_THRESHOLD,
            "hint": f"Занимайся {STREAK_KING_THRESHOLD} дней подряд без пропусков.",
        }
 
    if key == "marathoner":
        with get_db() as session:
            user_row = session.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        return {
            "current": min(user_row.packs_completed, MARATHONER_THRESHOLD), "target": MARATHONER_THRESHOLD,
            "hint": f"Пройди {MARATHONER_THRESHOLD} паков карточек полностью.",
        }
 
    if key == "movie_critic":
        return {"current": 0, "target": 1, "hint": "Скоро — раздел с сериалами Extra Español ещё не добавлен."}
 
    if key == "social_butterfly":
        return {"current": 0, "target": 1, "hint": "Скоро — система друзей ещё не добавлена."}
 
    return {"current": 0, "target": 1, "hint": "Условие не определено."}
