import asyncio
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import config
from mexc_ws import MexcWebSocket
from scanner import Scanner
from telegram_bot import TelegramBot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def start_health_server(port=8080):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"✅ Health check server запущен на порту {port}")
    server.serve_forever()


async def main():
    logger.info("🚀 Запуск MEXC Signal Bot...")

    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    telegram = TelegramBot(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID)
    scanner = Scanner(telegram)
    ws = MexcWebSocket(scanner, config.TOP_SYMBOLS)

    await telegram.send_menu(
        f"✅ <b>MEXC Signal Bot запущен!</b>\n"
        f"📊 Мониторинг: {len(config.TOP_SYMBOLS)} пар\n"
        f"⏱ Таймфреймы: 15м + 1ч\n\n"
        f"Выбери действие:"
    )

    await asyncio.gather(
        run_websocket(ws, telegram),
        telegram.handle_updates(scanner)
    )


async def run_websocket(ws, telegram):
    """WebSocket с автореконнектом"""
    while True:
        try:
            await ws.run()
        except Exception as e:
            logger.error(f"WebSocket ошибка: {e}")
            await telegram.send_message(f"⚠️ Переподключение к MEXC...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
