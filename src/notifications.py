"""
notifications.py — рассылки через бота: напоминание о стрике и факты от Хосе.
 
⚠️ Ограничение упрощения: время напоминания задано в UTC одним фиксированным
часом для ВСЕХ пользователей, без учёта их личного часового пояса — в БД
не хранится timezone юзера (в /start Telegram его не присылает без
специального запроса геолокации/языка). "4-6 часов до конца дня" в ТЗ
предполагает персональный часовой пояс — для точной реализации нужно
сначала научиться его получать/спрашивать у пользователя.
"""
import logging
import random
from datetime import datetime, timezone
 
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
 
from src.bot import bot, _app_keyboard
from src import database as db
 
logger = logging.getLogger(__name__)
 
STREAK_REMINDER_HOUR_UTC = 18  # см. предупреждение выше про часовые пояса
 
JOSE_FACTS = [
    "🇪🇸 Un poquito cada día — понемногу каждый день. Начни с пяти карточек в LingoPal.",
    "📖 Запоминай существительные вместе с артиклем: el libro, la casa. Это помогает сразу учить род слова.",
    "💬 Soy de Madrid — я из Мадрида; estoy en Madrid — я в Мадриде. Потренируй ser и estar с Хосе.",
    "✍️ Вопросительные qué, cómo и dónde пишутся с ударением. В грамматике есть упражнения на вопросы.",
    "🧩 Хочешь сказать «я только что пришёл»? Acabo de llegar. Ещё больше полезных конструкций — в грамматике.",
    "📚 Незнакомое слово в истории можно нажать и перевести. Загляни в раздел чтения LingoPal.",
    "🔄 Повторение помогает закреплять слова. Посмотри, что уже ждёт тебя в личном словаре.",
    "🌱 Ошибки — часть практики. Пройди одну тему, прочитай объяснения и попробуй снова.",
]


async def send_streak_reminders():
    """Раз в день (см. CronTrigger ниже): напоминание тем, кто сегодня
    ещё не выполнил ни одного засчитываемого действия."""
    users = db.get_users_inactive_today()
    logger.info(f"[notifications] стрик-напоминание: {len(users)} неактивных сегодня")
 
    for user in users:
        name = user["first_name"] or "друг"
        text = f"⏳ {name}, твой стрик в опасности! Сегодня ещё можно немного позаниматься. Загляни в LingoPal на пару минут! 🇪🇸"
        try:
            await bot.send_message(user["telegram_id"], text, reply_markup=_app_keyboard())
        except Exception as e:
            # Частая причина — пользователь заблокировал бота. Не роняем всю рассылку из-за одного.
            logger.warning(f"[notifications] не удалось отправить {user['telegram_id']}: {e}")
 
 
async def send_jose_facts():
    """1-2 раза в неделю (см. CronTrigger ниже): случайный факт всем пользователям."""
    users = db.get_all_users()
    fact = random.choice(JOSE_FACTS)
    logger.info(f"[notifications] рассылка факта: {len(users)} пользователей")
 
    for user in users:
        try:
            await bot.send_message(user["telegram_id"], fact, reply_markup=_app_keyboard())
        except Exception as e:
            logger.warning(f"[notifications] не удалось отправить {user['telegram_id']}: {e}")
 
 
def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        send_streak_reminders,
        CronTrigger(hour=STREAK_REMINDER_HOUR_UTC, minute=0),
        id="streak_reminder",
    )
    # Пн и Чт в 12:00 UTC — соответствует "1-2 раза в неделю" из ТЗ
    scheduler.add_job(
        send_jose_facts,
        CronTrigger(day_of_week="mon,thu", hour=12, minute=0),
        id="jose_facts",
    )
    return scheduler
 
