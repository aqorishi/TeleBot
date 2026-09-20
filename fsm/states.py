from aiogram.fsm.state import State, StatesGroup


class APIRegistration(StatesGroup):
    entering_customer_id = State()
    entering_api_key = State()
    entering_api_secret = State()




# class APIRegistration(StatesGroup):
#     choosing_exchange = State()
#     entering_api_key = State()
#     entering_api_secret = State()
#     confirming_real_or_test = State()
    
# class APIInputState(StatesGroup):
#     waiting_for_customer_id = State()
#     waiting_for_api_key = State()
#     waiting_for_api_secret = State()