from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Literal
import logging
import uuid

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ConfigDict

from src import database as db
from src.deepseek_client import ask_jose, ask_context
from src.tts import get_or_create_audio
from src import learning
from src.auth import require_user, is_local
from src.config import ALLOW_DEV_AUTH, DEEPSEEK_API_KEY
from src.middleware import RequestSizeLimit

BASE_DIR = Path(__file__).parent.parent
WEB_DIR = BASE_DIR / "web"

@asynccontextmanager
async def lifespan(app):
    db.init_db()
    from scripts.import_words import main as import_words
    from scripts.import_grammar import import_grammar
    from scripts.import_books import import_books
    import_words()
    import_grammar()
    import_books()
    yield


app = FastAPI(title="LingoPal API", lifespan=lifespan, dependencies=[Depends(require_user)])
app.add_middleware(RequestSizeLimit)
templates = Jinja2Templates(directory=WEB_DIR / "templates")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

SHARES_DIR = WEB_DIR / "static" / "shares"
SHARES_DIR.mkdir(parents=True, exist_ok=True)

VALID_LEVELS = {"A1", "A2", "B1", "B2"}
VALID_TYPES = {"word", "sentence"}
VALID_GRAMMAR_LEVELS = {"A1", "A2", "B1", "B2"}


@app.exception_handler(ValueError)
def bad_input(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(LookupError)
def not_found(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(PermissionError)
def forbidden(request, exc):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def mini_app_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request,
        "client_config": {"devUserId": 1 if ALLOW_DEV_AUTH and is_local(request) else None,
                          "assistantAvailable": bool(DEEPSEEK_API_KEY)}})


class UserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    telegram_id: int = Field(gt=0)


@app.post("/api/register")
def register(payload: UserRequest, request: Request):
    result = db.register_user(payload.telegram_id)
    db.set_first_name(payload.telegram_id, request.state.user.get("first_name"))
    return {"success": True, "user": result}


class StartPackRequest(UserRequest):
    level: Literal["A1", "A2", "B1", "B2"]
    item_type: Literal["word", "sentence"] = "word"
    size: int = Field(default=10, ge=5, le=20)


@app.post("/api/packs/start")
def start_pack(payload: StartPackRequest):
    if payload.level not in VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"Неверный уровень: {payload.level}")
    if payload.item_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Неверный тип: {payload.item_type}")
    result = db.start_pack(payload.telegram_id, payload.level, payload.item_type, payload.size)
    if result.get("error") == "no_words_available":
        raise HTTPException(status_code=404, detail="Свежих слов для нового пака не осталось на этом уровне")
    return {"success": True, "pack": result}


class SwipeRequest(BaseModel):
    telegram_id: int
    word_id: int
    knows: bool


@app.post("/api/packs/{pack_key}/swipe")
def pack_swipe(pack_key: str, payload: SwipeRequest):
    result = db.swipe_pack(payload.telegram_id, pack_key, payload.word_id, payload.knows)
    if result is None:
        raise HTTPException(status_code=404, detail="Пак не найден")
    return {"success": True, "pack": result}


@app.post("/api/packs/{pack_key}/continue")
def pack_continue(pack_key: str, payload: UserRequest):
    result = db.continue_pack(payload.telegram_id, pack_key)
    if result is None:
        raise HTTPException(status_code=404, detail="Пак не найден")
    return {"success": True, "pack": result}


@app.post("/api/packs/{pack_key}/finish")
def pack_finish(pack_key: str, payload: UserRequest):
    result = db.finish_pack(payload.telegram_id, pack_key)
    if result is None:
        raise HTTPException(status_code=404, detail="Пак не найден")
    if result.get("error") == "not_fully_learned":
        raise HTTPException(status_code=409, detail="В паке ещё остались невыученные слова")
    return {"success": True, **result}


@app.delete("/api/packs/{pack_key}")
def pack_delete(pack_key: str, telegram_id: int):
    if not db.delete_pack(telegram_id, pack_key):
        raise HTTPException(status_code=404, detail="Пак не найден")
    return {"success": True}


@app.get("/api/packs")
def packs_list(telegram_id: int, level: Optional[str] = None):
    return {"success": True, "packs": db.list_packs(telegram_id, level)}


class CreateReviewRequest(BaseModel):
    telegram_id: int
    word_ids: list[int] = Field(min_length=1, max_length=200)


@app.post("/api/review/create")
def review_create(payload: CreateReviewRequest):
    if not payload.word_ids:
        raise HTTPException(status_code=400, detail="Выбери хотя бы одно слово")
    result = db.create_review_pack(payload.telegram_id, payload.word_ids)
    if result.get("error") == "empty_selection":
        raise HTTPException(status_code=400, detail="Ни одно из выбранных слов не найдено в твоём словаре")
    return {"success": True, "pack": result}


