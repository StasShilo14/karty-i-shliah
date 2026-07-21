"""
Карти й Шлях — Telegram-бот для таро-розкладів
aiogram 3.x, AI-трактування через Claude API, 3 мови (UA/EN/ES), оплата Telegram Stars

Встановлення:
pip install aiogram==3.* aiohttp

Запуск:
1. Отримай токен у @BotFather (команда /newbot)
2. Встав токен у змінну середовища TAROT_BOT_TOKEN
3. Встав ключ у змінну середовища ANTHROPIC_API_KEY (для AI-трактувань)
4. python tarot_bot.py

Якщо ANTHROPIC_API_KEY не заданий — бот автоматично працює на фіксованих
текстах з cards_data.py (без збою функціоналу, просто без AI-персоналізації).
"""

import asyncio
import logging
import os
import random

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, Message, PreCheckoutQuery

from cards_data import FULL_DECK # повна колода — 78 карт (канонічні укр. назви)

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("TAROT_BOT_TOKEN", "ВСТАВ_СЮДИ_ТОКЕН_ВІД_BOTFATHER")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-6"

REVERSED_CHANCE = 0.30 # ймовірність перевернутої карти

# --- Ціни в Telegram Stars (XTR) -----------------------------------------
# Підключаються через @BotFather без ФОП/еквайрингу.
STARS_PRICE_DECISION = 15
STARS_PRICE_CELTIC = 40

CELTIC_CROSS_POSITIONS = {
"uk": ["Суть ситуації", "Що заважає/допомагає", "Свідома мета", "Коріння, минуле",
"Найближче майбутнє", "Підсвідомі впливи", "Твоя позиція", "Вплив оточення",
"Надії та страхи", "Підсумок"],
"en": ["Core of the situation", "What helps/hinders", "Conscious goal", "Roots, past",
"Near future", "Subconscious influences", "Your position", "Environment's influence",
"Hopes and fears", "Outcome"],
"es": ["Esencia de la situación", "Qué ayuda/dificulta", "Meta consciente", "Raíces, pasado",
"Futuro cercano", "Influencias subconscientes", "Tu posición", "Influencia del entorno",
"Esperanzas y miedos", "Resultado"],
}

SPREAD3_POSITIONS = {
"uk": ["Минуле", "Теперішнє", "Майбутнє"],
"en": ["Past", "Present", "Future"],
"es": ["Pasado", "Presente", "Futuro"],
}

LOVE_POSITIONS = {
"uk": ["Твої почуття", "Почуття партнера", "Куди рухаються стосунки"],
"en": ["Your feelings", "Partner's feelings", "Where the relationship is heading"],
"es": ["Tus sentimientos", "Sentimientos de la pareja", "Hacia dónde va la relación"],
}

DECISION_POSITIONS = {
"uk": ["Суть ситуації", "Що варто врахувати", "Найкращий шлях дії"],
"en": ["Core of the situation", "What to consider", "Best course of action"],
"es": ["Esencia de la situación", "Qué considerar", "Mejor curso de acción"],
}

SPREAD_TITLES = {
"uk": {"spread3": "Минуле · Теперішнє · Майбутнє", "love": "Розклад на стосунки",
"decision": "Розклад для рішення", "celtic": "Кельтський хрест"},
"en": {"spread3": "Past · Present · Future", "love": "Relationship Spread",
"decision": "Decision Spread", "celtic": "Celtic Cross"},
"es": {"spread3": "Pasado · Presente · Futuro", "love": "Tirada de Pareja",
"decision": "Tirada de Decisión", "celtic": "Cruz Celta"},
}

