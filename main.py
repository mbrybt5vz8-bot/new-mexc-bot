import asyncio
import logging
import config
from mexc_ws import MexcWebSocket
from scanner import Scanner
from telegram_bot import TelegramBot

logging.basicConfig(
   level=logging.INFO,
   format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
   logger.info("🚀 Запуск MEXC Signal Bot...")
   telegram = TelegramBot(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID)
   scanner = Scanner(telegram)
   ws = MexcWebSocket(scanner, config.TOP_SYMBOLS)

   await telegram.send_menu(
       f"✅ <b>MEXC Signal Bot запущен!</b>\n"
       f"📊 Мониторинг: 30 пар\n"
       f"⏱ Таймфреймы: 15м + 1ч\n\n"
       f"Выбери действие:"
   )

   await asyncio.gather(
       run_websocket(ws, telegram),
       telegram.handle_updates(scanner)
   )


async def run_websocket(ws, telegram):
   while True:
       try:
           await ws.run()
       except Exception as e:
           logger.error(f"WebSocket ошибка: {e}")
           await asyncio.sleep(5)


if __name__ == "__main__":
   asyncio.run(main())