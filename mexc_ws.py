import asyncio
import json
import logging
import aiohttp
from collections import defaultdict

logger = logging.getLogger(__name__)

BINANCE_REST_URL = "https://fapi.binance.com/fapi/v1/klines"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "MATICUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "BCHUSDT",
    "FILUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
    "SUIUSDT", "INJUSDT", "TIAUSDT", "SEIUSDT", "WIFUSDT",
    "PEPEUSDT", "SHIBUSDT", "FTMUSDT", "AAVEUSDT", "MKRUSDT"
]


def to_scanner_symbol(symbol: str) -> str:
    return symbol.replace("USDT", "_USDT")


class MexcWebSocket:
    def __init__(self, scanner, symbols: list):
        self.scanner = scanner
        self.candles = defaultdict(lambda: defaultdict(list))
        self.MAX_CANDLES = 60
        self.request_count = 0

    async def fetch_klines(self, session, symbol: str, interval: str, limit: int = 50):
        try:
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            async with session.get(BINANCE_REST_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candles = []
                    for k in data:
                        candles.append({
                            "time": k[0],
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                            "closed": True
                        })
                    return candles
                else:
                    logger.error(f"❌ {symbol} {interval}: HTTP {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"❌ Ошибка запроса {symbol} {interval}: {e}")
            return []

    async def scan_symbol(self, session, symbol: str):
        candles_15m = await self.fetch_klines(session, symbol, "15m", 50)
        await asyncio.sleep(0.1)
        candles_1h = await self.fetch_klines(session, symbol, "1h", 50)

        scanner_symbol = to_scanner_symbol(symbol)

        if len(candles_15m) >= 30:
            self.candles[scanner_symbol]["Min15"] = candles_15m
            await self.scanner.analyze(scanner_symbol, "Min15", candles_15m)

        if len(candles_1h) >= 30:
            self.candles[scanner_symbol]["Hour1"] = candles_1h
            await self.scanner.analyze(scanner_symbol, "Hour1", candles_1h)

    async def run(self):
        logger.info("🚀 Запуск REST сканера Binance Futures...")
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    self.request_count += 1
                    logger.info(f"🔍 Сканирование #{self.request_count} — {len(SYMBOLS)} пар...")
                    for symbol in SYMBOLS:
                        await self.scan_symbol(session, symbol)
                        await asyncio.sleep(0.2)
                    logger.info(f"✅ Сканирование #{self.request_count} завершено")
                    await asyncio.sleep(30)
                except Exception as e:
                    logger.error(f"❌ Ошибка сканирования: {e}")
                    await asyncio.sleep(10)