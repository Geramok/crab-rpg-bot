# -*- coding: utf-8 -*-
from aiogram import Router, F
from aiogram.types import (
    Message, PreCheckoutQuery, LabeledPrice,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

import database
from data import SHOP_ITEMS
from game_logic import shop_gold_reward, shop_dna_reward
from keyboards import kb, BACK
from states import Nav

router = Router()


def _preview_reward(user_id, item):
    """Предпросмотр награды ПРЯМО СЕЙЧАС — это ориентир, итоговая сумма на
    момент оплаты может немного отличаться, если прогресс успеет измениться."""
    user = database.get_user(user_id)
    if item["reward_type"] == "gold":
        amount = shop_gold_reward(user, item["levels_worth"])
        return f"{amount} золота 💰"
    mutations = database.get_mutations(user_id)
    amount = shop_dna_reward(mutations, item["mutation_upgrades_worth"])
    return f"{amount} очков ДНК 🧬"


def _shop_kb():
    buttons = []
    for key, item in SHOP_ITEMS.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{item['title']} — {item['stars']} ⭐",
                callback_data=f"buy_star_{key}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def open_shop(message: Message, state: FSMContext):
    await state.set_state(Nav.shop)
    user = database.get_user(message.from_user.id)
    text = (
        "🛍️ <b>Магазин за Telegram Stars</b>\n\n"
        f"🐚 Раковин наутилуса: {user['nautilus_shells']}\n\n"
        "Награда считается в процентах от твоего ТЕКУЩЕГО прогресса — эти "
        "товары одинаково полезны что в начале игры, что на высоких уровнях.\n\n"
    )
    for item in SHOP_ITEMS.values():
        preview = _preview_reward(message.from_user.id, item)
        text += (
            f"{item['title']} — {item['description']}\n"
            f"Прямо сейчас это ≈{preview}. Цена: {item['stars']} ⭐\n\n"
        )
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("Выбери, что купить:", reply_markup=_shop_kb())


@router.callback_query(F.data.startswith("buy_star_"))
async def buy_star_item(call, state: FSMContext):
    key = call.data.split("buy_star_", 1)[1]
    item = SHOP_ITEMS.get(key)
    if not item:
        await call.answer()
        return

    preview = _preview_reward(call.from_user.id, item)
    prices = [LabeledPrice(label=item["title"], amount=item["stars"])]
    await call.message.answer_invoice(
        title=item["title"],
        description=f"{item['description']} Сейчас это ≈{preview}.",
        payload=f"shop:{key}",
        provider_token="",  # для Telegram Stars provider_token оставляем пустым
        currency="XTR",
        prices=prices,
    )
    await call.answer()


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
