
"""
tts.py — озвучка испанских слов через edge-tts (бесплатный, без API-ключей).
 
Кэш на диске: одно и то же слово озвучивается один раз, дальше отдаём
готовый файл. Имя файла — читаемый slug + короткий хэш (чтобы избежать
коллизий омонимов после нормализации и path traversal через спецсимволы).
"""
import hashlib
import re
import asyncio
import uuid
from pathlib import Path
 
import edge_tts
 
AUDIO_DIR = Path(__file__).parent.parent / "web" / "static" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
 
# es-ES-ElviraNeural — европейский испанский. Для мексиканского варианта
# смени на "es-MX-DaliaNeural".
VOICE = "es-ES-ElviraNeural"
_generation_slots = asyncio.Semaphore(3)
 
 
def _slugify(word: str) -> str:
    slug = word.strip().lower()
    slug = re.sub(r"[^a-zñáéíóúü0-9]+", "_", slug)  # только безопасные для имени файла символы
    slug = slug.strip("_") or "word"
    return slug[:50]
 
 
def _filename_for(word: str) -> str:
    slug = _slugify(word)
    digest = hashlib.md5(word.strip().lower().encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{digest}.mp3"
 
 
async def get_or_create_audio(word: str) -> str:
    """Возвращает URL вида /static/audio/xxx.mp3. Генерирует файл, если
    его ещё нет в кэше на диске."""
    word = word.strip()
    if not word:
        raise ValueError("Пустое слово")
 
    filename = _filename_for(word)
    path = AUDIO_DIR / filename
 
    if not path.exists():
        async with _generation_slots:
            if not path.exists():
                temporary = AUDIO_DIR / f"{uuid.uuid4().hex}.tmp"
                try:
                    communicate = edge_tts.Communicate(word, VOICE)
                    await asyncio.wait_for(communicate.save(str(temporary)), timeout=25)
                    if not temporary.stat().st_size:
                        raise ValueError("Empty audio response")
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
 
    return f"/static/audio/{filename}"
