import logging
from email.policy import default
import re

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
    ConversationHandler
)
from models import *
from config import BOT_TOKEN, ADMINS

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

(
    ENTER_STUDIO_NAME,
    ENTER_STUDIO_ADDRESS,
    ENTER_STUDIO_CAPACITY,
    ENTER_STUDIO_HAS_SHOWER
) = range(4)

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


def check_yes(entered_str: str):
    words = re.findall(r'\w+', str(entered_str).lower())
    return any (word in {"да", "yes", "true", "1"} for word in words)


def check_no(entered_str: str):
    words = re.findall(r'\w+', str(entered_str).lower())
    return any (word in {"нет", "no", "false", "0"} for word in words)


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
    if is_admin(user):
        buttons.append(["👑 Админ-панель"])
    if user.is_teacher:
        buttons.append(["🏟️ Редактировать студии"])
    if user.is_teacher:
        buttons.append(["🎓 Управление занятиями"])

    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    text = update.message.text

    if text == "📅 Расписание":
        await show_schedule(update, context)
    elif text == "🎟 Мои записи":
        await show_my_bookings(update, context)
    elif text == "👑 Админ-панель" and is_admin(user):
        await admin_panel(user, update, context)
    elif text == "🙋‍♀️ Добавить учителя" and is_admin(user):
        await show_teacher_selection(update, context)
    elif text == "🎟 Вернуться в меню":
        await start(update, context)
    elif text == "🎓 Управление занятиями" and user.is_teacher:
        await yoga_class_panel(user, update, context) # TODO: dodelat'
    elif text == "🏟️ Редактировать студии" and user.is_teacher:
        await studios_management_panel(user, update, context) # TODOL dodelat'


async def admin_panel(user, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(user):
        buttons = [["🙋‍♀️ Добавить учителя", "🎟 Вернуться в меню"]]
    else:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    text = "Выберите действие из меню:"
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def yoga_class_panel(user, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if user.is_teacher:
        buttons = [["📅 Добавить занятие", "🎟 Вернуться в меню"]]
    else:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    text = "Выберите действие из меню:"
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def studios_management_panel(user, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if user.is_teacher:
        buttons = [["🏟️ Добавить студию", "🎟 Вернуться в меню"]]
    else:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    text = "Выберите действие из меню:"
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def show_teacher_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    user = await get_user(update)
    if not is_admin(user):
        await update.message.reply_text("❌ Доступ запрещен")
        return
    
    page_size = 10
    offset = page * page_size

    # Get users, not teachers:
    non_teachers = list(User.select().where(User.is_teacher == False)
                        .order_by(User.username)
                        .offset(offset)
                        .limit(page_size))
    buttons = []
    for user in non_teachers:
        user_label = f"{user.display_name} (@{user.username})"
        buttons.append([InlineKeyboardButton(user_label, callback_data=f'select_teacher_{user.telegram_id}')])

    # Navigate buttons:
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'teacher_page_{page-1}'))
    if len(non_teachers) == page_size:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'teacher_page_{page+1}'))

    if nav_buttons:
        buttons.append(nav_buttons)
    replay_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        query = update.callback_query
        await query.edit_message_text(
            text="Выберите пользователя для назначения учителем:",
            reply_markup=replay_markup
        )
    else:
        await update.message.reply_text(
            "Выберите пользователя для назначения учителем:",
            reply_markup=replay_markup
        )
      

async def create_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    if not user.is_teacher:
        await update.message.reply_text("❌ Доступно только учителям")
        return

    # TODO: Здесь должна быть логика выбора студии, времени и т.д.

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
    # 
    data = query.data

    try:
        if data.startswith('confirm_') or data.startswith('reject_'):
            action, _, booking_id = query.data.partition('_')
            try: 
                booking = Booking.get_by_id(booking_id)
            except DoesNotExist:
                logger.error(f"Booking {booking_id} not found")
                return
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
        elif data.startswith('teacher_page_'):
            page = int(data.split(' ')[2])
            await show_teacher_selection(update, context, page)

        elif data.startswith('select_teacher_'):
            telegram_id = int(data.split('_')[2])
            print(telegram_id)
            target_user = User.get(User.telegram_id == telegram_id)
            if target_user.is_teacher:
                await query.answer("⚠️ Этот пользователь уже учитель")
                return
            print(target_user.telegram_id)
            target_user.is_teacher = 1
            target_user.save()

            await query.edit_message_text(
                text=f"✅ Пользователь @{target_user.username} успешно назначен учителем!"
            )
            await send_notification(
                context,
                target_user.telegram_id,
                "🎉 Вы были назначены учителем в системе!"
            )
    except User.DoesNotExist:
        await query.answer("❌ Пользователь не найден")
    except ValueError as e:
        logger.error(f"Invalid data format: {e}")
        await query.answer("⚠️ Ошибка формата данных")
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        await query.answer("⚠️ Произошла ошибка, попробуйте позже")

