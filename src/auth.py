"""Verify Telegram Mini App initData before accessing user data."""
import hashlib
import hmac
import json
import time
from collections import OrderedDict, deque
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request

from src.config import ALLOW_DEV_AUTH, BOT_TOKEN, INIT_DATA_MAX_AGE

_requests = OrderedDict()
_limited_paths = {"/api/ask", "/api/ask-context", "/api/translate", "/api/tts"}


def is_local(request: Request) -> bool:
    return bool(request.client and request.client.host in {"127.0.0.1", "::1", "localhost", "testclient"}
                and not request.headers.get("x-forwarded-for"))


def validate_init_data(raw: str, token: str, now: float | None = None) -> dict:
    try:
        pairs = parse_qsl(raw, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError("duplicate fields")
        received_hash = fields.pop("hash")
        check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not token or not hmac.compare_digest(received_hash, expected):
            raise ValueError("invalid signature")
        age = (time.time() if now is None else now) - int(fields["auth_date"])
        if age < -30 or age > INIT_DATA_MAX_AGE:
            raise ValueError("expired data")
        user = json.loads(fields["user"])
        if not isinstance(user, dict) or type(user.get("id")) is not int or not 0 < user["id"] < 2**63:
            raise ValueError("invalid user")
        return user
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(401, "Сессия Telegram недействительна. Открой приложение заново.") from exc


async def require_user(request: Request):
    if not request.url.path.startswith("/api/") or request.url.path == "/api/health":
        return
    raw = request.headers.get("X-Telegram-Init-Data", "")
    if raw:
        user = validate_init_data(raw, BOT_TOKEN)
    elif ALLOW_DEV_AUTH and is_local(request):
        try:
            user_id = int(request.headers.get("X-Dev-User", "0"))
            if user_id <= 0:
                raise ValueError()
            user = {"id": user_id, "first_name": "Друг"}
        except ValueError as exc:
            raise HTTPException(401, "Не указан локальный пользователь") from exc
    else:
        raise HTTPException(401, "Открой LingoPal через Telegram-бота")

    claimed = request.query_params.get("telegram_id")
    if request.method in {"POST", "PUT", "PATCH"} and request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(400, "Некорректный JSON") from exc
        if isinstance(body, dict) and "telegram_id" in body:
            if str(body["telegram_id"]) != str(user["id"]):
                raise HTTPException(403, "Нет доступа к данным другого пользователя")
    if claimed is not None and claimed != str(user["id"]):
        raise HTTPException(403, "Нет доступа к данным другого пользователя")
    request.state.user = user
    if request.url.path in _limited_paths:
        key = user["id"]
        clock = time.monotonic()
        queue = _requests.setdefault(key, deque())
        while queue and clock - queue[0] >= 60:
            queue.popleft()
        if len(queue) >= 30:
            raise HTTPException(429, "Дай Хосе минутку и попробуй снова.", headers={"Retry-After": "60"})
        queue.append(clock)
        _requests.move_to_end(key)
        if len(_requests) > 4096:
            _requests.popitem(last=False)
