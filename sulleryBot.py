import logging
from aiogram import Bot, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ParseMode
from aiogram.utils.markdown import text, bold, italic
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import pytz
from aiogram import types


import sqlite3
import datetime
import tokenKey

logging.basicConfig(level=logging.INFO)

bot = Bot(token=tokenKey.API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())


conn = sqlite3.connect("transactions.db")
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_chat_id INTEGER,
    patient_name TEXT,
    service TEXT,
    service_cost REAL,
    percentage REAL,
    date TEXT
)""")
conn.commit()

conn2 = sqlite3.connect("user.db")
cursor2 = conn2.cursor()
cursor2.execute("PRAGMA table_info(users)")
columns = cursor2.fetchall()
if not any(column[1] == "first_name" for column in columns):
    cursor2.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER UNIQUE,
    first_name TEXT
)""")

conn2.commit()

class AddUserStates(StatesGroup):
    first_name = State()

class AddTransactionStates(StatesGroup):
    patient_name = State()
    service = State()
    service_cost = State()
    percentage = State()
    confirmation = State()

class ConfirmDeleteStates(StatesGroup):
    confirm_delete = State()
    confirm_delete_again = State()



@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    cursor2.execute("SELECT * FROM users WHERE chat_id=?", (user_id,))
    row = cursor2.fetchone()

    if row is None:
        await message.reply("Добро пожаловать! Напишите, пожалуйста, своё имя:")
        cursor2.execute("INSERT INTO users (chat_id, first_name) VALUES (?, ?)", (user_id, None)) # добавьте эту строку
        conn2.commit() # и эту строку
        await AddUserStates.first_name.set()
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("1 - добавить транзакцию")
        markup.add("2 - показать зарплату за этот месяц")
        markup.add("3 - показать зарплату за предыдущий месяц")
        markup.add("4 - пациенты за этот месяц")
        markup.add("5 - очистить все данные")
        await message.reply(f"Добро пожаловать, {row[2]}! Чем я могу вам помочь?", reply_markup=markup)



@dp.message_handler(lambda message: message.text and not message.text.startswith("1 -"), state=AddUserStates.first_name)
async def process_first_name(message: types.Message, state: FSMContext):
    first_name = message.text
    user_id = message.from_user.id
    cursor2.execute("UPDATE users SET first_name=? WHERE chat_id=?", (first_name, user_id))
    conn2.commit()
    await state.finish()
    await cmd_start(message)





@dp.message_handler(lambda message: message.text.strip() == "1 - добавить транзакцию", state=None)
async def add_transaction(message: types.Message):
    await AddTransactionStates.patient_name.set()
    await message.reply("Введите ФИО пациента:")

@dp.message_handler(lambda message: message.text and not message.text.startswith("1 -"), state=AddTransactionStates.patient_name)
async def process_patient_name(message: types.Message, state: FSMContext):
    patient_name = message.text
    await state.update_data(patient_name=patient_name)
    await message.reply("Какую услугу оказывали?")
    await AddTransactionStates.next()

@dp.message_handler(lambda message: message.text and not message.text.startswith("1 -"), state=AddTransactionStates.service)
async def process_service(message: types.Message, state: FSMContext):
    service = message.text
    await state.update_data(service=service)

    await AddTransactionStates.next()
    await message.reply("Введите стоимость услуги:")

@dp.message_handler(lambda message: message.text and not message.text.startswith("1 -"), state=AddTransactionStates.service_cost)
async def process_service_cost(message: types.Message, state: FSMContext):
    service_cost = float(message.text)
    await state.update_data(service_cost=service_cost)

    await AddTransactionStates.next()
    await message.reply("Введите процент заработка с этой услуги:")

@dp.message_handler(lambda message: message.text and not message.text.startswith("1 -"), state=AddTransactionStates.percentage)
async def process_percentage(message: types.Message, state: FSMContext):
    percentage = float(message.text)
    user_data = await state.get_data()
    
    patient_name = user_data["patient_name"]
    service = user_data["service"]
    service_cost = user_data["service_cost"]

    await state.update_data(percentage=percentage)
    
    # Ask for confirmation
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Да", "Нет")
    message_text = text(f"Добавить транзакцию: \n\n Пациент: ", patient_name, "\n Услуга: ", service, "\n Стоимость: ", service_cost, "₽\n Процент: ", percentage, "%\n\n","Подтвердить ввод?"
    )
    await message.reply(message_text, reply_markup=markup)
    
    await AddTransactionStates.confirmation.set()

@dp.message_handler(lambda message: message.text and not message.text.startswith("1 -"), state=AddTransactionStates.confirmation)
async def process_confirmation(message: types.Message, state: FSMContext):
    confirmation = message.text.lower()
    if confirmation == "да":
        user_data = await state.get_data()
        user_chat_id = message.chat.id
        patient_name = user_data["patient_name"]
        service = user_data["service"]
        service_cost = user_data["service_cost"]
        percentage = user_data["percentage"]

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        cursor.execute("INSERT INTO transactions (user_chat_id, patient_name, service, service_cost, percentage, date) VALUES (?, ?, ?, ?, ?, ?)",
        (user_chat_id, patient_name, service, service_cost, percentage, today))
        conn.commit()

        await state.finish()
        await message.reply("Спасибо, данные сохранены")
        await cmd_start(message)
    else:
        await state.finish()
        await cmd_start(message)

