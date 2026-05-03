import logging
from collections import defaultdict
import config

logger = logging.getLogger(__name__)


def ema(values: list, period: int) -> float:
    if len(values) < period:
        return 0.0
    k = 2 / (period + 1)
    result = sum(values[:period]) / period
    for v in values[period:]:
        result = v * k + result * (1 - k)
    return result


def rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains[-period:]) / period if gains else 0
    avg_loss = sum(losses[-period:]) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(candles: list, period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period


def support_level(candles: list, lookback: int = 10) -> float:
    return min(c["low"] for c in candles[-lookback:])


def resistance_level(candles: list, lookback: int = 10) -> float:
    return max(c["high"] for c in candles[-lookback:])


class Scanner:
    def __init__(self, telegram):
        self.telegram = telegram
        self.data = defaultdict(dict)
        self.last_signal = {}

    async def analyze(self, symbol: str, interval: str, candles: list):
        self.data[symbol][interval] = candles

        if interval != "Min15":
            return

        if "Hour1" not in self.data[symbol]:
            logger.info(f"⏳ {symbol}: ждём данные 1ч")
            return

        candles_15m = self.data[symbol]["Min15"]
        candles_1h = self.data[symbol]["Hour1"]

        if len(candles_15m) < 30 or len(candles_1h) < 30:
            logger.info(f"⏳ {symbol}: мало свечей 15м={len(candles_15m)} 1ч={len(candles_1h)}")
            return

        last = self.last_signal.get(symbol, 0)
        current_time = candles_15m[-1]["time"]
        if current_time - last < 1 * 60 * 60 * 1000:
            return

        if not self.telegram.scanner_running:
            logger.info(f"🔴 Сканер выключен")
            return

        signal = self._calculate_signal(symbol, candles_15m, candles_1h)
        logger.info(f"🔍 {symbol}: сигнал={signal['direction'] if signal else 'нет'} сила={signal['strength'] if signal else 0}")

        if signal and signal["strength"] >= config.MIN_SIGNAL_STRENGTH:
            self.last_signal[symbol] = current_time
            await self.telegram.send_signal(signal)
            logger.info(f"📡 Сигнал отправлен: {symbol} {signal['direction']} (сила: {signal['strength']})")

    def _calculate_signal(self, symbol: str, c15: list, c1h: list):
        closes_15 = [c["close"] for c in c15]
        closes_1h = [c["close"] for c in c1h]
        current_price = closes_15[-1]

        ema21_15 = ema(closes_15, config.EMA_FAST)
        ema55_15 = ema(closes_15, config.EMA_SLOW)
        ema21_1h = ema(closes_1h, config.EMA_FAST)
        ema55_1h = ema(closes_1h, config.EMA_SLOW)

        rsi_15 = rsi(closes_15)
        atr_val = atr(c15, config.ATR_PERIOD)
        avg_vol = sum(c["volume"] for c in c15[-20:]) / 20
        last_vol = c15[-1]["volume"]
        support = support_level(c15)
        resistance = resistance_level(c15)

        dist_to_support = (current_price - support) / current_price * 100
        dist_to_resistance = (resistance - current_price) / current_price * 100

        long_score = 0
        long_reasons = []

        if ema21_1h > ema55_1h:
            long_score += 1
            long_reasons.append("📈 Тренд 1ч вверх (EMA21>EMA55)")
        if 40 <= rsi_15 <= 60:
            long_score += 1
            long_reasons.append(f"📊 RSI15 нейтрален ({rsi_15:.1f})")
        elif rsi_15 < config.RSI_OVERSOLD:
            long_score += 1
            long_reasons.append(f"📊 RSI15 перепродан ({rsi_15:.1f})")
        if last_vol > avg_vol * config.VOLUME_MULTIPLIER:
            long_score += 1
            long_reasons.append(f"📦 Объём ×{last_vol/avg_vol:.1f} от среднего")
        if dist_to_support < 1.5:
            long_score += 1
            long_reasons.append(f"🎯 Цена у поддержки ({support:.4f})")
        if ema21_15 > ema55_15:
            long_score += 1
            long_reasons.append("⚡ EMA15 бычье выравнивание")

        short_score = 0
        short_reasons = []

        if ema21_1h < ema55_1h:
            short_score += 1
            short_reasons.append("📉 Тренд 1ч вниз (EMA21<EMA55)")
        if 40 <= rsi_15 <= 60:
            short_score += 1
            short_reasons.append(f"📊 RSI15 нейтрален ({rsi_15:.1f})")
        elif rsi_15 > config.RSI_OVERBOUGHT:
            short_score += 1
            short_reasons.append(f"📊 RSI15 перекуплен ({rsi_15:.1f})")
        if last_vol > avg_vol * config.VOLUME_MULTIPLIER:
            short_score += 1
            short_reasons.append(f"📦 Объём ×{last_vol/avg_vol:.1f} от среднего")
        if dist_to_resistance < 1.5:
            short_score += 1
            short_reasons.append(f"🎯 Цена у сопротивления ({resistance:.4f})")
        if ema21_15 < ema55_15:
            short_score += 1
            short_reasons.append("⚡ EMA15 медвежье выравнивание")

        if long_score >= short_score and long_score >= config.MIN_SIGNAL_STRENGTH:
            direction, score, reasons = "LONG", long_score, long_reasons
        elif short_score > long_score and short_score >= config.MIN_SIGNAL_STRENGTH:
            direction, score, reasons = "SHORT", short_score, short_reasons
        else:
            return None

        stop_distance = atr_val * config.ATR_STOP_MULTIPLIER

        if direction == "LONG":
            stop_loss = current_price - stop_distance
            take1 = current_price + stop_distance * config.RISK_REWARD_1
            take2 = current_price + stop_distance * config.RISK_REWARD_2
        else:
            stop_loss = current_price + stop_distance
            take1 = current_price - stop_distance * config.RISK_REWARD_1
            take2 = current_price - stop_distance * config.RISK_REWARD_2

        stop_pct = abs(current_price - stop_loss) / current_price * 100

        return {
            "symbol": symbol,
            "direction": direction,
            "entry": current_price,
            "stop_loss": stop_loss,
            "take1": take1,
            "take2": take2,
            "strength": score,
            "stop_pct": stop_pct,
            "rsi": rsi_15,
            "reasons": reasons
        }