import asyncio
import logging
import aiohttp
from collections import defaultdict

logger = logging.getLogger(__name__)

MEXC_REST_URL = "https://contract.mexc.com/api/v1/contract/kline"

SYMBOLS = [
    "BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "XRP_USDT",
    "DOGE_USDT", "ADA_USDT", "AVAX_USDT", "LINK_USDT", "DOT_USDT",
    "MATIC_USDT", "UNI_USDT", "ATOM_USDT", "LTC_USDT", "BCH_USDT",
    "FIL_USDT", "NEAR_USDT", "APT_USDT", "ARB_USDT", "OP_USDT",
    "SUI_USDT", "INJ_USDT", "TIA_USDT", "SEI_USDT", "WIF_USDT",
    "PEPE_USDT", "SHIB_USDT", "FTM_USDT", "AAVE_USDT", "MKR_USDT"
]


def to_scanner_symbol(symbol: str) -> str:
    return symbol


class MexcWebSocket:
    def __init__(self, scanner, symbols: list):
        self.scanner = scanner
        self.candles = defaultdict(lambda: defaultdict(list))
        self.scan_count = 0

    async def fetch_klines(self, session, symbol: str, interval: str, limit: int = 50):
        try:
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            async with session.get(
                MEXC_REST_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if not data.get("success"):
                        logger.error(f"❌ {symbol} {interval}: {data.get('message')}")
                        return []
                    raw = data.get("data", {})
                    times = raw.get("time", [])
                    opens = raw.get("open", [])
                    highs = raw.get("high", [])
                    lows = raw.get("low", [])
                    closes = raw.get("close", [])
                    volumes = raw.get("vol", [])
                    candles = []
                    for i in range(len(times)):
                        candles.append({
                            "time": times[i],
                            "open": float(opens[i]),
                            "high": float(highs[i]),
                            "low": float(lows[i]),
                            "close": float(closes[i]),
                            "volume": float(volumes[i]),
                            "closed": True
                        })
                    return candles
                else:
                    logger.error(f"❌ {symbol} {interval}: HTTP {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"❌ Ошибка {symbol} {interval}: {e}")
            return []

    async def scan_symbol(self, session, symbol: str):
        candles_15m = await self.fetch_klines(session, symbol, "Min15", 50)
        await asyncio.sleep(0.2)
        candles_1h = await self.fetch_klines(session, symbol, "Hour1", 50)

        if len(candles_15m) >= 30:
            await self.scanner.analyze(symbol, "Min15", candles_15m)

        if len(candles_1h) >= 30:
            await self.scanner.analyze(symbol, "Hour1", candles_1h)

    async def run(self):
        logger.info("🚀 Запуск REST сканера MEXC...")
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    self.scan_count += 1
                    logger.info(f"🔍 Сканирование #{self.scan_count} — {len(SYMBOLS)} пар...")
                    for symbol in SYMBOLS:
                        await self.scan_symbol(session, symbol)
                        await asyncio.sleep(0.2)
                    logger.info(f"✅ Сканирование #{self.scan_count} завершено")
                    await asyncio.sleep(30)
                except Exception as e:
                    logger.error(f"❌ Ошибка: {e}")
                    await asyncio.sleep(10)