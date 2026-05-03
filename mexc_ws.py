import asyncio
import json
import logging
import websockets
from collections import defaultdict

logger = logging.getLogger(__name__)

BINANCE_WS_URL = "wss://fstream.binance.com/stream"

SYMBOLS = [
   "btcusdt", "ethusdt", "solusdt", "bnbusdt", "xrpusdt",
   "dogeusdt", "adausdt", "avaxusdt", "linkusdt", "dotusdt",
   "maticusdt", "uniusdt", "atomusdt", "ltcusdt", "bchusdt",
   "filusdt", "nearusdt", "aptusdt", "arbusdt", "opusdt",
   "suiusdt", "injusdt", "tiausdt", "seiusdt", "wifusdt",
   "pepeusdt", "shibusdt", "ftmusdt", "aaveusdt", "mkrusdt"
]


def to_scanner_symbol(symbol: str) -> str:
   return symbol.upper().replace("USDT", "_USDT")


class MexcWebSocket:
   def __init__(self, scanner, symbols: list):
       self.scanner = scanner
       self.candles = defaultdict(lambda: defaultdict(list))
       self.MAX_CANDLES = 60
       self.streams = []
       for sym in SYMBOLS:
           self.streams.append(f"{sym}@kline_15m")
           self.streams.append(f"{sym}@kline_1h")

   async def run(self):
       streams_param = "/".join(self.streams)
       url = f"{BINANCE_WS_URL}?streams={streams_param}"
       async with websockets.connect(
           url,
           ping_interval=20,
           ping_timeout=10
       ) as ws:
           logger.info("✅ WebSocket подключён к Binance Futures")
           async for message in ws:
               await self._handle_message(message)

   async def _handle_message(self, raw_message: str):
       try:
           data = json.loads(raw_message)
           kline_data = data.get("data", {})
           if kline_data.get("e") != "kline":
               return
           k = kline_data.get("k", {})
           symbol_raw = k.get("s", "").lower()
           interval = k.get("i", "")
           closed = k.get("x", False)
           interval_map = {"15m": "Min15", "1h": "Hour1"}
           interval_key = interval_map.get(interval)
           if not interval_key:
               return
           symbol = to_scanner_symbol(symbol_raw)
           candle = {
               "time": k.get("t"),
               "open": float(k.get("o", 0)),
               "high": float(k.get("h", 0)),
               "low": float(k.get("l", 0)),
               "close": float(k.get("c", 0)),
               "volume": float(k.get("v", 0)),
               "closed": closed
           }
           candles = self.candles[symbol][interval_key]
           if candles and candles[-1]["time"] == candle["time"]:
               candles[-1] = candle
           else:
               candles.append(candle)
               if len(candles) > self.MAX_CANDLES:
                   candles.pop(0)
           if closed and len(candles) >= 30:
               await self.scanner.analyze(symbol, interval_key, candles.copy())
       except Exception as e:
           logger.error(f"Ошибка обработки сообщения: {e}")