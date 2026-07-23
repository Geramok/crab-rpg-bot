# -*- coding: utf-8 -*-
from aiogram import Router, F
from aiogram.types import (
    Message, PreCheckoutQuery, LabeledPrice,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

import database
from data import SHOP_ITEMS, RESOURCES
from game_logic import shop_gold_reward, shop_dna_reward
from keyboards import kb, BACK
from states import Nav

router = Router()

SHELL_ITEMS = {
    "speed_dig": {"title": "⏩ Ускорить копание", "shells": 3},
    "resource_pack": {"title": "🎁 Набор ресурсов для крафта", "shells": 5},
}


def _preview_reward(user_id, item):
    user = database.get_user(user_id)
    if item["reward_type"] == "gold":
        amount = shop_gold_reward(user, item["levels_worth"])
        return f"{amount} золота 💰"
    if item["reward_type"] == "dna":
        mutations = database.get_mutations(user_id)
        amount = shop_dna_reward(mutations, item["mutation_upgrades_worth"])
        return f"{amount} очков ДНК 🧬"
    return "постоянный буст +15% к золоту и ДНК навсегда"


def _shop_kb():
    buttons = []
    for key, item in SHOP_ITEMS.items():
        buttons.append([InlineKeyboardButton(text=f"{item['title']} — {item['stars']} ⭐", callback_data=f"buy_star_{key}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _shell_shop_kb():
    buttons = [
        [InlineKeyboardButton(text=f"{item['title']} ({item['shells']} 🐚)", callback_data=f"buy_shell_{key}")]
        for key, item in SHELL_ITEMS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def open_shop(message: Message, state: FSMContext):
    await state.set_state(Nav.shop)
    user = database.get_user(message.from_user.id)
    text = (
        "🛍️ <b>Магазин за Telegram Stars</b>\n\n"
        f"🐚 Раковин наутилуса: {user['nautilus_shells']}\n\n"
        "Награда считается в процентах от твоего ТЕКУЩЕГО прогресса.\n\n"
    )
    if user["permanent_boost"]:
        text += "🌟 У тебя уже активен Вечный прилив (+15% навсегда).\n\n"
    for key, item in SHOP_ITEMS.items():
        if key == "eternal_tide" and user["permanent_boost"]:
            continue
        preview = _preview_reward(message.from_user.id, item)
        text += f"{item['title']} — {item['description']}\nСейчас это ≈{preview}. Цена: {item['stars']} ⭐\n\n"
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("За звёзды:", reply_markup=_shop_kb())

    text2 = (
        "🐚 <b>За раковины наутилуса</b> (их даёшь мифическими ивентами):\n\n"
        "⏩ Ускорить копание — мгновенно завершает текущее копание.\n"
        "🎁 Набор ресурсов для крафта — сразу немного каждого ресурса."
    )
    await message.answer(text2, reply_markup=_shell_shop_kb())


@router.callback_query(F.data.startswith("buy_star_"))
async def buy_star_item(call, state: FSMContext):
    key = call.data.split("buy_star_", 1)[1]
    item = SHOP_ITEMS.get(key)
    if not item:
        await call.answer()
        return
    if key == "eternal_tide":
        user = database.get_user(call.from_user.id)
        if user["permanent_boost"]:
            await call.answer("У тебя уже есть Вечный прилив!", show_alert=True)
            return

    preview = _preview_reward(call.from_user.id, item)
    prices = [LabeledPrice(label=item["title"], amount=item["stars"])]
    await call.message.answer_invoice(
        title=item["title"],
        description=f"{item['description']} Сейчас это ≈{preview}.",
        payload=f"shop:{key}",
        provider_token="",
        currency="XTR",
        prices=prices,
    )
    await call.answer()


@router.callback_query(F.data.startswith("buy_shell_"))
async def buy_shell_item(call):
    key = call.data.split("buy_shell_", 1)[1]
    item = SHELL_ITEMS.get(key)
    if not item:
        await call.answer()
        return
    user = database.get_user(call.from_user.id)
    if user["nautilus_shells"] < item["shells"]:
        await call.answer(f"Не хватает раковин! Нужно {item['shells']} 🐚.", show_alert=True)
        return

    if key == "speed_dig":
        if not user["dig_start_ts"]:
            await call.answer("Копание сейчас не идёт.", show_alert=True)
            return
        spent = database.try_spend(call.from_user.id, "nautilus_shells", item["shells"])
        if not spent:
            await call.answer("Не успел — попробуй снова.", show_alert=True)
            return
        import time
        database.update_user(call.from_user.id, dig_start_ts=int(time.time()) - (user["dig_duration_seconds"] or 3600))
        await call.answer("Копание завершено! Иди забирай добычу.", show_alert=True)
        return

    if key == "resource_pack":
        spent = database.try_spend(call.from_user.id, "nautilus_shells", item["shells"])
        if not spent:
            await call.answer("Не успел — попробуй снова.", show_alert=True)
            return
        for res_key in RESOURCES:
            database.add_resource(call.from_user.id, res_key, 2)
        await call.answer("Получено по 2 каждого ресурса!", show_alert=True)
        return


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    if not payload.startswith("shop:"):
        return
    key = payload.split("shop:", 1)[1]
    item = SHOP_ITEMS.get(key)
    if not item:
        return

    user = database.get_user(message.from_user.id)
    if item["reward_type"] == "gold":
        amount = shop_gold_reward(user, item["levels_worth"])
        database.update_user(
            message.from_user.id,
            gold=user["gold"] + amount,
            total_earned_gold=user["total_earned_gold"] + amount,
        )
        await message.answer(f"✅ Спасибо за покупку! Начислено {amount} золота 💰")
    elif item["reward_type"] == "dna":
        mutations = database.get_mutations(message.from_user.id)
        amount = shop_dna_reward(mutations, item["mutation_upgrades_worth"])
        database.update_user(
            message.from_user.id,
            dna_points=user["dna_points"] + amount,
            total_dna_earned=user["total_dna_earned"] + amount,
        )
        await message.answer(f"✅ Спасибо за покупку! Начислено {amount} очков ДНК 🧬")
    elif item["reward_type"] == "permanent_boost":
        database.update_user(message.from_user.id, permanent_boost=1)
        await message.answer("🌟 Вечный прилив активирован! Теперь +15% к золоту и ДНК навсегда.")