UI_TEXT = {
"uk": {
"start": ("🔮 Вітаю у <b>«Карти й Шлях»</b>!\n\n"
"Команди:\n"
"/lang — обрати мову (укр/eng/esp)\n"
"/card — безкоштовна карта дня\n"
"/spread3 — розклад «Минуле · Теперішнє · Майбутнє»\n"
"/love — розклад на стосунки\n"
"/decision — платний розклад для рішення\n"
"/celtic — платний Кельтський хрест (10 карт)"),
"card_of_day": "✨ Твоя карта дня:",
"lang_set": "Мову встановлено: українська 🇺🇦",
},
"en": {
"start": ("🔮 Welcome to <b>«Cards & Path»</b>!\n\n"
"Commands:\n"
"/lang — choose language (UA/EN/ES)\n"
"/card — free card of the day\n"
"/spread3 — «Past · Present · Future» spread\n"
"/love — relationship spread\n"
"/decision — paid decision-making spread\n"
"/celtic — paid Celtic Cross (10 cards)"),
"card_of_day": "✨ Your card of the day:",
"lang_set": "Language set: English 🇬🇧",
},
"es": {
"start": ("🔮 ¡Bienvenido a <b>«Cartas y Camino»</b>!\n\n"
"Comandos:\n"
"/lang — elegir idioma (UA/EN/ES)\n"
"/card — carta del día gratis\n"
"/spread3 — tirada «Pasado · Presente · Futuro»\n"
"/love — tirada de pareja\n"
"/decision — tirada de decisión (de pago)\n"
"/celtic — Cruz Celta de pago (10 cartas)"),
"card_of_day": "✨ Tu carta del día:",
"lang_set": "Idioma configurado: Español 🇪🇸",
},
}

CHOOSE_LANG_TEXT = "Обери мову / Choose language / Elige idioma:\n\n/lang_uk — 🇺🇦\n/lang_en — 🇬🇧\n/lang_es — 🇪🇸"

# user_id -> мова ("uk" / "en" / "es"). Для MVP — в пам'яті процесу.
# Для продакшну варто зберігати в SQLite, щоб не губилось при рестарті бота.
user_lang: dict[int, str] = {}


def get_lang(user_id: int) -> str:
 return user_lang.get(user_id, "uk")


def draw_cards(n: int):
"""Витягнути n унікальних карт з повної колоди (78 карт) з орієнтацією."""
chosen = random.sample(FULL_DECK, n)
return [(card, random.random() < REVERSED_CHANCE) for card in chosen]


async def ai_interpret(card_name_uk: str, reversed_: bool, position: str, lang: str) -> str:
"""
Генерує трактування карти через Claude API мовою lang.
Якщо ключ не заданий або стався збій API — падає назад на статичний
текст з cards_data.py, щоб бот ніколи не "зламався" через AI-провайдера.
"""
lang_names = {"uk": "українською", "en": "in English", "es": "en español"}
orientation_uk = "перевернута" if reversed_ else "пряма"
card = next(c for c in FULL_DECK if c["name"] == card_name_uk)
fallback_text = card["reversed"] if reversed_ else card["upright"]

if not ANTHROPIC_API_KEY:
return fallback_text

prompt = (
f"Ти — досвідчений таролог. Карта: {card_name_uk} ({orientation_uk} позиція). "
f"Позиція в розкладі: «{position}». "
f"Дай коротке (2-3 речення), тепле, професійне трактування "
f"{lang_names.get(lang, 'українською')}. Без вступних фраз, одразу суть."
)

try:
async with aiohttp.ClientSession() as session:
async with session.post(
"https://api.anthropic.com/v1/messages",
headers={
"x-api-key": ANTHROPIC_API_KEY,
"anthropic-version": "2023-06-01",
"content-type": "application/json",
},
json={
"model": ANTHROPIC_MODEL,
"max_tokens": 200,
"messages": [{"role": "user", "content": prompt}],
},
timeout=aiohttp.ClientTimeout(total=15),
) as resp:
data = await resp.json()
return data["content"][0]["text"].strip()
except Exception as e:
logging.warning(f"AI interpretation failed, falling back to static text: {e}")
return fallback_text


async def format_card_ai(card: dict, reversed_: bool, position: str, lang: str) -> str:
orientation_emoji = "🔻" if reversed_ else "✨"
text = await ai_interpret(card["name"], reversed_, position, lang)
return f"🃏 <b>{card['name']}</b> {orientation_emoji}\n{text}"


