# -*- coding: utf-8 -*-
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from keyboards import (
    BACK, main_menu_kb, hunt_kb, mutations_root_kb, menu_root_kb,
    profile_kb, misc_kb,
)
from states import Nav, PARENT_STATE

router = Router()


@router.message(Nav.main, F.text == "🗡️ На охоту")
async def open_hunt(message: Message, state: FSMContext):
    import database
    user = database.get_user(message.from_user.id)
    await state.set_state(Nav.hunt)
    await message.answer(
        f"🌊 Морское дно... Текущая позиция: {user['cur_meters']} м.\n"
        f"Лучший результат: {user['max_meters']} м.",
        reply_markup=hunt_kb(bool(user["in_hunt"])),
    )


@router.message(Nav.main, F.text == "🧬 Мутации")
async def open_mutations_root(message: Message, state: FSMContext):
    await state.set_state(Nav.mutations_root)
    await message.answer(
        "🧬 <b>Мутации</b>\n\n"
        "🧬 Линька — сбросить уровень краба и золото в обмен на очки ДНК.\n"
        "🧪 Мутации — потратить очки ДНК на постоянные улучшения.",
        reply_markup=mutations_root_kb(),
    )


@router.message(Nav.main, F.text == "📋 Меню")
async def open_menu_root(message: Message, state: FSMContext):
    await state.set_state(Nav.menu_root)
    await message.answer("📋 <b>Меню</b>", reply_markup=menu_root_kb())


@router.message(Nav.menu_root, F.text == "👤 Профиль")
async def open_profile(message: Message, state: FSMContext):
    from handlers.profile import show_profile
    await state.set_state(Nav.profile)
    await show_profile(message)


@router.message(Nav.menu_root, F.text == "📊 Характеристики")
async def open_characteristics(message: Message, state: FSMContext):
    from handlers.profile import show_characteristics
    await state.set_state(Nav.characteristics)
    await show_characteristics(message)


@router.message(Nav.menu_root, F.text == "⛏️ Копать")
async def open_dig(message: Message, state: FSMContext):
    from handlers.dig import show_dig
    await state.set_state(Nav.dig)
    await show_dig(message)


@router.message(Nav.menu_root, F.text == "🎒 Инвентарь")
async def open_inventory(message: Message, state: FSMContext):
    from handlers.inventory import show_inventory
    await state.set_state(Nav.inventory)
    await show_inventory(message)


@router.message(Nav.menu_root, F.text == "🔧 Прочее")
async def open_misc(message: Message, state: FSMContext):
    await state.set_state(Nav.misc)
    await message.answer("🔧 <b>Прочее</b>", reply_markup=misc_kb())


# ---------------- Кнопка "Назад" (работает из любого состояния) ----------------

@router.message(F.text == BACK)
async def go_back(message: Message, state: FSMContext):
    cur = await state.get_state()
    parent = PARENT_STATE.get(cur, Nav.main)
    await state.set_state(parent)

    if parent == Nav.main:
        await message.answer("📋 Главное меню", reply_markup=main_menu_kb())
    elif parent == Nav.menu_root:
        await message.answer("📋 <b>Меню</b>", reply_markup=menu_root_kb())
    elif parent == Nav.mutations_root:
        await message.answer(
            "🧬 <b>Мутации</b>", reply_markup=mutations_root_kb()
        )
    elif parent == Nav.misc:
        await message.answer("🔧 <b>Прочее</b>", reply_markup=misc_kb())
    elif parent == Nav.profile:
        from handlers.profile import show_profile
        await show_profile(message)
    else:
        await message.answer("📋 Главное меню", reply_markup=main_menu_kb())
