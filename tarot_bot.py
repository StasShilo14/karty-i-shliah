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

import time

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from cards_data import FULL_DECK  # повна колода Таро — 78 карт (канонічні укр. назви)
from lenormand_data import LENORMAND_DECK  # колода Ленорман — 36 карт

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("TAROT_BOT_TOKEN", "ВСТАВ_СЮДИ_ТОКЕН_ВІД_BOTFATHER")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-6"

REVERSED_CHANCE = 0.30  # ймовірність перевернутої карти

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
           "decision": "Ясний Вибір — 3 карти", "celtic": "Кельтський Хрест — 10 карт",
           "lenormand": "Карта дня Ленорман"},
    "en": {"spread3": "Past · Present · Future", "love": "Relationship Spread",
           "decision": "Decision Spread", "celtic": "Celtic Cross",
           "lenormand": "Lenormand Card of the Day"},
    "es": {"spread3": "Pasado · Presente · Futuro", "love": "Tirada de Pareja",
           "decision": "Tirada de Decisión", "celtic": "Cruz Celta",
           "lenormand": "Carta del Día Lenormand"},
}

MENU_BUTTONS = {
    "uk": {"card": "🃏 Карта дня (Таро)", "spread3": "🔮 Минуле · Теперішнє · Майбутнє",
           "love": "💞 Стосунки", "decision": "🎯 Ясний Вибір — 3 карти (15⭐)", "celtic": "✨ Кельтський Хрест — 10 карт (40⭐)",
           "lenormand": "🎴 Карта дня (Ленорман)", "lang": "🌐 Мова"},
    "en": {"card": "🃏 Card of the Day (Tarot)", "spread3": "🔮 Past · Present · Future",
           "love": "💞 Relationship", "decision": "🎯 Decision (15⭐)", "celtic": "✨ Celtic Cross (40⭐)",
           "lenormand": "🎴 Card of the Day (Lenormand)", "lang": "🌐 Language"},
    "es": {"card": "🃏 Carta del Día (Tarot)", "spread3": "🔮 Pasado · Presente · Futuro",
           "love": "💞 Pareja", "decision": "🎯 Decisión (15⭐)", "celtic": "✨ Cruz Celta (40⭐)",
           "lenormand": "🎴 Carta del Día (Lenormand)", "lang": "🌐 Idioma"},
}

UI_TEXT = {
    "uk": {
        "start": ("🔮 Вітаю у <b>«Карти й Шлях»</b>!\n\n"
                  "Обери дію в меню нижче 👇 або скористайся командами:\n"
                  "/lang — обрати мову (укр/eng/esp)\n"
                  "/card — безкоштовна карта дня (Таро)\n"
                  "/lenormand — безкоштовна карта дня (Ленорман)\n"
                  "/spread3 — розклад «Минуле · Теперішнє · Майбутнє»\n"
                  "/love — розклад на стосунки\n"
                  "/decision — 🎯 Ясний Вибір: розклад на 3 карти для складного рішення (15⭐)\n"
                  "/celtic — ✨ Кельтський Хрест: розклад на 10 карт, повна картина ситуації (40⭐)"),
        "card_of_day": "✨ Твоя карта дня:",
        "lang_set": "Мову встановлено: українська 🇺🇦",
    },
    "en": {
        "start": ("🔮 Welcome to <b>«Cards & Path»</b>!\n\n"
                  "Choose an action from the menu below 👇 or use commands:\n"
                  "/lang — choose language (UA/EN/ES)\n"
                  "/card — free card of the day (Tarot)\n"
                  "/lenormand — free card of the day (Lenormand)\n"
                  "/spread3 — «Past · Present · Future» spread\n"
                  "/love — relationship spread\n"
                  "/decision — paid decision-making spread\n"
                  "/celtic — paid Celtic Cross (10 cards)"),
        "card_of_day": "✨ Your card of the day:",
        "lang_set": "Language set: English 🇬🇧",
    },
    "es": {
        "start": ("🔮 ¡Bienvenido a <b>«Cartas y Camino»</b>!\n\n"
                  "Elige una acción en el menú de abajo 👇 o usa comandos:\n"
                  "/lang — elegir idioma (UA/EN/ES)\n"
                  "/card — carta del día gratis (Tarot)\n"
                  "/lenormand — carta del día gratis (Lenormand)\n"
                  "/spread3 — tirada «Pasado · Presente · Futuro»\n"
                  "/love — tirada de pareja\n"
                  "/decision — tirada de decisión (de pago)\n"
                  "/celtic — Cruz Celta de pago (10 cartas)"),
        "card_of_day": "✨ Tu carta del día:",
        "lang_set": "Idioma configurado: Español 🇪🇸",
    },
}

