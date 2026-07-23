# -*- coding: utf-8 -*-
from aiogram import Router, F
from aiogram.types import (
    Message, PreCheckoutQuery, LabeledPrice,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

import database
from data import SHOP_ITEMS
from keyboards import kb, BACK
from states import Nav

router = Router()


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
    )
    for item in SHOP_ITEMS.values():
        reward = f"{item['reward_amount']} золота 💰" if item["reward_type"] == "gold" else f"{item['reward_amount']} очков ДНК 🧬"
        text += f"{item['title']} — {item['description']}\nДаёт: {reward}. Цена: {item['stars']} ⭐\n\n"
    await message.answer(text, reply_markup=kb([BACK]))
    await message.answer("Выбери, что купить:", reply_markup=_shop_kb())


@router.callback_query(F.data.startswith("buy_star_"))
async def buy_star_item(call, state: FSMContext):
    key = call.data.split("buy_star_", 1)[1]
    item = SHOP_ITEMS.get(key)
    if not item:
        await call.answer()
        return

    prices = [LabeledPrice(label=item["title"], amount=item["stars"])]
    await call.message.answer_invoice(
        title=item["title"],
        description=item["description"],
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
        database.update_user(
            message.from_user.id,
            gold=user["gold"] + item["reward_amount"],
            total_earned_gold=user["total_earned_gold"] + item["reward_amount"],
        )
        await message.answer(f"✅ Спасибо за покупку! Начислено {item['reward_amount']} золота 💰")
    elif item["reward_type"] == "dna":
        database.update_user(
            message.from_user.id,
            dna_points=user["dna_points"] + item["reward_amount"],
            total_dna_earned=user["total_dna_earned"] + item["reward_amount"],
        )
        await message.answer(f"✅ Спасибо за покупку! Начислено {item['reward_amount']} очков ДНК 🧬")
