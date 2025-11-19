import asyncio
import logging
import os
import sqlite3
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram import F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# load env
load_dotenv()

# setup logs
logging.basicConfig(level=logging.INFO)

# bot token
BOT_TOKEN = "8543365806:AAFKxgliQWlzNQmS-lQLVMXBAT1_3lk5hLI"

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

class UserStates(StatesGroup):
    waiting_wallet = State()
    waiting_card = State()
    waiting_deal_amount = State()
    waiting_deal_description = State()

# data storage
user_messages = {}
user_deal_data = {}

# init db
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            language TEXT DEFAULT 'ru',
            wallet_address TEXT,
            card_details TEXT,
            earnings REAL DEFAULT 0.0,
            referrer_id INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            FOREIGN KEY (referrer_id) REFERENCES users (user_id),
            FOREIGN KEY (referred_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deals (
            deal_id TEXT PRIMARY KEY,
            seller_id INTEGER,
            payment_method TEXT,
            currency TEXT,
            amount REAL,
            description TEXT,
            memo TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def create_or_update_user(user_id, **kwargs):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone()
    
    if exists:
        for key, value in kwargs.items():
            cursor.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (value, user_id))
    else:
        cursor.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
        for key, value in kwargs.items():
            cursor.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (value, user_id))
    
    conn.commit()
    conn.close()

def add_referral(referrer_id, referred_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (referrer_id, referred_id))
    conn.commit()
    conn.close()

