"""Run the API and, when configured, the Telegram bot."""
import asyncio
import logging

import uvicorn
from src.api import app
from src.config import BOT_TOKEN, HOST, MINI_APP_URL, PORT


async def main():
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="info"))
    if not BOT_TOKEN:
        await server.serve()
        return
    if MINI_APP_URL == "https://example.com/" or not MINI_APP_URL.startswith("https://"):
        raise RuntimeError("Укажи HTTPS-адрес приложения в MINI_APP_URL")
    from src.bot import bot, dp
    from src.notifications import create_scheduler
    scheduler = create_scheduler()
    scheduler.start()
    api_task = asyncio.create_task(server.serve())
    bot_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    try:
        done, _ = await asyncio.wait([api_task, bot_task], return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        server.should_exit = True
        if not bot_task.done():
            bot_task.cancel()
        await asyncio.gather(api_task, bot_task, return_exceptions=True)
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
