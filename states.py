"""FSM state groups shared across handlers."""
from aiogram.fsm.state import State, StatesGroup


class AddProduct(StatesGroup):
    title = State()
    description = State()
    price = State()
    delivery_type = State()
    delivery_content = State()


class EditProduct(StatesGroup):
    choose_field = State()
    new_value = State()


class Broadcast(StatesGroup):
    waiting_text = State()
    confirm = State()


class Refund(StatesGroup):
    waiting_order_id = State()
    confirm = State()