@dp.message_handler(lambda message: message.text == "2 - показать зарплату за этот месяц")
async def show_current_month_salary(message: types.Message):
    today = datetime.datetime.now()
    user_chat_id = message.chat.id
    start_date = today.replace(day=1).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    salary = await calculate_salary(user_chat_id, start_date, end_date)
    await message.reply(f"Зарплата за этот месяц: {salary:.2f}₽")
@dp.message_handler(lambda message: message.text == "3 - показать зарплату за предыдущий месяц")
async def show_previous_month_salary(message: types.Message):
    today = datetime.datetime.now()
    end_date = today.replace(day=1) - datetime.timedelta(days=1)
    start_date = end_date.replace(day=1)
    user_chat_id = message.chat.id
    start_date = start_date.strftime("%Y-%m-%d")
    end_date = end_date.strftime("%Y-%m-%d")
    salary = await calculate_salary(user_chat_id, start_date, end_date)
    await message.reply(f"Зарплата за предыдущий месяц: {salary:.2f}₽")

@dp.message_handler(lambda message: message.text == "4 - пациенты за этот месяц")
async def patients_handler(message: types.Message):
    # Получаем данные из базы данных
    user_chat_id = message.chat.id
    data = get_patients_data_for_current_month(user_chat_id)
    
    # Отправляем сообщения с информацией о каждом пациенте
    for patient_data in data:
        date = patient_data["date"]
        fio = patient_data["fio"]
        service = patient_data["service"]
        cost = patient_data["cost"]
        percent = patient_data["percent"]
        earnings = cost * percent / 100
        
        message_text = f"Дата приёма: {date}\nФИО пациента: {fio}\nУслуга: {service}\nСтоимость: {cost}\nПроцент заработка: {percent}\n Заработок: {earnings:.2f}₽"
        await message.answer(message_text)


@dp.message_handler(lambda message: message.text == "5 - очистить все данные", state=None)
async def confirm_delete_data(callback_query: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Да", callback_data="confirm_delete_yes"),
        InlineKeyboardButton("Нет", callback_data="confirm_delete_no"),
    )
    await bot.send_message(
        chat_id=callback_query.from_user.id,
        text="Вы уверены? Данное действие удалит все данные!",
        reply_markup=keyboard,
    )
    await ConfirmDeleteStates.confirm_delete.set()


@dp.callback_query_handler(lambda c: c.data == "confirm_delete_yes", state=ConfirmDeleteStates.confirm_delete)
async def confirm_delete_data_again(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Да", callback_data="confirm_delete_yes_again"),
        InlineKeyboardButton("Нет", callback_data="confirm_delete_no_again"),
    )
    await bot.send_message(
        chat_id=callback_query.from_user.id,
        text="Вы точно уверены?! Данные можно потерять безвозвратно!",
        reply_markup=keyboard,
    )
    await ConfirmDeleteStates.next()


@dp.callback_query_handler(lambda c: c.data == "confirm_delete_yes_again", state=ConfirmDeleteStates.confirm_delete_again)
async def delete_data(callback_query: types.CallbackQuery, state: FSMContext):
    user_chat_id = callback_query.from_user.id
    cursor.execute("DELETE FROM transactions WHERE user_chat_id = ?", (user_chat_id,))
    conn.commit()
    sticker_id = "CAACAgUAAxkBAAEIoM1kPrJgUDUcDaE8eUglGJrpvzvd5gACsgIAAhExQFfgcZ-2saVC8S8E"
    await bot.send_sticker(chat_id=callback_query.from_user.id, sticker=sticker_id)
    await bot.send_message(chat_id=callback_query.from_user.id, text="Ваши данные очищены!")
    await state.finish()


@dp.callback_query_handler(lambda c: c.data in ["confirm_delete_no", "confirm_delete_no_again"], state=ConfirmDeleteStates)
async def cancel_delete_data(callback_query: types.CallbackQuery, state: FSMContext):
    sticker_id = "CAACAgIAAxkBAAEIoMlkPq7RTosuHEecO_pjFD7H3M7M9AAC4woAAoQAAahLjp6mmWkh5X4vBA"
    await bot.send_sticker(chat_id=callback_query.from_user.id, sticker=sticker_id)
    await state.finish()

async def calculate_salary(user_chat_id, start_date, end_date):
    cursor.execute("SELECT service_cost, percentage FROM transactions WHERE user_chat_id = ? AND date BETWEEN ? AND ?",
    (user_chat_id, start_date, end_date))
    rows = cursor.fetchall()
    if rows:
        total_salary = sum(row[0] * row[1] / 100 for row in rows)
    else:
        total_salary = 0
    return total_salary

def get_patients_data_for_current_month(user_chat_id):
    conn = sqlite3.connect("transactions.db")
    cursor = conn.cursor()

    now = datetime.datetime.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_month = now.replace(day=1, month=now.month+1, hour=0, minute=0, second=0, microsecond=0)
    query = "SELECT date, patient_name, service, service_cost, percentage FROM transactions WHERE user_chat_id = ? AND date BETWEEN ? AND ?"
    cursor.execute(query, (user_chat_id, start_of_month, end_of_month))
    data = [{"date": row[0], "fio": row[1], "service": row[2], "cost": row[3], "percent": row[4]} for row in cursor.fetchall()]
    conn.close()
    
    return data

async def on_startup(dp):
    await bot.send_message(chat_id=104553486, text='Бот запущен!')

async def on_shutdown(dp):
    await bot.send_message(chat_id=104553486, text='Бот остановлен!')
    conn.close()
    await bot.delete_webhook()
    await bot.close()

if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
