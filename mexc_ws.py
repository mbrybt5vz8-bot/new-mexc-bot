import asyncio
import json
import logging
import websockets
from collections import defaultdict

logger = logging.getLogger(__name__)

MEXC_WS_URL = "wss://contract.mexc.com/edge"


class MexcWebSocket:
    def __init__(self, scanner, symbols: list):
        self.scanner = scanner
        self.symbols = symbols
        self.candles = defaultdict(lambda: defaultdict(list))
        self.MAX_CANDLES = 60

    async def run(self):
        async with websockets.connect(
            MEXC_WS_URL,
            ping_interval=20,
            ping_timeout=10,
            extra_headers={"User-Agent": "Mozilla/5.0"}
        ) as ws:
            logger.info("✅ WebSocket подключён к MEXC")
            await self._subscribe(ws)
            asyncio.create_task(self._keep_alive(ws))

            async for message in ws:
                await self._handle_message(message)

    async def _subscribe(self, ws):
        for symbol in self.symbols:
            for interval in ["Min15", "Hour1"]:
                sub = {
                    "method": "sub.kline",
                    "param": {"symbol": symbol, "interval": interval}
                }
                await ws.send(json.dumps(sub))
                await asyncio.sleep(0.05)
        logger.info(f"✅ Подписка на {len(self.symbols)} пар × 2 таймфрейма")

    async def _keep_alive(self, ws):
        while True:
            try:
                await ws.send(json.dumps({"method": "ping"}))
                await asyncio.sleep(20)
            except Exception:
                break

    async def _handle_message(self, raw_message: str):
        try:
            data = json.loads(raw_message)

            if data.get("channel") != "push.kline":
                return

            symbol = data.get("symbol")
            if not symbol:
                return

            kline_data = data.get("data", {})
            interval = kline_data.get("interval")

            candle = {
                "time": kline_data.get("t"),
                "open": float(kline_data.get("o", 0)),
                "high": float(kline_data.get("h", 0)),
                "low": float(kline_data.get("l", 0)),
                "close": float(kline_data.get("c", 0)),
                "volume": float(kline_data.get("q", 0)),
            }

            candles = self.candles[symbol][interval]

            if candles and candles[-1]["time"] == candle["time"]:
                candles[-1] = candle
            else:
                if candles and len(candles) >= 30:
                    await self.scanner.analyze(symbol, interval, candles.copy())

                candles.append(candle)
                if len(candles) > self.MAX_CANDLES:
                    candles.pop(0)

        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")