@app.get("/api/review/packs")
def review_packs(telegram_id: int):
    return {"success": True, "packs": db.list_review_packs(telegram_id)}


@app.get("/api/progress")
def progress(telegram_id: int, level: str, item_type: str = "word"):
    if level not in VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"Неверный уровень: {level}")
    return {"success": True, **db.get_level_progress(telegram_id, level, item_type)}


@app.get("/api/profile")
def profile(telegram_id: int):
    result = db.get_profile(telegram_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {"success": True, **result}


@app.get("/api/quests")
def get_quests(telegram_id: int):
    return {"success": True, **db.get_quests_view(telegram_id)}


@app.get("/api/tts")
async def tts(word: str = Query(min_length=1, max_length=512)):
    if not word.strip():
        raise HTTPException(status_code=400, detail="Пустое слово")
    try:
        url = await get_or_create_audio(word)
    except Exception as e:
        logging.getLogger(__name__).warning("TTS unavailable: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Озвучка временно недоступна. Попробуй позже.")
    return {"success": True, "url": url}


@app.get("/api/dictionary")
def get_dictionary(telegram_id: int, level: Optional[str] = None, letter: Optional[str] = None, search: Optional[str] = None):
    return {"success": True, "entries": db.get_dictionary(telegram_id, level=level, letter=letter, search=search)}


class AddToDictionaryRequest(BaseModel):
    telegram_id: int
    word_id: int


@app.post("/api/dictionary")
def add_to_dictionary(payload: AddToDictionaryRequest):
    try:
        added = db.add_word_to_dictionary(payload.telegram_id, payload.word_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True, "added": added}


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class AskRequest(UserRequest):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=30)


@app.post("/api/ask")
async def ask(payload: AskRequest):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Пустое сообщение")
    try:
        reply = await ask_jose(payload.message, [item.model_dump() for item in payload.history])
    except Exception as e:
        raise HTTPException(status_code=503, detail="Хосе пока недоступен. Попробуй позже.")

    streak_result = None
    quest_events = []
    unlocked_achievements = []

    if payload.telegram_id:
        try:
            streak_result = db.update_streak(payload.telegram_id)
            quest_events = db.record_quest_progress(payload.telegram_id, "jose_questions", 1)
            unlocked_achievements = db.check_achievements(payload.telegram_id)
        except ValueError:
            pass

    return {
        "success": True,
        "reply": reply,
        "streak_result": streak_result,
        "quest_events": quest_events,
        "unlocked_achievements": unlocked_achievements,
    }


class AskContextRequest(BaseModel):
    word: str = Field(min_length=1, max_length=512)
    translation: str = Field(min_length=1, max_length=512)


@app.post("/api/ask-context")
async def ask_word_context(payload: AskContextRequest):
    try:
        result = await ask_context(payload.word, payload.translation)
    except Exception as e:
        raise HTTPException(status_code=503, detail="Хосе временно недоступен. Попробуй позже.")
    return {"success": True, **result}


# ============================================
# ГРАММАТИКА — ROUTES СОВПАДАЮТ С grammar.js
# ============================================

@app.get("/api/grammar/blocks")
def grammar_blocks(telegram_id: int, level: str):
    if level not in VALID_GRAMMAR_LEVELS:
        raise HTTPException(status_code=400, detail=f"Неверный уровень: {level}")

    return {
        "success": True,
        "blocks": db.get_grammar_blocks(telegram_id, level),
    }


@app.get("/api/grammar/blocks/{block_id}")
def grammar_block_detail(block_id: str, request: Request):
    block = learning.require_block_access(request.state.user["id"], block_id)
    if not block:
        raise HTTPException(status_code=404, detail="Блок грамматики не найден")

    return {"success": True, "block": block}


@app.get("/api/grammar/blocks/{block_id}/questions")
def grammar_block_questions(block_id: str, request: Request):
    learning.require_block_access(request.state.user["id"], block_id)
    return {"success": True, "questions": [learning.public_question(q) for q in db.get_grammar_questions(block_id)]}


class GrammarCompleteRequest(UserRequest):
    attempt_id: str = Field(min_length=32, max_length=32)


@app.post("/api/grammar/blocks/{block_id}/complete")
def grammar_complete(block_id: str, payload: GrammarCompleteRequest):
    return {"success": True, **learning.finish_grammar(payload.telegram_id, block_id, payload.attempt_id)}