CHOOSE_LANG_TEXT = "Обери мову / Choose language / Elige idioma:\n\n/lang_uk — 🇺🇦\n/lang_en — 🇬🇧\n/lang_es — 🇪🇸"


def build_main_menu(lang: str) -> InlineKeyboardMarkup:
    """Будує inline-меню з кнопками замість того, щоб людина набирала команди вручну."""
    b = MENU_BUTTONS[lang]
    rows = [
        [InlineKeyboardButton(text=b["card"], callback_data="menu_card")],
        [InlineKeyboardButton(text=b["lenormand"], callback_data="menu_lenormand")],
        [InlineKeyboardButton(text=b["spread3"], callback_data="menu_spread3")],
        [InlineKeyboardButton(text=b["love"], callback_data="menu_love")],
        [InlineKeyboardButton(text=b["decision"], callback_data="menu_decision")],
        [InlineKeyboardButton(text=b["celtic"], callback_data="menu_celtic")],
        [InlineKeyboardButton(text=b["lang"], callback_data="menu_lang")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# user_id -> мова ("uk" / "en" / "es"). Для MVP — в пам'яті процесу.
# Для продакшну варто зберігати в SQLite, щоб не губилось при рестарті бота.
user_lang: dict[int, str] = {}

# token -> активна сесія розкладу, що чекає на розкриття карт користувачем.
# Токен унікальний на кожен виклик /card, /spread3 і т.д. — так кілька
# розкладів одного юзера (або кількох юзерів) не конфліктують між собою.
# Структура: {"kind": "tarot"/"lenormand", "positions": [...], "cards": [...],
#             "lang": str, "revealed": set()}
pending_reveals: dict[str, dict] = {}


def get_lang(user_id: int) -> str:
    return user_lang.get(user_id, "uk")


def draw_cards(n: int):
    """Витягнути n унікальних карт з повної колоди Таро (78 карт) з орієнтацією."""
    chosen = random.sample(FULL_DECK, n)
    return [(card, random.random() < REVERSED_CHANCE) for card in chosen]


def draw_lenormand(n: int):
    """Витягнути n унікальних карт Ленорман. На відміну від Таро — без перевернутих позицій."""
    return random.sample(LENORMAND_DECK, n)


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


async def ai_interpret_lenormand(card_name: str, position: str, lang: str) -> str:
    """
    Генерує трактування карти Ленорман через Claude API. На відміну від Таро,
    тут немає перевернутих позицій — лише одне базове значення на картку.
    Так само падає назад на статичний текст, якщо AI недоступний.
    """
    lang_names = {"uk": "українською", "en": "in English", "es": "en español"}
    card = next(c for c in LENORMAND_DECK if c["name"] == card_name)
    fallback_text = card["meaning"]

    if not ANTHROPIC_API_KEY:
        return fallback_text

    prompt = (
        f"Ти — досвідчений практик системи Ленорман. Карта: {card_name}. "
        f"Позиція в розкладі: «{position}». "
        f"Дай коротке (2-3 речення), тепле, професійне тлумачення "
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
        logging.warning(f"Lenormand AI interpretation failed, falling back: {e}")
        return fallback_text


async def send_one_lenormand_card(message: Message, card: dict, position: str, lang: str):
    """Надсилає одну карту Ленорман: фото + AI-трактування (колода Dondorf, 36 карт)."""
    text = await ai_interpret_lenormand(card["name"], position, lang)
    caption = f"🎴 <b>{card['name']}</b>\n{text}"
    image_path = card.get("image")
    if image_path and os.path.isfile(image_path):
        await message.answer_photo(photo=FSInputFile(image_path), caption=caption, parse_mode="HTML")
    else:
        await message.answer(caption, parse_mode="HTML")


async def send_one_card(message: Message, card: dict, reversed_: bool, position: str, lang: str):
    """
    Надсилає одну карту: з фото, якщо воно є в cards_data.py (зараз — усі 22
    Старші Аркани), або звичайним текстовим повідомленням, якщо фото ще нема
    (Молодші Аркани — додамо пізніше).
    """
    caption = await format_card_ai(card, reversed_, position, lang)
    image_url = card.get("image")
    if image_url:
        # Telegram caption ліміт — 1024 символи; наш AI-текст короткий, тому вкладається
        await message.answer_photo(photo=image_url, caption=caption, parse_mode="HTML")
    else:
        await message.answer(caption, parse_mode="HTML")


bot = Bot(token=API_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_handler(message: Message):
    lang = get_lang(message.from_user.id)
    await message.answer(UI_TEXT[lang]["start"], parse_mode="HTML", reply_markup=build_main_menu(lang))


@dp.message(Command("menu"))
async def menu_handler(message: Message):
    lang = get_lang(message.from_user.id)
    await message.answer("🔮", reply_markup=build_main_menu(lang))


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
    await start_selection(message, message.from_user.id, "tarot", [UI_TEXT[lang]["card_of_day"]], lang)


@dp.message(Command("lenormand"))
async def lenormand_card_handler(message: Message):
    lang = get_lang(message.from_user.id)
    await start_selection(message, message.from_user.id, "lenormand",
                           [SPREAD_TITLES[lang]["lenormand"]], lang)


REVEAL_LABEL = {
    "uk": "🂠 Перевернути карту",
    "en": "🂠 Reveal the card",
    "es": "🂠 Revelar la carta",
}


async def start_selection(target: Message, user_id: int, kind: str,
                           positions: list[str], lang: str, title: str | None = None):
    """
    Запускає розклад прямо в чаті — без Mini App і без переходу на сторонній
    сайт. Карти вже витягнуті заздалегідь; для кожної позиції надсилається
    окреме повідомлення-«карта сорочкою вгору» з кнопкою «Перевернути».
    Натискання кнопки редагує саме це повідомлення й одразу показує карту.
    """
    if kind == "tarot":
        cards = draw_cards(len(positions))  # [(card, reversed), ...]
    else:
        cards = [(card, False) for card in draw_lenormand(len(positions))]

    token = f"{user_id}_{int(time.time() * 1000)}"
    pending_reveals[token] = {
        "kind": kind, "positions": positions, "cards": cards,
        "lang": lang, "revealed": set(),
    }

    if title:
        await target.answer(f"🔮 <b>{title}</b>", parse_mode="HTML")

    for idx, position in enumerate(positions):
        label = f"<i>{position}</i>" if len(positions) > 1 else position
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=REVEAL_LABEL[lang], callback_data=f"reveal:{token}:{idx}")
        ]])
        await target.answer(f"🂠 {label}", parse_mode="HTML", reply_markup=kb)


