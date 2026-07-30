# -*- coding: utf-8 -*-
import re

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database
from data import CRABS, INTRO_TEXT, HELP_PAGES, PROMO_CODES
from keyboards import intro_kb, crab_choice_kb, main_menu_kb, help_pagination_kb
from states import Nav

router = Router()

NAME_TO_CRAB = {c["name"]: cid for cid, c in CRABS.items()}

_SAFE_NICK = re.compile(r"^[a-zA-Zа-яА-ЯёЁ0-9 _\-]{3,16}$")


def _safe_default_nickname(user_id, username, first_name):
    candidate = (username or first_name or "").strip()
    if _SAFE_NICK.match(candidate):
        return candidate
    return f"Краб{user_id % 100000}"


async def _try_apply_promo_from_payload(user_id, payload):
    """payload — это всё, что после '/start ' (диплинк-параметр). Промокоды
    оформляются как 'promo_КОД' — если формат не совпал, просто ничего не
    делаем (это обычный /start без промокода). Возвращает строку для показа
    игроку или None, если промокода не было вовсе."""
    if not payload or not payload.startswith("promo_"):
        return None
    code = payload[len("promo_"):].upper()
    promo = PROMO_CODES.get(code)
    if not promo:
        return "🎟️ Такого промокода не существует (возможно, устарел)."

    gold = promo.get("gold", 0)
    dna = promo.get("dna_points", 0)
    shells = promo.get("nautilus_shells", 0)
    boost = bool(promo.get("permanent_boost", False))
    applied = await database.run_async(
        database.try_redeem_promo, user_id, code, gold, dna, shells, boost
    )
    if not applied:
        return "🎟️ Этот промокод ты уже активировал раньше — второй раз награда не начисляется."

    reward_parts = []
    if gold:
        reward_parts.append(f"+{gold} 💰")
    if dna:
        reward_parts.append(f"+{dna} 🧬")
    if shells:
        reward_parts.append(f"+{shells} 🐚")
    if boost:
        reward_parts.append("🌟 Вечный прилив (+15% к золоту/ДНК навсегда)")
    reward_txt = f" ({', '.join(reward_parts)})" if reward_parts else ""
    return f"{promo.get('text', '🎁 Промокод активирован!')}{reward_txt}"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
    user = await database.run_async(database.get_user, message.from_user.id)
    if not user:
        nickname = _safe_default_nickname(
            message.from_user.id, message.from_user.username, message.from_user.first_name
        )
        await database.run_async(database.create_user, message.from_user.id, nickname)
        user = await database.run_async(database.get_user, message.from_user.id)

    promo_text = await _try_apply_promo_from_payload(message.from_user.id, command.args)

    if user["crab_type"]:
        await state.set_state(Nav.main)
        text = "С возвращением на дно океана, краб! 🦀"
        if promo_text:
            text = f"{promo_text}\n\n{text}"
        await message.answer(text, reply_markup=main_menu_kb())
        return

    await state.clear()
    text = INTRO_TEXT
    if promo_text:
        text = f"{promo_text}\n\n{text}"
    await message.answer(text, reply_markup=intro_kb())


@router.message(F.text == "📖 Обучение")
async def show_tutorial(message: Message, state: FSMContext):
    cur = await state.get_state()
    if cur is not None:
        return
    title, text = HELP_PAGES[0]
    await message.answer(f"<b>{title}</b>\n\n{text}", reply_markup=help_pagination_kb(0, len(HELP_PAGES)))


@router.callback_query(StateFilter(None), F.data.startswith("help_page_"))
async def tutorial_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split("_")[-1])
    if not (0 <= page < len(HELP_PAGES)):
        await call.answer()
        return
    title, text = HELP_PAGES[page]
    await call.answer()
    await call.message.edit_text(
        f"<b>{title}</b>\n\n{text}", reply_markup=help_pagination_kb(page, len(HELP_PAGES))
    )


async def prompt_crab_choice(message: Message, state: FSMContext):
    """Показывает выбор краба — используется и при первом старте, и повторно
    после каждой линьки."""
    await state.set_state(Nav.choose_crab)
    text = "🦀 <b>Выбери краба:</b>\n\n" + "\n".join(
        f"{c['name']} — {c['desc']}" for c in CRABS.values()
    )
    await message.answer(text, reply_markup=crab_choice_kb())


@router.message(F.text == "▶️ Начать игру")
async def begin_game(message: Message, state: FSMContext):
    cur = await state.get_state()
    if cur is not None:
        return
    user = await database.run_async(database.get_user, message.from_user.id)
    if user and user["crab_type"]:
        await state.set_state(Nav.main)
        await message.answer("Продолжаем путь!", reply_markup=main_menu_kb())
        return

    await prompt_crab_choice(message, state)


@router.message(Nav.choose_crab, F.text.in_(NAME_TO_CRAB.keys()))
async def choose_crab(message: Message, state: FSMContext):
    crab_id = NAME_TO_CRAB[message.text]
    user = await database.run_async(database.get_user, message.from_user.id)
    is_remolt = bool(user and user["molts"] > 0)
    await database.run_async(
        database.update_user,
        message.from_user.id,
        crab_type=crab_id,
        cur_hp=CRABS[crab_id]["max_hp"],
    )
    await state.set_state(Nav.main)
    text = (
        "🦀 Новый панцирь, новая жизнь! Можешь продолжать путь."
        if is_remolt else
        "🌊 Путешествие начинается! Кнопки внизу экрана — вся игра."
    )
    await message.answer(text, reply_markup=main_menu_kb())
