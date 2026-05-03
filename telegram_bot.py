import asyncio
import logging
import aiohttp
import json

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.scanner_running = True
        self.signals_enabled = True

    # ─────────────────────────────────────────
    # ОТПРАВКА СООБЩЕНИЙ
    # ─────────────────────────────────────────

    async def send_message(self, text: str, reply_markup=None):
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Telegram error: {await resp.text()}")
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")

    async def answer_callback(self, callback_query_id: str, text: str = ""):
        url = f"{self.base_url}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id, "text": text}
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(url, json=payload)
        except Exception as e:
            logger.error(f"Ошибка callback: {e}")

    # ─────────────────────────────────────────
    # ГЛАВНОЕ МЕНЮ (кнопки как на скрине)
    # ─────────────────────────────────────────

    def _main_menu(self):
        scanner_btn = "🟢 Сканер ВКЛ" if self.scanner_running else "🔴 Сканер ВЫКЛ"
        signals_btn = "🔔 Сигналы ВКЛ" if self.signals_enabled else "🔕 Сигналы ВЫКЛ"
        return {
            "inline_keyboard": [
                [
                    {"text": scanner_btn, "callback_data": "toggle_scanner"},
                    {"text": signals_btn, "callback_data": "toggle_signals"}
                ],
                [
                    {"text": "📊 Статус", "callback_data": "status"},
                    {"text": "📋 Топ пары", "callback_data": "top_pairs"}
                ],
                [
                    {"text": "⚙️ Настройки", "callback_data": "settings"},
                    {"text": "❓ Помощь", "callback_data": "help"}
                ]
            ]
        }

    async def send_menu(self, text: str = "📡 <b>MEXC Signal Bot</b>\nВыбери действие:"):
        await self.send_message(text, reply_markup=self._main_menu())

    # ─────────────────────────────────────────
    # СИГНАЛ
    # ─────────────────────────────────────────

    async def send_signal(self, signal: dict):
        if not self.signals_enabled:
            return

        direction = signal["direction"]
        symbol = signal["symbol"].replace("_", "/")
        strength = signal["strength"]
        dir_emoji = "🟢 ЛОНГ" if direction == "LONG" else "🔴 ШОРТ"
        stars = "⭐" * strength + "☆" * (5 - strength)

        def fmt(price):
            if price > 1000:
                return f"{price:.2f}"
            elif price > 1:
                return f"{price:.4f}"
            else:
                return f"{price:.6f}"

        reasons_text = "\n".join(signal["reasons"])

        text = (
            f"{'─'*28}\n"
            f"{dir_emoji}  <b>{symbol}</b>\n"
            f"{'─'*28}\n"
            f"💪 Сила: {stars} ({strength}/5)\n\n"
            f"📍 Вход:     <b>{fmt(signal['entry'])}</b>\n"
            f"🛑 Стоп:     <b>{fmt(signal['stop_loss'])}</b>  (-{signal['stop_pct']:.2f}%)\n"
            f"🎯 Тейк 1:  <b>{fmt(signal['take1'])}</b>  (R:R 2:1)\n"
            f"🎯 Тейк 2:  <b>{fmt(signal['take2'])}</b>  (R:R 3:1)\n\n"
            f"📊 RSI 15м: {signal['rsi']:.1f}\n\n"
            f"<b>Условия:</b>\n{reasons_text}\n"
            f"{'─'*28}\n"
            f"⚠️ Не финансовый совет"
        )

        # Кнопки под сигналом
        markup = {
            "inline_keyboard": [[
                {"text": "🟢 Лонг на MEXC", "url": f"https://futures.mexc.com/exchange/{signal['symbol']}"},
                {"text": "🔴 Шорт на MEXC", "url": f"https://futures.mexc.com/exchange/{signal['symbol']}"}
            ]]
        }

        await self.send_message(text, reply_markup=markup)

    # ─────────────────────────────────────────
    # ОБРАБОТКА КОМАНД И КНОПОК
    # ─────────────────────────────────────────

    async def handle_updates(self, scanner=None):
        """Polling для обработки нажатий кнопок"""
        offset = None
        url = f"{self.base_url}/getUpdates"

        while True:
            try:
                params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
                if offset:
                    params["offset"] = offset

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=35)) as resp:
                        data = await resp.json()

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    await self._process_update(update, scanner)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Polling ошибка: {e}")
                await asyncio.sleep(5)

    async def _process_update(self, update: dict, scanner=None):
        # Текстовые команды
        if "message" in update:
            msg = update["message"]
            text = msg.get("text", "")
            if text == "/start" or text == "/menu":
                await self.send_menu("📡 <b>MEXC Signal Bot запущен!</b>\nВыбери действие:")

        # Нажатия кнопок
        elif "callback_query" in update:
            cb = update["callback_query"]
            data = cb.get("data", "")
            cb_id = cb["id"]

            if data == "toggle_scanner":
                self.scanner_running = not self.scanner_running
                status = "запущен ✅" if self.scanner_running else "остановлен ⛔"
                await self.answer_callback(cb_id, f"Сканер {status}")
                await self.send_menu(f"🔄 Сканер {status}")

            elif data == "toggle_signals":
                self.signals_enabled = not self.signals_enabled
                status = "включены 🔔" if self.signals_enabled else "выключены 🔕"
                await self.answer_callback(cb_id, f"Сигналы {status}")
                await self.send_menu(f"🔄 Сигналы {status}")

            elif data == "status":
                await self.answer_callback(cb_id)
                sc = "🟢 Работает" if self.scanner_running else "🔴 Остановлен"
                sg = "🔔 Включены" if self.signals_enabled else "🔕 Выключены"
                await self.send_message(
                    f"📊 <b>Статус бота</b>\n\n"
                    f"Сканер: {sc}\n"
                    f"Сигналы: {sg}\n"
                    f"Пар в мониторинге: 30\n"
                    f"Таймфреймы: 15м + 1ч",
                    reply_markup=self._main_menu()
                )

            elif data == "top_pairs":
                await self.answer_callback(cb_id)
                pairs = "BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, DOT, MATIC, UNI, ATOM, LTC, BCH, FIL, NEAR, APT, ARB, OP, SUI, INJ, TIA, SEI, WIF, PEPE, SHIB, FTM, AAVE, MKR"
                await self.send_message(
                    f"📋 <b>Топ-30 пар MEXC</b>\n\n{pairs}",
                    reply_markup=self._main_menu()
                )

            elif data == "settings":
                await self.answer_callback(cb_id)
                await self.send_message(
                    f"⚙️ <b>Настройки</b>\n\n"
                    f"Мин. сила сигнала: 3/5\n"
                    f"Мультипликатор объёма: ×1.5\n"
                    f"EMA: 21 / 55\n"
                    f"RSI перепродан: &lt;35\n"
                    f"RSI перекуплен: &gt;65\n"
                    f"Стоп: ATR × 1.5\n"
                    f"Тейк 1: R:R 2:1\n"
                    f"Тейк 2: R:R 3:1\n"
                    f"Антиспам: 1 сигнал / 4ч на пару",
                    reply_markup=self._main_menu()
                )

            elif data == "help":
                await self.answer_callback(cb_id)
                await self.send_message(
                    f"❓ <b>Как работает бот</b>\n\n"
                    f"1. Подключается к MEXC через WebSocket\n"
                    f"2. Следит за 30 топ-парами в реал-тайме\n"
                    f"3. Анализирует закрытие каждой свечи\n"
                    f"4. При 3+ условиях — отправляет сигнал\n\n"
                    f"<b>Условия сигнала:</b>\n"
                    f"📈 Тренд по EMA на 1ч\n"
                    f"📊 RSI на 15м\n"
                    f"📦 Объём выше среднего\n"
                    f"🎯 Цена у уровня\n"
                    f"⚡ EMA на 15м",
                    reply_markup=self._main_menu()
                )
