# -*- coding: utf-8 -*-
import re

from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database
from data import CRABS, INTRO_TEXT, HELP_PAGES
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


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    if not user:
        nickname = _safe_default_nickname(
            message.from_user.id, message.from_user.username, message.from_user.first_name
        )
        database.create_user(message.from_user.id, nickname)
        user = database.get_user(message.from_user.id)

    if user["crab_type"]:
        await state.set_state(Nav.main)
        await message.answer("С возвращением на дно океана, краб! 🦀", reply_markup=main_menu_kb())
        return

    await state.clear()
    await message.answer(INTRO_TEXT, reply_markup=intro_kb())


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
    user = database.get_user(message.from_user.id)
    if user and user["crab_type"]:
        await state.set_state(Nav.main)
        await message.answer("Продолжаем путь!", reply_markup=main_menu_kb())
        return

    await prompt_crab_choice(message, state)


@router.message(Nav.choose_crab, F.text.in_(NAME_TO_CRAB.keys()))
async def choose_crab(message: Message, state: FSMContext):
    crab_id = NAME_TO_CRAB[message.text]
    user = database.get_user(message.from_user.id)
    is_remolt = bool(user and user["molts"] > 0)
    database.update_user(
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