# endregion


# region Conversations add studio
async def start_adding_studio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    if not user.is_teacher:
        await update.message.reply_text("❌ Доступно только учителям")
        return ConversationHandler.END
    await update.message.reply_text("Отправьте мне название студии")
    return ENTER_STUDIO_NAME


async def get_studio_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['studio_name'] = update.message.text
    await update.message.reply_text("Отправьте мне адрес студии:")
    return ENTER_STUDIO_ADDRESS


async def get_studio_address(update: Update, context = ContextTypes.DEFAULT_TYPE):
    context.user_data['studio_address'] = update.message.text
    await update.message.reply_text("Отправьте мне сколько студия вмещает человек (максимум):")
    return ENTER_STUDIO_CAPACITY


async def get_studio_capacity(update: Update, context = ContextTypes.DEFAULT_TYPE):
    context.user_data['capacity'] = update.message.text
    await update.message.reply_text("В студии есть душ (да/нет)?:")
    return ENTER_STUDIO_HAS_SHOWER


async def get_studio_has_shower(update: Update, context = ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    name = context.user_data.get('studio_name')
    address = context.user_data.get('studio_address')
    capacity = context.user_data.get('capacity')
    has_shower_str = update.message.text

    if not name:
        await update.message.reply_text("❌ Ошибка: название не получил. Добавление студии отменено")
        return ConversationHandler.END
    if not address:
        await update.message.reply_text("❌ Ошибка: адрес не получил. Добавление студии отменено")
        return ConversationHandler.END
    try:
        capacity = int(capacity)
    except ValueError:
        await update.message.reply_text("❌ Ошибка: Вместимость должна быть числом. Добавление студии отменено")
        return ConversationHandler.END
    if check_yes(has_shower_str):
        has_shower = 1
    elif check_no(has_shower_str):
        has_shower = 0
    else:
        await update.message.reply_text("❌ Ошибка: Не смог понять есть ли в студии душ. Добавление студии отменено")

    created_by = User.get(User.telegram_id == user.telegram_id).id
    try:
        Studio.create(name=name, address=address, capacity=capacity, has_shower=has_shower, created_by=created_by)
        await update.message.reply_text(f"✅ Студия '{name}' успешно добавлена")
    except IntegrityError:
        await update.message.reply_text(f"❌ Не удалось создать студию, попробуйте ещё раз.")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_adding_studio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Добавление студии отменено")
    context.user_data.clear()
    return ConversationHandler.END
# endregion


# region Conversations add yoga_class
#TODO: add yogaclass
#endregion

def main():
    try:
        initialize_db()
        application = Application.builder().token(BOT_TOKEN).build()

        # Регистрация обработчиков
        application.add_handler(CommandHandler("start", start))
        application.add_handler(ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex(r"^🏟️ Добавить студию$"), start_adding_studio)
            ],
            states={
                ENTER_STUDIO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_studio_name)],
                ENTER_STUDIO_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_studio_address)],
                ENTER_STUDIO_CAPACITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_studio_capacity)],
                ENTER_STUDIO_HAS_SHOWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_studio_has_shower)]
            },
            fallbacks=[CommandHandler('cancel', cancel_adding_studio)],
        ))
        application.add_handler(MessageHandler(filters.TEXT, handle_message))
        application.add_handler(CallbackQueryHandler(handle_callback))
        application.add_handler(ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex(r"^🏟️ Добавить студию$"), start_adding_studio)
            ],
            states={
                ENTER_STUDIO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_studio_name)],
                ENTER_STUDIO_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_studio_address)]
            },
            fallbacks=[CommandHandler('cancel', cancel_adding_studio)],
        ))
        application.run_polling()
    except Exception as e:
        logger.error('Fatal error: ', e)


if __name__ == "__main__":
    main()
