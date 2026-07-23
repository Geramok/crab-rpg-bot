# -*- coding: utf-8 -*-
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import database
from data import MUTATION_SLOTS
from game_logic import molt_required_level, dna_points_for_molt, mutation_cost
from keyboards import mutations_root_kb, kb, BACK
from states import Nav

router = Router()


def _molt_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, сбросить уровень", callback_data="molt_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="molt_cancel"),
    ]])


@router.message(Nav.mutations_root, F.text == "🧬 Линька")
async def molt_request(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    required = molt_required_level(user["molts"])
    if user["crab_level"] < required:
        await message.answer(
            f"Линька доступна с {required} уровня краба (это твоя {user['molts'] + 1}-я линька — "
            f"с каждой следующей линькой требуемый уровень растёт).\n"
            f"Твой текущий уровень: {user['crab_level']}.",
            reply_markup=mutations_root_kb(),
        )
        return

    gain = dna_points_for_molt(user["molts"], user["crab_level"])
    over = user["crab_level"] - required
    bonus_txt = f" (в т.ч. +{round(over * 0.4)} за {over} уровней сверх минимума)" if over > 0 else ""
    await message.answer(
        f"⚠️ Линька сбросит твой уровень краба ({user['crab_level']} → 1) и всё золото ({user['gold']} 💰).\n"
        f"Взамен ты получишь <b>{gain}</b> очков ДНК 🧬{bonus_txt} "
        f"(мутации и уже накопленные очки сохранятся).\n\n"
        f"Провести линьку?",
        reply_markup=_molt_confirm_kb(),
    )


@router.callback_query(F.data == "molt_confirm")
async def molt_confirm(call: CallbackQuery, state: FSMContext):
    user = database.get_user(call.from_user.id)
    required = molt_required_level(user["molts"])
    if user["crab_level"] < required:
        await call.answer("Условие для линьки больше не выполняется.", show_alert=True)
        return

    gain = dna_points_for_molt(user["molts"], user["crab_level"])
    database.update_user(
        call.from_user.id,
        crab_level=1,
        gold=0,
        dna_points=user["dna_points"] + gain,
        molts=user["molts"] + 1,
        total_dna_earned=user["total_dna_earned"] + gain,
    )
    next_required = molt_required_level(user["molts"] + 1)
    await call.message.edit_text(
        f"🧬 Линька прошла успешно! Получено {gain} очков ДНК.\n"
        f"Всего линек: {user['molts'] + 1}. Следующая линька потребует {next_required} уровня."
    )
    await call.answer()
    await call.message.answer("Что дальше?", reply_markup=mutations_root_kb())


@router.callback_query(F.data == "molt_cancel")
async def molt_cancel(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Линька отменена.")
    await call.answer()
    await call.message.answer("Что дальше?", reply_markup=mutations_root_kb())


# ---------------- Магазин мутаций (пассивные способности) ----------------

def _mutations_shop_text_and_kb(user_id):
    user = database.get_user(user_id)
    mutations = database.get_mutations(user_id)
    total_levels = sum(m["level"] for m in mutations.values())

    text = f"🧪 <b>Мутации — части тела с пассивными навыками</b>\nОчки ДНК: {user['dna_points']} 🧬\n\n"
    buttons = []
    for slot, info in MUTATION_SLOTS.items():
        m = mutations.get(slot, {"level": 0, "equipped": 0})
        cost = mutation_cost(slot, m["level"] + 1, total_levels)
        equipped_txt = "✅ надета" if m["equipped"] else "выключена"
        cur_power = info["per_level"] * m["level"]
        text += (
            f"{info['name']} — «{info['ability_name']}» (ур. {m['level']}, {equipped_txt})\n"
            f"{info['desc']}\n"
            f"Текущая сила: {cur_power:.1f}%. Следующий уровень: {cost} 🧬\n\n"
        )
        buttons.append([
            InlineKeyboardButton(text=f"⬆️ Улучшить «{info['ability_name']}» ({cost} 🧬)", callback_data=f"buy_{slot}")
        ])
        if m["level"] > 0:
            toggle_txt = "Снять" if m["equipped"] else "Надеть"
            buttons.append([
                InlineKeyboardButton(text=f"{toggle_txt} {info['name']}", callback_data=f"toggle_{slot}")
            ])
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Nav.mutations_root, F.text == "🧪 Мутации")
async def open_mutations_shop(message: Message, state: FSMContext):
    await state.set_state(Nav.mutations_shop)
    text, ikb = _mutations_shop_text_and_kb(message.from_user.id)
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("Выбери действие:", reply_markup=ikb)


@router.callback_query(F.data.startswith("buy_"))
async def buy_mutation(call: CallbackQuery, state: FSMContext):
    slot = call.data.split("_", 1)[1]
    if slot not in MUTATION_SLOTS:
        await call.answer()
        return
    user = database.get_user(call.from_user.id)
    mutations = database.get_mutations(call.from_user.id)
    total_levels = sum(m["level"] for m in mutations.values())
    m = mutations.get(slot, {"level": 0, "equipped": 0})
    cost = mutation_cost(slot, m["level"] + 1, total_levels)

    if user["dna_points"] < cost:
        await call.answer(f"Не хватает очков ДНК! Нужно {cost}.", show_alert=True)
        return

    database.update_user(call.from_user.id, dna_points=user["dna_points"] - cost)
    database.set_mutation(call.from_user.id, slot, level=m["level"] + 1)
    await call.answer("Способность улучшена!")

    text, ikb = _mutations_shop_text_and_kb(call.from_user.id)
    await call.message.edit_text(text, reply_markup=ikb)


@router.callback_query(F.data.startswith("toggle_"))
async def toggle_mutation(call: CallbackQuery, state: FSMContext):
    slot = call.data.split("_", 1)[1]
    if slot not in MUTATION_SLOTS:
        await call.answer()
        return
    mutations = database.get_mutations(call.from_user.id)
    m = mutations.get(slot, {"level": 0, "equipped": 0})
    if m["level"] <= 0:
        await call.answer("Сначала купи эту способность.", show_alert=True)
        return
    database.set_mutation(call.from_user.id, slot, equipped=not m["equipped"])
    await call.answer("Готово!")

    text, ikb = _mutations_shop_text_and_kb(call.from_user.id)
    await call.message.edit_text(text, reply_markup=ikb)
