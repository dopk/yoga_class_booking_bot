import logging
from email.policy import default

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from models import *
from config import BOT_TOKEN, ADMINS

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# region Helpers
async def get_user(update: Update) -> User:
    if not update.effective_user:
        raise ValueError("Effective user not found")
    user = update.effective_user
    db_user, created = User.get_or_create(
        telegram_id=user.id,
        defaults={
            'display_name': user.full_name or '',
            'username': user.username or ''
        }
    )
    if created:
        logger.info(f"New user registered: {user.id}")
    return db_user


def is_admin(user: User) -> bool:
    return user.telegram_id in ADMINS


async def send_notification(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str):
    await context.bot.send_message(chat_id=user_id, text=text)


# endregion

# region Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    text = (
        f"Привет, {user.display_name}!\n"
        "Выберите действие из меню:"
    )

    buttons = [["📅 Расписание", "🎟 Мои записи"]]
    if user.role == "teacher":
        buttons.append(["🎓 Управление занятиями"])
    if is_admin(user):
        buttons.append(["👑 Админ-панель"])

    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    text = update.message.text

    if text == "📅 Расписание":
        await show_schedule(update, context)
    elif text == "🎟 Мои записи":
        await show_my_bookings(update, context)
    elif text == "🎓 Управление занятиями" and user.is_teacher:
        await manage_classes(update, context)
    elif text == "👑 Админ-панель" and is_admin(user):
        await admin_panel(user, update, context)
    elif text == "📅 Добавить учителя" and is_admin(user):
        await select_and_add_teacher(update, context)
    elif text == "🎟 Вернуться в меню":
        await start(update, context)
    elif text == "🎓 Управление занятиями" and user.is_teacher:
        await start(update, context) #TODO: dodelat'


async def admin_panel(user, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(user):
        buttons = [["📅 Добавить учителя", "🎟 Вернуться в меню"]]
    else:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    text = "Выберите действие из меню:"
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def add_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    if not is_admin(user):
        await update.message.reply_text("❌ Доступ запрещен")
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Использование: /add_teacher <telegram_username>")
        return

    try:
        try:
            target_id = int(args[0])
            target_user = User.get(User.telegram_id == target_id)
        except ValueError:
            await update.message.reply_text("❌ ID должен быть числом")
        target_user.is_teacher = True
        target_user.save()
        await update.message.reply_text("✅ Пользователь назначен учителем")
        await send_notification(context, target_user.telegram_id, "🎉 Вам назначены права учителя!")
    except User.DoesNotExist:
        await update.message.reply_text("❌ Пользователь не найден")


async def create_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    if not user.is_teacher:
        await update.message.reply_text("❌ Доступно только учителям")
        return

    # Здесь должна быть логика выбора студии, времени и т.д.
    # с использованием ConversationHandler или FSM

    # Пример создания класса
    try:
        YogaClass.create(
            studio=studio,
            teacher=user,
            start_time=start_time,
            duration=duration,
            capacity=capacity
        )
        await update.message.reply_text("✅ Занятие создано")
    except IntegrityError as e:
        await update.message.reply_text("❌ Время занятия пересекается с существующим")


async def book_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    # Логика выбора класса и создания брони
    booking = Booking.create(user=user, yoga_class=yoga_class)

    # Уведомление учителю
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{booking.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{booking.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=yoga_class.teacher.telegram_id,
        text=f"Новая бронь от {user.display_name}",
        reply_markup=reply_markup
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if '_' not in query.data:
        logger.error(f"Invalid callback data: {query.data}")
        return
    action, _, booking_id = query.data.partition('_')

    try:
        booking = Booking.get_by_id(booking_id)
    except DoesNotExist:
        logger.error(f"Booking {booking_id} not found")
    user = await get_user(update)

    if booking.yoga_class.teacher != user:
        await query.answer("❌ Нет прав для этого действия")
        return

    if action == "confirm":
        booking.status = 'confirmed'
        text = "Бронь подтверждена"
        notify_text = f"✅ Ваша бронь на {booking.yoga_class.start_time} подтверждена"
    else:
        booking.status = 'rejected'
        text = "Бронь отклонена"
        notify_text = f"❌ Ваша бронь на {booking.yoga_class.start_time} отклонена"

    booking.save()
    await query.answer(text)
    await send_notification(context, booking.user.telegram_id, notify_text)


# endregion

def main():
    try:
        initialize_db()
        application = Application.builder().token(BOT_TOKEN).build()

        # Регистрация обработчиков
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("add_teacher", add_teacher))
        application.add_handler(MessageHandler(filters.TEXT, handle_message))
        application.add_handler(CallbackQueryHandler(handle_callback))

        application.run_polling()
    except Exception as e:
        logger.error('Fatal error: ', e)


if __name__ == "__main__":
    main()