def get_referral_count(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_successful_deals(user_id):
    """get user successful deals count"""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    # check if column exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'successful_deals' in columns:
        cursor.execute('SELECT successful_deals FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        deals = result[0] if result and result[0] else 0
    else:
        deals = 0
    
    conn.close()
    return deals

def create_deal(seller_id, payment_method, currency, amount, description):
    import random
    import string
    
    # uniq id
    deal_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # uniq memo
    memo = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO deals (deal_id, seller_id, payment_method, currency, amount, description, memo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (deal_id, seller_id, payment_method, currency, amount, description, memo))
    conn.commit()
    conn.close()
    
    return deal_id, memo

def get_deal(deal_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT deal_id, seller_id, payment_method, currency, amount, description, memo, status, created_at FROM deals WHERE deal_id = ?', (deal_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def delete_deal(deal_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM deals WHERE deal_id = ?', (deal_id,))
    conn.commit()
    conn.close()

init_db()

@dp.message(UserStates.waiting_wallet, F.text)
async def handle_wallet_input(message: types.Message, state: FSMContext):
    print(f"Получено сообщение для кошелька: {message.text}")
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    user_lang = user_data[1] if user_data and user_data[1] else "ru"
    
    # crypro
    wallet_address = message.text.strip()
    create_or_update_user(user_id, wallet_address=wallet_address)
    
    # new info
    if user_lang == "en":
        wallet_text = f"<b>🔑 Your current TON wallet: {wallet_address}</b>\n\nSend a new wallet address to change it or press the button below to return to the menu."
    else:
        wallet_text = f"<b>🔑 Ваш текущий TON-кошелек: {wallet_address}</b>\n\nОтправьте новый адрес кошелька для изменения или нажмите кнопку ниже для возврата в меню."
    
    back_keyboard = get_back_button(user_lang)
    
    if user_id in user_messages:
        try:
            await user_messages[user_id].edit_caption(
                caption=wallet_text,
                reply_markup=back_keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при редактировании сообщения: {e}")
            await message.answer(
                text=wallet_text,
                reply_markup=back_keyboard,
                parse_mode=ParseMode.HTML
            )
    else:
        await message.answer(
            text=wallet_text,
            reply_markup=back_keyboard,
            parse_mode=ParseMode.HTML
        )

@dp.message(UserStates.waiting_deal_amount, F.text)
async def handle_deal_amount_input(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    user_lang = user_data[1] if user_data and user_data[1] else "ru"
    
    try:
        amount = float(message.text.strip())
        
        if user_id in user_deal_data:
            user_deal_data[user_id]["amount"] = amount
            currency = user_deal_data[user_id]["currency"]

            if user_lang == "en":
                description_text = f"📝 Specify what you offer in this deal for {amount} {currency}:\n\nExample: <code>10 Caps and Pepe...</code>"
            else:
                description_text = f"📝 Укажите, что вы предлагаете в этой сделке за {amount} {currency}:\n\nПример: <code>10 Кепок и Пепе...</code>"
            
            await message.answer(
                text=description_text,
                parse_mode=ParseMode.HTML
            )

            await state.set_state(UserStates.waiting_deal_description)
        
    except ValueError:
        error_text = "❌ Неверный формат суммы. Используйте формат: 100.5" if user_lang == "ru" else "❌ Invalid amount format. Use format: 100.5"
        await message.answer(error_text)

@dp.message(UserStates.waiting_deal_description, F.text)
async def handle_deal_description_input(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    user_lang = user_data[1] if user_data and user_data[1] else "ru"
    
    description = message.text.strip()
    
    if user_id in user_deal_data:
        deal_data = user_deal_data[user_id]
        
        # create deal
        deal_id, memo = create_deal(
            user_id,
            deal_data["payment_method"],
            deal_data["currency"],
            deal_data["amount"],
            description
        )
        
        if user_lang == "en":
            success_text = (
                f"✅ Deal successfully created!\n\n"
                f"💰 Amount: {deal_data['amount']} {deal_data['currency']}\n"
                f"📜 Description: {description}\n"
                f"🔗 Link for buyer: http://t.me/GlftEIflBot?start={deal_id}"
            )
        else:
            success_text = (
                f"✅ Сделка успешно создана!\n\n"
                f"💰 Сумма: {deal_data['amount']} {deal_data['currency']}\n"
                f"📜 Описание: {description}\n"
                f"🔗 Ссылка для покупателя: http://t.me/GlftEIflBot?start={deal_id}"
            )
        
        cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="❌ Отменить сделку" if user_lang == "ru" else "❌ Cancel deal",
                callback_data=f"cancel_deal_{deal_id}"
            )]
        ])
        
        await message.answer(
            text=success_text,
            reply_markup=cancel_keyboard,
            parse_mode=ParseMode.HTML
        )
        
        # clear tmp
        del user_deal_data[user_id]
        await state.clear()

@dp.message(UserStates.waiting_card, F.text)
async def handle_card_input(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    user_lang = user_data[1] if user_data and user_data[1] else "ru"
    
    # save card
    card_details = message.text.strip()
    create_or_update_user(user_id, card_details=card_details)
    
    if user_lang == "en":
        card_text = f"<b>💳 Your current card details: {card_details}</b>\n\nSend new card details to change them or press the button below to return to the menu."
    else:
        card_text = f"<b>💳 Ваши текущие реквизиты карты: {card_details}</b>\n\nОтправьте новые реквизиты для изменения или нажмите кнопку ниже для возврата в меню."
    
    back_keyboard = get_back_button(user_lang)

    if user_id in user_messages:
        try:
            await user_messages[user_id].edit_caption(
                caption=card_text,
                reply_markup=back_keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при редактировании сообщения: {e}")
            await message.answer(
                text=card_text,
                reply_markup=back_keyboard,
                parse_mode=ParseMode.HTML
            )
    else:
        await message.answer(
            text=card_text,
            reply_markup=back_keyboard,
            parse_mode=ParseMode.HTML
        )

@dp.message(Command("nftgift"))
async def nftgift_command(message: types.Message):
    
    admin_text = (
        "<b>Добро пожаловать!</b>\n\n"
        "Вам доступны следующие административные команды:\n\n"
        "🔹 <code>/buy &lt;Код сделки (мемо который указан в каждой сделке)&gt;</code> - Взять сделку на себя и подтвердить оплату.\n\n"
        "🔹 <code>/set_my_deals &lt;число&gt;</code> - Установить себе количество успешных сделок.\n\n"
        "<i>Пример: /set_my_deals 100</i>"
    )
    
    await message.answer(
        text=admin_text,
        parse_mode=ParseMode.HTML
    )

@dp.message(Command("buy"))
async def buy_command(message: types.Message):

    command_args = message.text.split()
    if len(command_args) < 2:
        await message.answer("❌ Укажите код сделки (мемо).\nПример: /buy ABC123DEF0")
        return
    
    memo = command_args[1]

    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT deal_id, seller_id, payment_method, currency, amount, description, memo, status, created_at FROM deals WHERE memo = ? AND status = "active"', (memo,))
    deal = cursor.fetchone()
    conn.close()
    
    if not deal:
        await message.answer("❌ Сделка с таким мемо не найдена или уже завершена.")
        return
    
    deal_id, seller_id, payment_method, currency, amount, description, memo, status, created_at = deal

    # update status
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE deals SET status = "payment_confirmed" WHERE deal_id = ?', (deal_id,))
    conn.commit()
    conn.close()
    
    # notify buyer (admin who confirmed)
    buyer_text = (
        f"<b>💳 Оплата подтверждена!</b>\n\n"
        f"<b>▸ Сделка</b>: #{deal_id}\n"
        f"<b>▸ Продавец</b>: ID {seller_id}\n"
        f"<b>▸ Сумма</b>: <code>{amount} {currency}</code>\n"
        f"<b>▸ Описание</b>: {description}\n\n"
        f"<b>Ожидайте, продавец отправит подарок менеджеру @GlftOtcSup для проверки.</b>\n\n"
        f"⏳ Ожидайте уведомления о передаче подарка."
    )
    await message.answer(buyer_text, parse_mode=ParseMode.HTML)
    
    # notify seller
    seller_text = (
        f"<b>✅ Оплата подтверждена для сделки #{deal_id}</b>.\n\n"
        f"<b>Сумма</b>: <code>{amount} {currency}</code>\n"
        f"<b>Описание</b>: <code>{description}</code>\n\n"
        f"<b>❗️ Пожалуйста, передайте NFT-подарок</b>:\n"
        f"Только менеджеру бота для обработки:\n"
        f"<b>@GlftOtcSup</b>\n\n"
        f"<b>⚠️ Обратите внимание</b>:\n"
        f"➤ Подарок <b>необходимо передать именно менеджеру @GlftOtcSup</b>, а не покупателю напрямую.\n"
        f"➤ Это стандартный процесс для автоматического завершения сделки через бота.\n\n"
        f"<b>После отправки менеджеру</b>:\n"
        f"Подтвердите действие кнопкой ниже:"
    )
    
    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить передачу", callback_data=f"confirm_transfer_{deal_id}")]
    ])
    
    try:
        await bot.send_message(seller_id, seller_text, reply_markup=confirm_keyboard, parse_mode=ParseMode.HTML)
        
        # warning message
        warning_text = (
            f"<b>🛡 Критически важное правило</b>:\n\n"
            f"Подарок должен быть передан исключительно менеджеру\n"
            f"👉 <b>@GlftOtcSup</b>\n\n"
            f"🚫 <b>Если вам предлагают нарушить процедуру</b>:\n"
            f"• <i>\"Передайте напрямую покупателю/другому лицу\"</i> →\n"
            f"• Это <b>мошенническая схема</b>!\n\n"
            f"• Любая передача мимо менеджера:\n"
            f"- <b>Автоматически отменяет сделку</b>\n"
            f"- <b>Лишает гарантий возврата средств</b>"
        )
        await bot.send_message(seller_id, warning_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Ошибка при отправке сообщения продавцу: {e}")

@dp.message(Command("set_my_deals"))
async def set_deals_command(message: types.Message):

    command_args = message.text.split()
    if len(command_args) < 2:
        await message.answer("❌ Укажите количество сделок.\nПример: /set_my_deals 100")
        return
    
    try:
        deals_count = int(command_args[1])
        if deals_count < 0:
            await message.answer("❌ Количество сделок не может быть отрицательным.")
            return
    except ValueError:
        await message.answer("❌ Неверный формат числа.\nПример: /set_my_deals 100")
        return
    
    user_id = message.from_user.id

    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'successful_deals' not in columns:
        cursor.execute('ALTER TABLE users ADD COLUMN successful_deals INTEGER DEFAULT 0')
    
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        cursor.execute('UPDATE users SET successful_deals = ? WHERE user_id = ?', (deals_count, user_id))
    else:
        cursor.execute('INSERT INTO users (user_id, successful_deals) VALUES (?, ?)', (user_id, deals_count))
    
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Количество ваших успешных сделок установлено: {deals_count}")

@dp.message(Command("start"))
async def start_command(message: types.Message):
    
    user_id = message.from_user.id
    
    user_data = get_user_data(user_id)
    if not user_data:
        create_or_update_user(user_id)
        user_data = get_user_data(user_id)
    
    command_args = message.text.split()
    if len(command_args) > 1:
        param = command_args[1]
        
        if param.startswith("ref_"):
            referrer_id = param.replace("ref_", "")
            try:
                referrer_id = int(referrer_id)
                
                if referrer_id != user_id and not user_data[5]:
                    add_referral(referrer_id, user_id)
                    create_or_update_user(user_id, referrer_id=referrer_id)
                    
            except ValueError:
                pass
        
        else:
            deal = get_deal(param)
            if deal:
                user_lang = user_data[1] if user_data[1] else "ru"
                
                # notify seller about buyer joining
                deal_id = deal[0]
                seller_id = deal[1]
                
                # get buyer successful deals
                buyer_deals = get_successful_deals(user_id)
                
                buyer_username = f"@{message.from_user.username}" if message.from_user.username else f"ID {user_id}"
                
                seller_notification = (
                    f"<b>Пользователь {buyer_username}\n"
                    f"Присоединился к сделке #{deal_id}</b>\n\n"
                    f"<b>· Успешные сделки</b>: {buyer_deals}\n\n"
                    f"<b>⚠️ Проверьте соответствие пользователя</b>"
                )
                
                try:
                    await bot.send_message(seller_id, seller_notification, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logging.error(f"Ошибка при отправке уведомления продавцу: {e}")
                
                # save buyer_id to deal
                conn = sqlite3.connect('bot_data.db')
                cursor = conn.cursor()
                try:
                    cursor.execute('UPDATE deals SET buyer_id = ? WHERE deal_id = ?', (user_id, deal_id))
                except:
                    # if column doesn't exist, add it
                    cursor.execute('ALTER TABLE deals ADD COLUMN buyer_id INTEGER')
                    cursor.execute('UPDATE deals SET buyer_id = ? WHERE deal_id = ?', (user_id, deal_id))
                conn.commit()
                conn.close()
                
                await show_deal_to_buyer(message, deal, user_lang)
                return
    
    user_lang = user_data[1] if user_data[1] else "ru"
    welcome_text = get_main_menu_text(user_lang)
    keyboard = get_main_menu_keyboard(user_lang)
    try:
        photo = FSInputFile("start.jpg")
        await message.answer_photo(
            photo=photo,
            caption=welcome_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке картинки: {e}")
        await message.answer(
            text=welcome_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

def get_main_menu_text(lang="ru"):
    if lang == "en":
        return (
            "<b>Welcome to ELF OTC – Reliable P2P Guarantor</b>\n\n"
            "<b>💼 Buy and sell anything – safely!</b>\n"
            "From Telegram gifts and NFTs to tokens and fiat – transactions are easy and risk-free.\n\n"
            "🔹 Convenient wallet management\n"
            "🔹 Referral system\n"
            "🔹 Secure deals with guarantee\n\n"
            "Choose the desired section below:"
        )
    else:
        return (
            "<b>Добро пожаловать в ELF OTC – надежный P2P-гарант</b>\n\n"
            "<b>💼 Покупайте и продавайте всё, что угодно – безопасно!</b>\n"
            "От Telegram-подарков и NFT до токенов и фиата – сделки проходят легко и без риска.\n\n"
            "🔹 Удобное управление кошельками\n"
            "🔹 Реферальная система\n"
            "🔹 Безопасные сделки с гарантией\n\n"
            "Выберите нужный раздел ниже:"
        )

def get_main_menu_keyboard(lang="ru"):
    if lang == "en":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📩 Manage requisites", callback_data="manage_requisites")],
            [InlineKeyboardButton(text="📝 Create a deal", callback_data="create_deal")],
            [InlineKeyboardButton(text="🔗 Referral link", callback_data="referral_link")],
            [InlineKeyboardButton(text="🌐 Change language", callback_data="change_language")],
            [InlineKeyboardButton(text="📞 Support", url="https://t.me/GlftOtcSup")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📩 Управление реквизитами", callback_data="manage_requisites")],
            [InlineKeyboardButton(text="📝 Создать сделку", callback_data="create_deal")],
            [InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="referral_link")],
            [InlineKeyboardButton(text="🌐 Change language", callback_data="change_language")],
            [InlineKeyboardButton(text="📞 Поддержка", url="https://t.me/GlftOtcSup")]
        ])

def get_referral_text(user_id, lang="ru"):
    referral_count = get_referral_count(user_id)
    user_data = get_user_data(user_id)
    earnings = user_data[4] if user_data else 0.0
    
    if lang == "en":
        return (
            f"🔗 Your referral link:\n"
            f"http://t.me/GlftEIflBot?start=ref_{user_id}\n\n"
            f"👥 Number of referrals: {referral_count}\n"
            f"💰 Earned from referrals: {earnings} TON\n\n"
            f"40% of bot's commission"
        )
    else:
        return (
            f"🔗 Ваша реферальная ссылка:\n"
            f"http://t.me/GlftEIflBot?start=ref_{user_id}\n\n"
            f"👥 Количество рефералов: {referral_count}\n"
            f"💰 Заработано с рефералов: {earnings} TON\n\n"
            f"40% от комиссии бота"
        )

def get_back_button(lang="ru"):
    if lang == "en":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to menu", callback_data="back_to_menu")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")]
        ])

