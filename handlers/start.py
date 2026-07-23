# -*- coding: utf-8 -*-
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

import database
from data import CRABS, SHORES, INTRO_TEXT, HELP_TEXT
from keyboards import intro_kb, crab_choice_kb, shore_choice_kb, main_menu_kb
from states import Nav

router = Router()

NAME_TO_CRAB = {c["name"]: cid for cid, c in CRABS.items()}
NAME_TO_SHORE = {v: k for k, v in SHORES.items()}


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    if not user:
        database.create_user(message.from_user.id, message.from_user.username or message.from_user.first_name)
        user = database.get_user(message.from_user.id)

    if user["crab_type"] and user["shore"]:
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
    await message.answer(HELP_TEXT, reply_markup=intro_kb())


@router.message(F.text == "▶️ Начать игру")
async def begin_game(message: Message, state: FSMContext):
    cur = await state.get_state()
    if cur is not None:
        return
    user = database.get_user(message.from_user.id)
    if user and user["crab_type"] and user["shore"]:
        await state.set_state(Nav.main)
        await message.answer("Продолжаем путь!", reply_markup=main_menu_kb())
        return

    await state.set_state(Nav.choose_crab)
    text = "🦀 <b>Выбери своего краба:</b>\n\n"
    for cid, c in CRABS.items():
        text += (
            f"{c['name']}\n{c['desc']}\n"
            f"Урон {c['damage']} | Уклонение {c['evasion']}% | Удача {c['luck']}% | "
            f"Крит.шанс {c['crit_chance']}% | Крит.урон {c['crit_damage']}% | Прочность {c['max_hp']}\n\n"
        )
    await message.answer(text, reply_markup=crab_choice_kb())


@router.message(Nav.choose_crab, F.text.in_(NAME_TO_CRAB.keys()))
async def choose_crab(message: Message, state: FSMContext):
    crab_id = NAME_TO_CRAB[message.text]
    database.update_user(
        message.from_user.id,
        crab_type=crab_id,
        cur_hp=CRABS[crab_id]["max_hp"],
    )
    await state.set_state(Nav.choose_shore)
    await message.answer(
        "Отличный выбор! Теперь выбери берег, с которого начнётся твоё путешествие:",
        reply_markup=shore_choice_kb(),
    )


@router.message(Nav.choose_shore, F.text.in_(NAME_TO_SHORE.keys()))
async def choose_shore(message: Message, state: FSMContext):
    shore_id = NAME_TO_SHORE[message.text]
    database.update_user(message.from_user.id, shore=shore_id)
    await state.set_state(Nav.main)
    await message.answer(
        "🌊 Путешествие начинается! Используй кнопки внизу экрана, чтобы играть.",
        reply_markup=main_menu_kb(),
    )
