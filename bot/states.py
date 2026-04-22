from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    waiting_for_offer = State()
    waiting_for_phone = State()
    waiting_for_market_name = State()
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_middle_name = State()
    waiting_for_pinfl = State()
    waiting_for_passport_front = State()
    waiting_for_passport_back = State()
    waiting_for_selfie = State()
    waiting_for_approval = State()

class ClientStates(StatesGroup):
    main_menu = State()
    waiting_for_auditor_message = State()
    waiting_for_recon_disown_text = State()

class AuditorStates(StatesGroup):
    main_menu = State()
    waiting_for_broadcast_message = State()
    waiting_for_search_query = State()       # Qidiruv so'rovi kiritish
    viewing_search_results = State()         # Natijalar ro'yxati
    viewing_user_detail = State()            # Bitta user detail
    viewing_user_contracts = State()         # User shartnomalar
    viewing_user_sales = State()             # User xaridlar tarixi

class AdminStates(StatesGroup):
    main_menu = State()
    editing_config = State()
    waiting_for_rejection_reason = State()
    waiting_for_broadcast_message = State()