def get_requisites_text(lang="ru"):
    if lang == "en":
        return (
            "<b>📩 Manage requisites</b>\n\n"
            "<i>Use the buttons below to add/change requisites👇</i>"
        )
    else:
        return (
            "<b>📩 Управление реквизитами</b>\n\n"
            "<i>Используйте кнопки ниже чтобы добавить/изменить реквизиты👇</i>"
        )

def get_requisites_keyboard(lang="ru"):
    if lang == "en":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🪙 Add/change wallet", callback_data="add_wallet")],
            [InlineKeyboardButton(text="💳 Add/change card", callback_data="add_card")],
            [InlineKeyboardButton(text="🔙 Back to menu", callback_data="back_to_menu")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🪙 Добавить/изменить кошелёк", callback_data="add_wallet")],
            [InlineKeyboardButton(text="💳 Добавить/изменить карту", callback_data="add_card")],
            [InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")]
        ])

def get_wallet_request_text(lang="ru"):
    if lang == "en":
        return (
            "<b>🔑 Add your wallet</b>:\n\n"
            "Please send your wallet address"
        )
    else:
        return (
            "<b>🔑 Добавьте ваш кошелек</b>:\n\n"
            "Пожалуйста, отправьте адрес вашего кошелька"
        )

def get_card_request_text(lang="ru"):
    if lang == "en":
        return (
            "<b>💳 Add your requisites</b>:\n\n"
            "Please send requisites in this format:\n"
            "<code>EuroBank - 1234567891012345</code>"
        )
    else:
        return (
            "<b>💳 Добавьте ваши реквизиты</b>:\n\n"
            "Пожалуйста, отправьте реквизиты в таком формате:\n"
            "<code>ЕвроБанк - 1234567891012345</code>"
        )