@dp.callback_query(F.data.startswith("reveal:"))
async def cb_reveal(callback: CallbackQuery):
    """Розкриває одну карту в чаті одразу після натискання кнопки під нею."""
    try:
        _, token, idx_str = callback.data.split(":", 2)
        idx = int(idx_str)
    except Exception:
        await callback.answer()
        return

    session = pending_reveals.get(token)
    if not session or idx in session["revealed"]:
        await callback.answer()
        return
    session["revealed"].add(idx)

    lang = session["lang"]
    position = session["positions"][idx]
    card, rev = session["cards"][idx]

    # Прибираємо кнопку з повідомлення-заглушки, щоб не можна було натиснути двічі
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if session["kind"] == "tarot":
        await send_one_card(callback.message, card, rev, position, lang)
    else:
        await send_one_lenormand_card(callback.message, card, position, lang)

    if len(session["revealed"]) >= len(session["positions"]):
        pending_reveals.pop(token, None)

    await callback.answer()


@dp.message(Command("spread3"))
async def spread3_handler(message: Message):
    lang = get_lang(message.from_user.id)
    await start_selection(message, message.from_user.id, "tarot",
                           SPREAD3_POSITIONS[lang], lang, title=SPREAD_TITLES[lang]["spread3"])


@dp.message(Command("love"))
async def love_handler(message: Message):
    lang = get_lang(message.from_user.id)
    await start_selection(message, message.from_user.id, "tarot",
                           LOVE_POSITIONS[lang], lang, title=SPREAD_TITLES[lang]["love"])


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
        provider_token="",  # порожній рядок — ознака оплати саме через Stars
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
        await start_selection(message, message.from_user.id, "tarot",
                               DECISION_POSITIONS[lang], lang, title=SPREAD_TITLES[lang]["decision"])
    elif payload == "celtic_spread":
        await start_selection(message, message.from_user.id, "tarot",
                               CELTIC_CROSS_POSITIONS[lang], lang, title=SPREAD_TITLES[lang]["celtic"])


