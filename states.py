# -*- coding: utf-8 -*-
from aiogram.fsm.state import StatesGroup, State


class Nav(StatesGroup):
    choose_crab = State()
    choose_shore = State()
    main = State()
    hunt = State()
    mutations_root = State()
    mutations_shop = State()
    menu_root = State()
    profile = State()
    characteristics = State()
    dig = State()
    inventory = State()
    craft = State()
    misc = State()
    misc_detail = State()
    events = State()
    shop = State()
    waiting_nickname = State()
    waiting_search = State()


# Куда возвращает кнопка "Назад" из каждого состояния
PARENT_STATE = {
    Nav.hunt: Nav.main,
    Nav.mutations_root: Nav.main,
    Nav.mutations_shop: Nav.mutations_root,
    Nav.menu_root: Nav.main,
    Nav.profile: Nav.menu_root,
    Nav.characteristics: Nav.menu_root,
    Nav.dig: Nav.menu_root,
    Nav.inventory: Nav.menu_root,
    Nav.craft: Nav.menu_root,
    Nav.misc: Nav.menu_root,
    Nav.misc_detail: Nav.misc,
    Nav.events: Nav.misc,
    Nav.shop: Nav.profile,
    Nav.waiting_search: Nav.profile,
    Nav.waiting_nickname: Nav.profile,
}