@app.post("/api/grammar/blocks/{block_id}/start")
def grammar_start(block_id: str, payload: UserRequest):
    return {"success": True, **learning.start_grammar(payload.telegram_id, block_id)}


class GrammarAnswerRequest(UserRequest):
    attempt_id: str = Field(min_length=32, max_length=32)
    question_id: str = Field(min_length=1, max_length=64)
    answer: str | bool | list[str]


@app.post("/api/grammar/answer")
def grammar_answer(payload: GrammarAnswerRequest):
    return {"success": True, **learning.answer_grammar(payload.telegram_id, payload.attempt_id,
                                                       payload.question_id, payload.answer)}


class SetGrammarLevelRequest(BaseModel):
    telegram_id: int
    level: str


@app.post("/api/user/set-grammar-level")
def set_grammar_level(payload: SetGrammarLevelRequest):
    if payload.level not in VALID_GRAMMAR_LEVELS:
        raise HTTPException(status_code=400, detail=f"Неверный уровень: {payload.level}")
    try:
        db.set_grammar_level(payload.telegram_id, payload.level)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True}


@app.get("/api/profile/stats")
def profile_stats(telegram_id: int):
    return {"success": True, **db.get_profile_stats(telegram_id)}


@app.get("/api/achievements")
def achievements(telegram_id: int):
    return {"success": True, "achievements": db.get_achievements_view(telegram_id)}


@app.get("/api/achievements/{key}/progress")
def achievement_progress(key: str, telegram_id: int):
    try:
        result = db.get_achievement_progress(telegram_id, key)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True, **result}


class VisibilityRequest(BaseModel):
    telegram_id: int
    is_public: bool


@app.post("/api/user/settings")
def user_settings(payload: VisibilityRequest):
    try:
        db.set_user_visibility(payload.telegram_id, payload.is_public)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True}


@app.post("/api/share/upload")
async def share_upload(telegram_id: int, file: UploadFile = File(...)):
    filename = f"{uuid.uuid4().hex}.png"
    path = SHARES_DIR / filename
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Файл слишком большой (лимит 5 МБ)")
    if file.content_type != "image/png" or not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=415, detail="Нужен файл PNG")
    path.write_bytes(content)
    return {"success": True, "url": f"/static/shares/{filename}"}


@app.get("/api/books")
def books_list(telegram_id: int, level: str):
    if level not in VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"Неверный уровень: {level}")
    return {"success": True, "books": db.get_books(level, telegram_id)}


@app.get("/api/books/{book_id}")
def book_detail(book_id: int, telegram_id: int):
    book = db.get_book_detail(book_id, telegram_id)
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")
    return {"success": True, "book": book}


class BookProgressRequest(BaseModel):
    telegram_id: int
    progress_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)


@app.post("/api/books/{book_id}/progress")
def book_progress(book_id: int, payload: BookProgressRequest):
    result = db.save_book_progress(payload.telegram_id, book_id, payload.progress_ratio)
    return {"success": True, **result}


class TranslateRequest(BaseModel):
    telegram_id: int
    text: str = Field(min_length=1, max_length=512)
    book_level: Literal["A1", "A2", "B1", "B2"] = "A1"


@app.post("/api/translate")
async def translate(payload: TranslateRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Пустой текст")
    try:
        result = await db.translate_word_or_phrase(
            payload.telegram_id,
            payload.text,
            payload.book_level,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail="Перевод временно недоступен. Попробуй позже.")
    return {"success": True, **result}


@app.get("/api/review/due-count")
def review_due_count(telegram_id: int):
    return {"success": True, "count": db.count_due_review_words(telegram_id)}


@app.get("/api/review/due-words")
def review_due_words(telegram_id: int):
    return {"success": True, "words": db.get_due_review_words(telegram_id)}


class ReviewAnswerRequest(BaseModel):
    telegram_id: int
    session_id: str = Field(min_length=32, max_length=32)
    word_id: int
    correct: bool


@app.post("/api/review/answer")
def review_answer(payload: ReviewAnswerRequest):
    try:
        result = learning.answer_review(
            payload.telegram_id,
            payload.session_id,
            payload.word_id,
            payload.correct,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True, **result}


class FinishReviewRequest(UserRequest):
    session_id: str = Field(min_length=32, max_length=32)


@app.post("/api/review/finish-session")
def review_finish_session(payload: FinishReviewRequest):
    result = learning.finish_review(
        payload.telegram_id,
        payload.session_id,
    )
    return {"success": True, **result}


@app.post("/api/review/start")
def review_start(payload: UserRequest):
    return {"success": True, **learning.start_review(payload.telegram_id)}