@dp.callback_query(F.data == "menu_card")
async def cb_card(callback: CallbackQuery):
    lang = get_lang(callback.from_user.id)
    await start_selection(callback.message, callback.from_user.id, "tarot",
                           [UI_TEXT[lang]["card_of_day"]], lang)
    await callback.answer()


@dp.callback_query(F.data == "menu_lenormand")
async def cb_lenormand(callback: CallbackQuery):
    lang = get_lang(callback.from_user.id)
    await start_selection(callback.message, callback.from_user.id, "lenormand",
                           [SPREAD_TITLES[lang]["lenormand"]], lang)
    await callback.answer()


@dp.callback_query(F.data == "menu_spread3")
async def cb_spread3(callback: CallbackQuery):
    lang = get_lang(callback.from_user.id)
    await start_selection(callback.message, callback.from_user.id, "tarot",
                           SPREAD3_POSITIONS[lang], lang, title=SPREAD_TITLES[lang]["spread3"])
    await callback.answer()


@dp.callback_query(F.data == "menu_love")
async def cb_love(callback: CallbackQuery):
    lang = get_lang(callback.from_user.id)
    await start_selection(callback.message, callback.from_user.id, "tarot",
                           LOVE_POSITIONS[lang], lang, title=SPREAD_TITLES[lang]["love"])
    await callback.answer()


@dp.callback_query(F.data == "menu_decision")
async def cb_decision(callback: CallbackQuery):
    lang = get_lang(callback.from_user.id)
    desc = "AI-трактування, 3 карти" if lang == "uk" else "AI interpretation, 3 cards"
    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=SPREAD_TITLES[lang]["decision"],
        description=desc,
        payload="decision_spread",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=SPREAD_TITLES[lang]["decision"], amount=STARS_PRICE_DECISION)],
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_celtic")
async def cb_celtic(callback: CallbackQuery):
    lang = get_lang(callback.from_user.id)
    desc = "AI-трактування, 10 карт" if lang == "uk" else "AI interpretation, 10 cards"
    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=SPREAD_TITLES[lang]["celtic"],
        description=desc,
        payload="celtic_spread",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=SPREAD_TITLES[lang]["celtic"], amount=STARS_PRICE_CELTIC)],
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_lang")
async def cb_lang(callback: CallbackQuery):
    await callback.message.answer(CHOOSE_LANG_TEXT)
    await callback.answer()


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
