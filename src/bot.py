import asyncio
import logging
 
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
 
from src.config import BOT_TOKEN, MINI_APP_URL
from src import database as db
 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
 
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
 
 
def _app_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📚 Учить испанский", web_app=WebAppInfo(url=MINI_APP_URL))
    ]])
 
 
@dp.message(Command("start"))
async def cmd_start(message: Message):
    db.create_user(message.from_user.id)
    db.set_first_name(message.from_user.id, message.from_user.first_name)
    await message.answer(
        "¡Hola! 👋 Это приложение для изучения испанского.\n"
        "Карточки, свайпы, личный словарь — открывай и учись 👇",
        reply_markup=_app_keyboard(),
    )
 
 
async def main():
    await dp.start_polling(bot)
 
 
if __name__ == "__main__":
    asyncio.run(main())