bot = Bot(token=API_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_handler(message: Message):
lang = get_lang(message.from_user.id)
await message.answer(UI_TEXT[lang]["start"], parse_mode="HTML")


@dp.message(Command("lang"))
async def lang_handler(message: Message):
await message.answer(CHOOSE_LANG_TEXT)


@dp.message(Command("lang_uk"))
async def set_lang_uk(message: Message):
user_lang[message.from_user.id] = "uk"
await message.answer(UI_TEXT["uk"]["lang_set"])


@dp.message(Command("lang_en"))
async def set_lang_en(message: Message):
user_lang[message.from_user.id] = "en"
await message.answer(UI_TEXT["en"]["lang_set"])


@dp.message(Command("lang_es"))
async def set_lang_es(message: Message):
user_lang[message.from_user.id] = "es"
await message.answer(UI_TEXT["es"]["lang_set"])


@dp.message(Command("card"))
async def card_of_day_handler(message: Message):
lang = get_lang(message.from_user.id)
card, rev = draw_cards(1)[0]
card_text = await format_card_ai(card, rev, UI_TEXT[lang]["card_of_day"], lang)
await message.answer(f"{UI_TEXT[lang]['card_of_day']}\n\n{card_text}", parse_mode="HTML")


async def send_named_spread(message: Message, title: str, positions: list[str], lang: str):
cards = draw_cards(len(positions))
parts = [f"🔮 <b>{title}</b>\n"]
for pos, (card, rev) in zip(positions, cards):
card_text = await format_card_ai(card, rev, pos, lang)
parts.append(f"<i>{pos}</i>\n{card_text}\n")
await message.answer("\n".join(parts), parse_mode="HTML")


@dp.message(Command("spread3"))
async def spread3_handler(message: Message):
lang = get_lang(message.from_user.id)
await send_named_spread(message, SPREAD_TITLES[lang]["spread3"], SPREAD3_POSITIONS[lang], lang)


@dp.message(Command("love"))
async def love_handler(message: Message):
lang = get_lang(message.from_user.id)
await send_named_spread(message, SPREAD_TITLES[lang]["love"], LOVE_POSITIONS[lang], lang)


# --- Платні розклади через Telegram Stars --------------------------------

@dp.message(Command("decision"))
async def decision_invoice_handler(message: Message):
lang = get_lang(message.from_user.id)
desc = "AI-трактування, 3 карти" if lang == "uk" else "AI interpretation, 3 cards"
await bot.send_invoice(
chat_id=message.chat.id,
title=SPREAD_TITLES[lang]["decision"],
description=desc,
payload="decision_spread",
provider_token="", # порожній рядок — ознака оплати саме через Stars
currency="XTR",
prices=[LabeledPrice(label=SPREAD_TITLES[lang]["decision"], amount=STARS_PRICE_DECISION)],
)


@dp.message(Command("celtic"))
async def celtic_invoice_handler(message: Message):
lang = get_lang(message.from_user.id)
desc = "AI-трактування, 10 карт" if lang == "uk" else "AI interpretation, 10 cards"
await bot.send_invoice(
chat_id=message.chat.id,
title=SPREAD_TITLES[lang]["celtic"],
description=desc,
payload="celtic_spread",
provider_token="",
currency="XTR",
prices=[LabeledPrice(label=SPREAD_TITLES[lang]["celtic"], amount=STARS_PRICE_CELTIC)],
)


@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
# Тут можна додати перевірки (напр. ліміти зловживань), для MVP підтверджуємо завжди
await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
lang = get_lang(message.from_user.id)
payload = message.successful_payment.invoice_payload

if payload == "decision_spread":
await send_named_spread(message, SPREAD_TITLES[lang]["decision"], DECISION_POSITIONS[lang], lang)
elif payload == "celtic_spread":
await send_named_spread(message, SPREAD_TITLES[lang]["celtic"], CELTIC_CROSS_POSITIONS[lang], lang)


async def main():
await dp.start_polling(bot)


if __name__ == "__main__":
asyncio.run(main())