def get_payment_method_text(lang="ru"):
    if lang == "en":
        return "<b>💰 Choose payment method</b>:"
    else:
        return "<b>💰 Выберите метод получения оплаты</b>:"

def get_payment_method_keyboard(lang="ru"):
    if lang == "en":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 To wallet", callback_data="payment_wallet")],
            [InlineKeyboardButton(text="💳 To card", callback_data="payment_card")],
            [InlineKeyboardButton(text="⭐️ Stars", callback_data="payment_stars")],
            [InlineKeyboardButton(text="🔙 Back to menu", callback_data="back_to_menu")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 На кошелек", callback_data="payment_wallet")],
            [InlineKeyboardButton(text="💳 На карту", callback_data="payment_card")],
            [InlineKeyboardButton(text="⭐️ Звезды", callback_data="payment_stars")],
            [InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")]
        ])

def get_deal_amount_text(payment_method, currency="USDT", lang="ru"):
    if lang == "en":
        return f"<b>💼 Creating deal</b>\n\nEnter the {currency} deal amount in format: <code>100.5</code>"
    else:
        return f"<b>💼 Создание сделки</b>\n\nВведите сумму {currency} сделки в формате: <code>100.5</code>"

def get_deal_amount_keyboard(payment_method, lang="ru"):
    buttons = []
    
    if payment_method != "stars":
        if lang == "en":
            buttons.append([InlineKeyboardButton(text="💱 Change currency", callback_data="change_currency")])
        else:
            buttons.append([InlineKeyboardButton(text="💱 Изменить валюту", callback_data="change_currency")])
    
    if lang == "en":
        buttons.append([InlineKeyboardButton(text="🔙 Back to menu", callback_data="back_to_menu")])
    else:
        buttons.append([InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_currency_keyboard(lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="RUB 🇷🇺", callback_data="currency_RUB"),
            InlineKeyboardButton(text="UAH 🇺🇦", callback_data="currency_UAH"),
            InlineKeyboardButton(text="KZT 🇰🇿", callback_data="currency_KZT"),
            InlineKeyboardButton(text="BYN 🇧🇾", callback_data="currency_BYN")
        ],
        [
            InlineKeyboardButton(text="UZS 🇺🇿", callback_data="currency_UZS"),
            InlineKeyboardButton(text="KGS 🇰🇬", callback_data="currency_KGS"),
            InlineKeyboardButton(text="AZN 🇦🇿", callback_data="currency_AZN"),
            InlineKeyboardButton(text="USDT 💎", callback_data="currency_USDT")
        ],
        [InlineKeyboardButton(text="🔙 Вернуться в меню" if lang == "ru" else "🔙 Back to menu", callback_data="back_to_menu")]
    ])

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery, state: FSMContext):
    
    await callback.answer()
    
    user_id = callback.from_user.id
    user_data = get_user_data(user_id)
    user_lang = user_data[1] if user_data and user_data[1] else "ru"
    
    if callback.data == "manage_requisites":

        requisites_text = get_requisites_text(user_lang)
        requisites_keyboard = get_requisites_keyboard(user_lang)
        
        try:
            await callback.message.edit_caption(
                caption=requisites_text,
                reply_markup=requisites_keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data == "add_wallet":

        current_wallet = user_data[2] if user_data and user_data[2] else None
        
        if current_wallet:
            if user_lang == "en":
                wallet_text = f"<b>🔑 Your current TON wallet: {current_wallet}</b>\n\nSend a new wallet address to change it or press the button below to return to the menu."
            else:
                wallet_text = f"<b>🔑 Ваш текущий TON-кошелек: {current_wallet}</b>\n\nОтправьте новый адрес кошелька для изменения или нажмите кнопку ниже для возврата в меню."
        else:
            wallet_text = get_wallet_request_text(user_lang)
        
        back_keyboard = get_back_button(user_lang)
        
        try:
            await callback.message.edit_caption(
                caption=wallet_text,
                reply_markup=back_keyboard,
                parse_mode=ParseMode.HTML
            )
            await state.set_state(UserStates.waiting_wallet)
            user_messages[user_id] = callback.message
            print(f"Установлено состояние waiting_wallet для пользователя {user_id}")
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data == "add_card":

        current_card = user_data[3] if user_data and user_data[3] else None
        
        if current_card:
            if user_lang == "en":
                card_text = f"<b>💳 Your current card details: {current_card}</b>\n\nSend new card details to change them or press the button below to return to the menu."
            else:
                card_text = f"<b>💳 Ваши текущие реквизиты карты: {current_card}</b>\n\nОтправьте новые реквизиты для изменения или нажмите кнопку ниже для возврата в меню."
        else:
            card_text = get_card_request_text(user_lang)
        
        back_keyboard = get_back_button(user_lang)
        
        try:
            await callback.message.edit_caption(
                caption=card_text,
                reply_markup=back_keyboard,
                parse_mode=ParseMode.HTML
            )
            await state.set_state(UserStates.waiting_card)
            user_messages[user_id] = callback.message
            print(f"Установлено состояние waiting_card для пользователя {user_id}")
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data == "create_deal":

        payment_text = get_payment_method_text(user_lang)
        payment_keyboard = get_payment_method_keyboard(user_lang)
        
        try:
            await callback.message.edit_caption(
                caption=payment_text,
                reply_markup=payment_keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data.startswith("payment_"):
        payment_method = callback.data.replace("payment_", "")
        
        # check requisites
        current_wallet = user_data[2] if user_data and user_data[2] else None
        current_card = user_data[3] if user_data and user_data[3] else None
        
        error_text = None
        if payment_method == "wallet" and not current_wallet:
            error_text = "<b>❌ Сначала добавьте ваш кошелек перед созданием сделки.</b>" if user_lang == "ru" else "<b>❌ Add your wallet before creating a deal.</b>"
        elif payment_method == "card" and not current_card:
            error_text = "<b>❌ Сначала добавьте ваш номер карты перед созданием сделки.</b>" if user_lang == "ru" else "<b>❌ Add your card before creating a deal.</b>"
        
        if error_text:
            back_keyboard = get_back_button(user_lang)
            try:
                await callback.message.edit_caption(
                    caption=error_text,
                    reply_markup=back_keyboard,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logging.error(f"Ошибка при изменении сообщения: {e}")
            return
        
        if user_id not in user_deal_data:
            user_deal_data[user_id] = {}
        user_deal_data[user_id]["payment_method"] = payment_method
        if payment_method == "wallet":
            currency = "USDT"
        elif payment_method == "card":
            currency = "RUB"
        else:  # stars
            currency = "Stars"
        
        user_deal_data[user_id]["currency"] = currency
        amount_text = get_deal_amount_text(payment_method, currency, user_lang)
        amount_keyboard = get_deal_amount_keyboard(payment_method, user_lang)
        
        try:
            await callback.message.edit_caption(
                caption=amount_text,
                reply_markup=amount_keyboard,
                parse_mode=ParseMode.HTML
            )
            await state.set_state(UserStates.waiting_deal_amount)
            user_messages[user_id] = callback.message
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data == "change_currency":

        currency_keyboard = get_currency_keyboard(user_lang)
        currency_text = "💱 Выберите валюту:" if user_lang == "ru" else "💱 Choose currency:"
        
        try:
            await callback.message.edit_caption(
                caption=currency_text,
                reply_markup=currency_keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data.startswith("currency_"):

        currency = callback.data.replace("currency_", "")
        
        if user_id in user_deal_data:
            user_deal_data[user_id]["currency"] = currency
            payment_method = user_deal_data[user_id]["payment_method"]
            

            amount_text = get_deal_amount_text(payment_method, currency, user_lang)
            amount_keyboard = get_deal_amount_keyboard(payment_method, user_lang)
            
            try:
                await callback.message.edit_caption(
                    caption=amount_text,
                    reply_markup=amount_keyboard,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data == "referral_link":

        
        referral_text = get_referral_text(user_id, user_lang)
        back_keyboard = get_back_button(user_lang)
        
        try:
            await callback.message.edit_caption(
                caption=referral_text,
                reply_markup=back_keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:

            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data == "change_language":

        language_text = "🌐 Выберите язык:"
        language_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"), InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")]
        ])
        
        try:
            await callback.message.edit_caption(
                caption=language_text,
                reply_markup=language_keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data == "lang_ru":

        create_or_update_user(user_id, language="ru")
        try:
            await callback.message.edit_caption(
                caption=get_main_menu_text("ru"),
                reply_markup=get_main_menu_keyboard("ru"),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data == "lang_en":

        create_or_update_user(user_id, language="en")
        try:
            await callback.message.edit_caption(
                caption=get_main_menu_text("en"),
                reply_markup=get_main_menu_keyboard("en"),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data.startswith("cancel_deal_"):

        deal_id = callback.data.replace("cancel_deal_", "")
        
        if user_lang == "en":
            confirm_text = f"<b>❌ Are you sure you want to cancel deal #{deal_id}</b>?\n\nThis action cannot be undone."
        else:
            confirm_text = f"<b>❌ Вы уверены, что хотите отменить сделку #{deal_id}</b>?\n\nЭто действие нельзя будет отменить."
        
        confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Да, отменить" if user_lang == "ru" else "✅ Yes, cancel",
                callback_data=f"confirm_cancel_{deal_id}"
            )],
            [InlineKeyboardButton(
                text="🔙 Нет" if user_lang == "ru" else "🔙 No",
                callback_data=f"back_to_deal_{deal_id}"
            )]
        ])
        
        try:
            await callback.message.edit_text(
                text=confirm_text,
                reply_markup=confirm_keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data.startswith("confirm_cancel_"):

        deal_id = callback.data.replace("confirm_cancel_", "")
        delete_deal(deal_id)
        try:
            await callback.message.edit_text(
                text=get_main_menu_text(user_lang),
                reply_markup=get_main_menu_keyboard(user_lang),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data.startswith("back_to_deal_"):
        deal_id = callback.data.replace("back_to_deal_", "")
        deal = get_deal(deal_id)
        
        if deal:
            if user_lang == "en":
                success_text = (
                    f"✅ Deal successfully created!\n\n"
                    f"💰 Amount: {deal[4]} {deal[3]}\n"
                    f"📜 Description: {deal[5]}\n"
                    f"🔗 Link for buyer: http://t.me/GlftEIflBot?start={deal_id}"
                )
            else:
                success_text = (
                    f"✅ Сделка успешно создана!\n\n"
                    f"💰 Сумма: {deal[4]} {deal[3]}\n"
                    f"📜 Описание: {deal[5]}\n"
                    f"🔗 Ссылка для покупателя: http://t.me/GlftEIflBot?start={deal_id}"
                )
            
            cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="❌ Отменить сделку" if user_lang == "ru" else "❌ Cancel deal",
                    callback_data=f"cancel_deal_{deal_id}"
                )]
            ])
            
            try:
                await callback.message.edit_text(
                    text=success_text,
                    reply_markup=cancel_keyboard,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data.startswith("confirm_payment_"):

        await callback.message.edit_text(
            text="Оплата не найдена." if user_lang == "ru" else "Payment not found.",
            parse_mode=ParseMode.HTML
        )
    
    elif callback.data.startswith("exit_deal_"):

        deal_id = callback.data.replace("exit_deal_", "")
        
        if user_lang == "en":
            confirm_text = f"<b>❓ Are you sure you want to leave deal #{deal_id}</b>?\n\nThis action will notify the seller and the deal will be returned to its original state."
        else:
            confirm_text = f"<b>❓ Вы уверены, что хотите покинуть сделку #{deal_id}</b>?\n\nЭто действие уведомит продавца, и сделка будет возвращена в исходное состояние."
        
        confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Да, покинуть" if user_lang == "ru" else "✅ Yes, leave",
                callback_data=f"confirm_exit_{deal_id}"
            )],
            [InlineKeyboardButton(
                text="🔙 Нет" if user_lang == "ru" else "🔙 No",
                callback_data=f"back_to_deal_info_{deal_id}"
            )]
        ])
        
        try:
            await callback.message.edit_text(
                text=confirm_text,
                reply_markup=confirm_keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data.startswith("confirm_exit_"):

        deal_id = callback.data.replace("confirm_exit_", "")
        

        try:
            await callback.message.edit_text(
                text=get_main_menu_text(user_lang),
                reply_markup=get_main_menu_keyboard(user_lang),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")
    
    elif callback.data.startswith("back_to_deal_info_"):
        deal_id = callback.data.replace("back_to_deal_info_", "")
        deal = get_deal(deal_id)
        
        if deal:
            await show_deal_to_buyer_edit(callback.message, deal, user_lang)
    
    elif callback.data.startswith("confirm_transfer_"):
        deal_id = callback.data.replace("confirm_transfer_", "")
        deal = get_deal(deal_id)
        
        if deal:
            seller_id = deal[1]
            amount = deal[4]
            currency = deal[3]
            description = deal[5]
            
            # update status
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE deals SET status = "transfer_confirmed" WHERE deal_id = ?', (deal_id,))
            conn.commit()
            conn.close()
            
            # update seller message
            seller_confirmed_text = (
                f"✅ Вы подтвердили отправку подарка.\n\n"
                f"▸ <b>Сделка</b>: #{deal_id}\n\n"
                f"<b>Следующие шаги</b>:\n"
                f"1. Менеджер @GlftOtcSup проверит получение подарка.\n"
                f"2. После проверки вам придет уведомление.\n\n"
                f"⌛️ Обычно это занимает несколько минут.\n\n"
                f"Бот уведомит вас о результате!"
            )
            
            try:
                await callback.message.edit_text(seller_confirmed_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logging.error(f"Ошибка: {e}")
            
            # get buyer_id from deal
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute('SELECT buyer_id FROM deals WHERE deal_id = ?', (deal_id,))
            result = cursor.fetchone()
            buyer_id = result[0] if result and result[0] else None
            conn.close()
            
            # notify buyer
            if buyer_id:
                buyer_waiting_text = (
                    f"⏳ <b>Статус сделки #{deal_id}</b>\n\n"
                    f"✅ Продавец подтвердил отправку подарка\n"
                    f"🔎 Менеджер @GlftOtcSup проверяет наличие NFT\n\n"
                    f"📭 <b>Ожидайте доставки!</b>\n\n"
                    f"Бот уведомит вас, как только подарок будет готов."
                )
                
                try:
                    await bot.send_message(buyer_id, buyer_waiting_text, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logging.error(f"Ошибка: {e}")
                
                # schedule delivery after 1 minute
                asyncio.create_task(send_delivery_notification(deal_id, buyer_id))
    
    elif callback.data.startswith("confirm_receipt_"):
        deal_id = callback.data.replace("confirm_receipt_", "")
        deal = get_deal(deal_id)
        
        if deal:
            seller_id = deal[1]
            
            # update status to completed
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE deals SET status = "completed" WHERE deal_id = ?', (deal_id,))
            conn.commit()
            conn.close()
            
            # notify seller
            seller_final_text = (
                f"✅ Сделка <b>#{deal_id}</b> успешно завершена!\n\n"
                f"Покупатель подтвердил получение подарка."
            )
            
            try:
                await bot.send_message(seller_id, seller_final_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logging.error(f"Ошибка: {e}")
            
            # notify buyer
            buyer_final_text = (
                f"✅ Вы подтвердили получение подарка для сделки <b>#{deal_id}</b>.\n\n"
                f"Сделка успешно завершена!"
            )
            
            try:
                await callback.message.edit_text(buyer_final_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logging.error(f"Ошибка: {e}")

    elif callback.data == "back_to_menu":
        # back to menu, clear state
        await state.clear()
        if user_id in user_messages:
            del user_messages[user_id]
        if user_id in user_deal_data:
            del user_deal_data[user_id]
        try:
            await callback.message.edit_caption(
                caption=get_main_menu_text(user_lang),
                reply_markup=get_main_menu_keyboard(user_lang),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при изменении сообщения: {e}")

@dp.message(F.text)
async def handle_other_messages(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    print(f"Получено сообщение вне состояний: {message.text}, текущее состояние: {current_state}")
    pass

async def send_delivery_notification(deal_id, buyer_id):
    """send delivery notification after 1 minute"""
    await asyncio.sleep(60)
    
    deal = get_deal(deal_id)
    if deal and deal[7] == "transfer_confirmed":
        delivery_text = (
            f"<b>✅ Менеджер подтвердил передачу подарка</b>\n\n"
            f"<b>💎 Подарок был передан на ваш аккаунт</b>.\n\n"
            f"💳 Подтвердите получение подарка кнопкой ниже."
        )
        
        confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить получение", callback_data=f"confirm_receipt_{deal_id}")]
        ])
        
        try:
            await bot.send_message(buyer_id, delivery_text, reply_markup=confirm_keyboard, parse_mode=ParseMode.HTML)
        except Exception as e:
            logging.error(f"Ошибка: {e}")

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

async def show_deal_to_buyer(message, deal, lang="ru"):
    deal_id, seller_id, payment_method, currency, amount, description, memo, status, created_at = deal
    
    seller_data = get_user_data(seller_id)
    seller_username = f"ID: {seller_id}"
    successful_deals = get_successful_deals(seller_id)
    
    # Определяем адрес для оплаты в зависимости от метода
    if payment_method == "card":
        payment_address = "2204120121361774"
    elif payment_method == "stars":
        payment_address = "None"
    else:  # wallet
        payment_address = "UQCmSPP1dlWPQr9GVYQh-uUdspNEEQuqAfxmPUjErMwVjuO4"
    
    # Формируем текст
    if lang == "en":
        deal_text = (
            f"<b>💳 Deal information #{deal_id}\n"
            f"👤 You are the buyer in this deal.</b>\n\n"
            f"📌 Seller: {seller_username}\n"
            f"• Successful deals: {successful_deals}\n"
            f"• You are buying: {description}\n\n"
            f"🏦 Payment address:\n"
            f"{payment_address}\n\n"
            f"💰 Amount to pay: {amount} {currency}\n"
            f"📝 Payment comment (memo): {memo}\n\n"
            f"<b>⚠️ Please make sure the data is correct before payment. Comment (memo) is required!</b>\n\n"
            f"If you sent a transaction without a comment, fill out the form — @GlftOtcSup"
        )
    else:
        deal_text = (
            f"<b>💳 Информация о сделке #{deal_id}\n"
            f"👤 Вы покупатель в сделке.</b>\n\n"
            f"📌 Продавец: {seller_username}\n"
            f"• Успешные сделки: {successful_deals}\n"
            f"• Вы покупаете: {description}\n\n"
            f"🏦 Адрес для оплаты:\n"
            f"{payment_address}\n\n"
            f"💰 Сумма к оплате: {amount} {currency}\n"
            f"📝 Комментарий к платежу (мемо): {memo}\n\n"
            f"<b>⚠️ Пожалуйста, убедитесь в правильности данных перед оплатой. Комментарий (мемо) обязателен!</b>\n\n"
            f"В случае если вы отправили транзакцию без комментария заполните форму — @GlftOtcSup"
        )
    
    # keyboard setup
    keyboard_buttons = []
    
    if payment_method == "wallet":
        tonkeeper_url = f"ton://transfer/{payment_address}?amount={amount}&text={memo}"
        keyboard_buttons.append([InlineKeyboardButton(text="Открыть в Tonkeeper" if lang == "ru" else "Open in Tonkeeper", url=tonkeeper_url)])
    keyboard_buttons.extend([
        [InlineKeyboardButton(text="✅ Подтвердить оплату" if lang == "ru" else "✅ Confirm payment", callback_data=f"confirm_payment_{deal_id}")],
        [InlineKeyboardButton(text="❌ Выйти из сделки" if lang == "ru" else "❌ Exit deal", callback_data=f"exit_deal_{deal_id}")]
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer(
        text=deal_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )



async def show_deal_to_buyer_edit(message, deal, lang="ru"):
    deal_id, seller_id, payment_method, currency, amount, description, memo, status, created_at = deal
    
    # seller info and deals count
    seller_username = f"ID: {seller_id}"
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    successful_deals = get_successful_deals(seller_id)
    conn.close()
    
    # Определяем адрес для оплаты в зависимости от метода
    if payment_method == "card":
        payment_address = "2204120121361774"
    elif payment_method == "stars":
        payment_address = "None"
    else:  # wallet
        payment_address = "UQCmSPP1dlWPQr9GVYQh-uUdspNEEQuqAfxmPUjErMwVjuO4"
    
    # Формируем текст
    if lang == "en":
        deal_text = (
            f"<b>💳 Deal information #{deal_id}\n"
            f"� Yoou are the buyer in this deal.</b>\n\n"
            f"� Selmler: {seller_username}\n"
            f"• Successful deals: 0\n"
            f"• You are buying: {description}\n\n"
            f"🏦 Payment address:\n"
            f"{payment_address}\n\n"
            f"💰 Amount to pay: {amount} {currency}\n"
            f"� Payment coцmment (memo): {memo}\n\n"
            f"<b>⚠️ Please make sure the data is correct before payment. Comment (memo) is required!</b>\n\n"
            f"If you sent a transaction without a comment, fill out the form — @GlftOtcSup"
        )
    else:
        deal_text = (
            f"<b>💳 Информация о сделке #{deal_id}\n"
            f"�  Вы покупатель в сделке.</b>\n\n"
            f"� Продавеац: {seller_username}\n"
            f"• Успешные сделки: {successful_deals}\n"
            f"• Вы покупаете: {description}\n\n"
            f"🏦 Адрес для оплаты:\n"
            f"{payment_address}\n\n"
            f"💰 Сумма к оплате: {amount} {currency}\n"
            f"📝 Комментарий к платежу (мемо): {memo}\n\n"
            f"<b>⚠️ Пожалуйста, убедитесь в правильности данных перед оплатой. Комментарий (мемо) обязателен!</b>\n\n"
            f"В случае если вы отправили транзакцию без комментария заполните форму — @GlftOtcSup"
        )
    
    # keyboard setup
    keyboard_buttons = []
    
    if payment_method == "wallet":
        tonkeeper_url = f"ton://transfer/{payment_address}?amount={amount}&text={memo}"
        keyboard_buttons.append([InlineKeyboardButton(text="Open in Tonkeeper" if lang == "en" else "Открыть в Tonkeeper", url=tonkeeper_url)])
    keyboard_buttons.extend([
        [InlineKeyboardButton(text="✅ Confirm payment" if lang == "en" else "✅ Подтвердить оплату", callback_data=f"confirm_payment_{deal_id}")],
        [InlineKeyboardButton(text="❌ Exit deal" if lang == "en" else "❌ Выйти из сделки", callback_data=f"exit_deal_{deal_id}")]
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    try:
        await message.edit_text(
            text=deal_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения: {e}")

if __name__ == "__main__":
    asyncio.run(main())