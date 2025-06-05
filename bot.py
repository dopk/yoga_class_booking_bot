import logging
from datetime import datetime
import re

from apscheduler.schedulers.background import BackgroundScheduler
from prometheus_client import start_http_server
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from config import BOT_TOKEN, ADMINS
from monitoring import *
from core.models import *
from services import *

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы для состояний ConversationHandler
(
    ENTER_STUDIO_NAME,
    ENTER_STUDIO_ADDRESS,
    ENTER_STUDIO_CAPACITY,
    ENTER_STUDIO_HAS_SHOWER,
    ENTER_CLASS_STUDIO,
    ENTER_CLASS_TIME,
    ENTER_CLASS_DURATION,
    ENTER_CLASS_CAPACITY
) = range(8)


# region Helpers
async def get_user(update: Update) -> User:
    """Get or create user in database."""
    if not update.effective_user:
        raise ValueError("Effective user not found")

    user = update.effective_user
    db_user, created = UserService.get_or_create(
        messenger_id=user.id,
        display_name=user.full_name,
        username=user.username)

    if created:
        logger.info("New user registered: %s", user.id)
    return db_user


async def get_user_from_query(query) -> User:
    """Получение пользователя из callback query."""
    return await get_user(query.update)


def is_admin(user: User) -> bool:
    """Ceck is user admin."""
    return user.messenger_id in ADMINS

def check_yes(entered_str: str) -> bool:
    """Check string contains yes"""
    words = re.findall(r'\w+', str(entered_str).lower())
    return any(word in {"да", "yes", "true", "1"} for word in words)

def check_no(entered_str: str) -> bool:
    """Check string contains no"""
    words = re.findall(r'\w+', str(entered_str).lower())
    return any(word in {"нет", "no", "false", "0"} for word in words)

async def send_notification(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str):
    """Send notification to user."""
    await context.bot.send_message(chat_id=user_id, text=text)

def create_reply_keyboard(buttons_list: list) -> ReplyKeyboardMarkup:
    """Create Reply Keybord from buttons list."""
    logger.debug("Creating reply keyboard with buttons: %s", buttons_list)
    return ReplyKeyboardMarkup(buttons_list, resize_keyboard=True)

def create_inline_keyboard(buttons_list: list) -> InlineKeyboardMarkup:
    """Create  Inline Keybord from buttons list."""
    return InlineKeyboardMarkup(buttons_list)
# endregion

# region Handlers
@track_command('start')
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /start - main menu."""
    try:
        commands_counter.labels(command='start').inc()
        user = await get_user(update)

        # Формируем кнопки меню в зависимости от роли пользователя
        buttons = [["📅 Расписание", "🎟 Мои записи"]]

        if is_admin(user):
            buttons.append(["👑 Админ-панель"])
        if user.is_teacher:
            buttons.extend([
                ["🏟️ Редактировать студии"],
                ["🎓 Управление занятиями"]
            ])
        buttons.append(["🎟 Вернуться в меню"])

        logger.debug(f"Creating menu for user {user.messenger_id} with buttons: {buttons}")

        text = f"Привет, {user.display_name}!\nВыберите действие из меню:"
        await update.message.reply_text(text, reply_markup=create_reply_keyboard(buttons))
    except Exception as e:
        errors_counter.inc()
        logger.error(f"Error in handle_message: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при обработке запроса")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text message (menu buttons) handler."""
    user = await get_user(update)
    if not update.message or not update.message.text:
        await fallback_handler(update, context)
        return
    text = update.message.text
    logger.info(f"Received message: {text}")

    if text == "🎟 Вернуться в меню":
        await start(update, context)
        return

    # Map button text to func
    handlers = {
        "📅 Расписание": (show_schedule, 'schedule'),
        "🎟 Мои записи": (show_my_bookings, 'my_bookings'),
        "👑 Админ-панель": (admin_panel, 'admin_panel'),
        "🙋‍♀️ Добавить учителя": (show_teacher_selection, 'teacher_selection'),
        "🎓 Управление занятиями": (yoga_class_panel, 'yoga_class_panel'),
        "🏟️ Редактировать студии": (studios_management_panel, 'studios_management_panel')
    }

    if text in handlers:
        handler, metric_name = handlers[text]

        # Проверка прав для административных функций
        if text in ["👑 Админ-панель", "🙋‍♀️ Добавить учителя"] and not is_admin(user):
            await update.message.reply_text("❌ Доступ запрещен")
            return

        # Проверка прав для функций преподавателя
        if text in ["🎓 Управление занятиями", "🏟️ Редактировать студии"] and not user.is_teacher:
            await update.message.reply_text("❌ Доступ запрещен")
            return

        if metric_name:
            commands_counter.labels(command=metric_name).inc()

        await handler(update, context)
    else:
        await update.message.reply_text("Я не понимаю эту команду. Используйте меню.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for inline-buttons."""
    query = update.callback_query
    logger.info(f"Received callback: {query.data}")
    await query.answer()

    try:
        if query.data.startswith(('confirm_', 'reject_')):
            await handle_booking_decision(query, context)

        elif query.data.startswith('teacher_page_'):
            page = int(query.data.split('_')[2])
            await show_teacher_selection(update, context, page)

        elif query.data.startswith('select_teacher_'):
            messenger_id = int(query.data.split('_')[2])
            await handle_teacher_selection(query, context, messenger_id)

    except Exception as e:
        errors_counter.inc()
        logger.error(f"Error in callback handler: {e}")
        await query.answer("⚠️ Произошла ошибка, попробуйте позже")

async def handle_booking_decision(query, context):
    """Handler for bookin decision."""
    action, _, booking_id = query.data.partition('_')

    try:
        booking = Booking.get_by_id(booking_id)
        user = await get_user_from_query(query)

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
        await send_notification(context, booking.user.messenger_id, notify_text)

    except DoesNotExist:
        errors_counter.inc()
        logger.error(f"Booking {booking_id} not found")

async def handle_teacher_selection(query, context, messenger_id):
    """Обработка выбора пользователя в качестве учителя."""
    target_user = User.get(User.messenger_id == messenger_id)

    if target_user.is_teacher:
        await query.answer("⚠️ Этот пользователь уже учитель")
        return

    target_user.is_teacher = True
    target_user.save()

    await query.edit_message_text(
        text=f"✅ Пользователь @{target_user.username} успешно назначен учителем!"
    )
    await send_notification(
        context,
        target_user.messenger_id,
        "🎉 Вы были назначены учителем в системе!"
    )

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Studio coise pagination."""
    query = update.callback_query
    await query.answer()

    current_page = context.user_data['current_page']

    if query.data == "studio_next_page":
        current_page += 1
    elif query.data == "studio_prev_page":
        current_page -= 1

    context.user_data['current_page'] = current_page
    return await show_studio_page(update, context, current_page)

async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для необработанных сообщений."""
    logger.warning(f"Unhandled message: {update.message.text}")
    await update.message.reply_text(
        "Извините, я не понял ваш запрос. Пожалуйста, используйте кнопки меню.",
        reply_markup=create_reply_keyboard([["🎟 Вернуться в меню"]])
    )
# endregion


# region panels
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel."""
    buttons = [["🙋‍♀️ Добавить учителя", "🎟 Вернуться в меню"]]
    await update.message.reply_text(
        "Выберите действие из меню:",
        reply_markup=create_reply_keyboard(buttons)
    )

async def yoga_class_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yoga class management panel."""
    buttons = [["📅 Добавить занятие", "🎟 Вернуться в меню"]]
    await update.message.reply_text(
        "Выберите действие из меню:",
        reply_markup=create_reply_keyboard(buttons)
    )

async def studios_management_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель управления студиями."""
    buttons = [["🏟️ Добавить студию", "🎟 Вернуться в меню"]]
    await update.message.reply_text(
        "Выберите действие из меню:",
        reply_markup=create_reply_keyboard(buttons)
    )

@track_command('show_teacher_selection')
async def show_teacher_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Show users to make teacher."""
    user = await get_user(update)
    if not is_admin(user):
        await update.message.reply_text("❌ Доступ запрещен")
        return

    page_size = 10
    non_teachers = list(User.select().where(User.is_teacher == False)
                        .order_by(User.username)
                        .paginate(page, page_size))

    # Create buttons with users
    buttons = [
        [InlineKeyboardButton(
            f"{user.display_name} (@{user.username})",
            callback_data=f'select_teacher_{user.messenger_id}'
        )]
        for user in non_teachers
    ]

    # Navigate buttons:
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'teacher_page_{page-1}'))
    if len(non_teachers) == page_size:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'teacher_page_{page+1}'))

    if nav_buttons:
        buttons.append(nav_buttons)

    reply_markup = create_inline_keyboard(buttons)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text="Выберите пользователя для назначения учителем:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Выберите пользователя для назначения учителем:",
            reply_markup=reply_markup
        )
# endregion


# region Conversations add studio
@track_command('start_adding_studio')
async def start_adding_studio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding studio process."""
    user = await get_user(update)
    if not user.is_teacher:
        await update.message.reply_text("❌ Доступно только учителям")
        return ConversationHandler.END

    await update.message.reply_text("Отправьте мне название студии")
    return ENTER_STUDIO_NAME

@track_command('get_studio_name')
async def get_studio_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get studio name."""
    context.user_data['studio_name'] = update.message.text
    await update.message.reply_text("Отправьте мне адрес студии:")
    return ENTER_STUDIO_ADDRESS

@track_command('get_studio_address')
async def get_studio_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get studio address."""
    context.user_data['studio_address'] = update.message.text
    await update.message.reply_text("Отправьте мне вместимость студии (максимальное количество человек):")
    return ENTER_STUDIO_CAPACITY

@track_command('get_studio_capacity')
async def get_studio_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get studio capacity."""
    try:
        capacity = int(update.message.text)
        if capacity <= 0:
            raise ValueError
        context.user_data['capacity'] = capacity
        await update.message.reply_text("В студии есть душ (да/нет)?:")
        return ENTER_STUDIO_HAS_SHOWER
    except ValueError:
        await update.message.reply_text("❌ Вместимость должна быть положительным числом. Попробуйте еще раз.")
        return ENTER_STUDIO_CAPACITY

@track_command('get_studio_has_shower')
async def get_studio_has_shower(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get is studio has shower and create studio."""
    user = await get_user(update)
    name = context.user_data.get('studio_name')
    address = context.user_data.get('studio_address')
    capacity = context.user_data.get('capacity')
    has_shower_str = update.message.text
    created_by = User.get(User.messenger_id == user.messenger_id).id

    if not name:
        await update.message.reply_text("❌ Ошибка: название не получил. Добавление студии отменено")
        return ConversationHandler.END
    if not address:
        await update.message.reply_text("❌ Ошибка: адрес не получил. Добавление студии отменено")
        return ConversationHandler.END
    try:
        capacity = int(capacity)
    except ValueError:
        errors_counter.inc()
        await update.message.reply_text("❌ Ошибка: Вместимость должна быть числом. Добавление студии отменено")
        return ConversationHandler.END
    if check_yes(has_shower_str):
        has_shower = 1
    elif check_no(has_shower_str):
        has_shower = 0
    else:
        await update.message.reply_text("❌ Ошибка: Не смог понять есть ли в студии душ. Добавление студии отменено")

    try:
        Studio.create(
            name=name,
            address=address,
            capacity=capacity,
            has_shower=has_shower,
            created_by=created_by)
        await update.message.reply_text(f"✅ Студия '{name}' успешно добавлена")
    except IntegrityError:
        errors_counter.inc()
        await update.message.reply_text("❌ Не удалось создать студию, попробуйте ещё раз.")

    context.user_data.clear()
    return ConversationHandler.END


@track_command('cancel_adding_studio')
async def cancel_adding_studio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel adding studio."""
    await update.message.reply_text("❌ Добавление студии отменено")
    context.user_data.clear()
    return ConversationHandler.END
# endregion


# region Conversations add yoga_class
@track_command('start_creating_yoga_class')
async def start_creating_yoga_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start of creating studio."""
    user = await get_user(update)
    if not user.is_teacher:
        await update.message.reply_text("❌ Доступно только учителям")
        return ConversationHandler.END

    studios = list(Studio.select().order_by(Studio.created_at))
    if not studios:
        await update.message.reply_text("❌ Нет доступных студий. Сначала создайте студию")
        return ConversationHandler.END

    context.user_data['studio_pages'] = [studios[i:i+10] for i in range(0, len(studios), 10)]
    context.user_data['current_page'] = 0

    return await show_studio_page(update, context, 0)


async def show_studio_page(update, context, page_number):
    """Show studios page."""
    pages = context.user_data['studio_pages']
    buttons = [
        [InlineKeyboardButton(studio.name, callback_data=f"select_studio_{studio.id}")]
        for studio in pages[page_number]
    ]

    nav_buttons = []
    if page_number > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data="studio_prev_page"))
    if page_number < len(pages) - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data="studio_next_page"))

    if nav_buttons:
        buttons.append(nav_buttons)

    reply_markup = create_inline_keyboard(buttons)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            "Выберите студию:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Выберите студию:",
            reply_markup=reply_markup
        )
    return ENTER_CLASS_STUDIO

@track_command('select_studio')
async def select_studio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Studio selection."""
    query = update.callback_query
    await query.answer()

    studio_id = int(query.data.split("_")[2])
    context.user_data['studio_id'] = studio_id

    await query.edit_message_text(
        "Отправьте дату и время начала занятия в формате: ДД.ММ.ГГГГ ЧЧ:ММ (например 22.11.2027 11:34):"
    )
    return ENTER_CLASS_TIME

@track_command('get_class_time')
async def get_class_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение времени начала занятия."""
    try:
        start_time = datetime.strptime(update.message.text, "%d.%m.%Y %H:%M")

        if start_time < datetime.now():
            await update.message.reply_text("❌ Начало занятия не может быть в прошлом. Введите будущую дату.")
            return ENTER_CLASS_TIME

        context.user_data['start_time'] = start_time
        await update.message.reply_text("Отправьте мне продолжительность занятия в минутах:")
        return ENTER_CLASS_DURATION

    except ValueError:
        errors_counter.inc()
        await update.message.reply_text("❌ Не смог распознать дату и время. Попробуйте ещё раз, я понимаю формат ДД.ММ.ГГГГ ЧЧ:ММ")
        return ENTER_CLASS_TIME

@track_command('get_class_duration')
async def get_class_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get class duration."""
    try:
        duration = int(update.message.text)

        if duration < 15 or duration > 240:
            await update.message.reply_text("❌ е смог распознять продолжительнотсь занятия, отправьте, пожалуйста только число цифрами (а ешё мой программист решил, что занятие короче 15 минут не имеет смысла, а длиннее 240 никто не выдержит).")
            return ENTER_CLASS_DURATION

        context.user_data['duration'] = duration

        studio = Studio.get_by_id(context.user_data['studio_id'])
        await update.message.reply_text(
            f"Отправьте максимальное количество участников. Вместимость зала: {studio.capacity}"
        )
        return ENTER_CLASS_CAPACITY

    except ValueError:
        await update.message.reply_text("❌ Не смог распознять продолжительнотсь занятия, отправьте, пожалуйста только число цифрами (в минутах).")
        return ENTER_CLASS_DURATION

@track_command('get_class_capacity')
async def get_class_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get max yoga class students count."""
    try:
        capacity = int(update.message.text)
        if capacity < 1:
            raise ValueError

        user = await get_user(update)
        yoga_class = YogaClass.create(
            name="Занятие",  # TODO: enter class name
            studio=context.user_data['studio_id'],
            teacher=user.id,
            start_time=context.user_data['start_time'],
            duration=context.user_data['duration'],
            capacity=capacity
        )

        await update.message.reply_text(f"✅ Занятие на {yoga_class.start_time} успешно создано!")
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Количество участников должно быть положительным числом. Отправьте снова.")
        return ENTER_CLASS_CAPACITY
    except Exception as e:
        errors_counter.inc()
        logger.error(f"Error creating yoga class: {e}")
        await update.message.reply_text("❌ Ошибка при создании занятия. Попробуйте снова.")
        return ConversationHandler.END

@track_command('cancel_creating_yoga_class')
async def cancel_creating_yoga_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена процесса создания занятия."""
    await update.message.reply_text("❌ Создание занятия отменено")
    context.user_data.clear()
    return ConversationHandler.END
# endregion


@track_command('show_schedule')
async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ расписания занятий."""
    try:
        # Получаем будущие занятия
        classes = YogaClass.select().where(
            YogaClass.start_time > datetime.now()
        ).order_by(YogaClass.start_time)

        if not classes:
            await update.message.reply_text("На данный момент нет запланированных занятий.")
            return

        text = "📅 Расписание занятий:\n\n"
        for class_ in classes:
            text += (
                f"🏷 {class_.name}\n"
                f"⏰ {class_.start_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"🏟 {class_.studio.name}\n"
                f"👨‍🏫 Преподаватель: {class_.teacher.display_name}\n"
                f"🔢 Мест: {Booking.select().where(Booking.yoga_class == class_, Booking.status == 'confirmed').count()}/{class_.capacity}\n\n"
            )

        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Error showing schedule: {e}")
        await update.message.reply_text("❌ Произошла ошибка при загрузке расписания.")

@track_command('show_my_bookings')
async def show_my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ броней пользователя."""
    try:
        user = await get_user(update)
        bookings = Booking.select().where(
            Booking.user == user,
            Booking.yoga_class.start_time > datetime.now()
        ).order_by(Booking.yoga_class.start_time)

        if not bookings:
            await update.message.reply_text("У вас нет активных броней.")
            return

        text = "🎟 Ваши брони:\n\n"
        for booking in bookings:
            status_emoji = "🟢" if booking.status == 'confirmed' else "🟡" if booking.status == 'pending' else "🔴"
            text += (
                f"{status_emoji} {booking.yoga_class.name}\n"
                f"⏰ {booking.yoga_class.start_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"🏟 {booking.yoga_class.studio.name}\n"
                f"Статус: {booking.status}\n\n"
            )

        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Error showing bookings: {e}")
        await update.message.reply_text("❌ Произошла ошибка при загрузке ваших броней.")


# bot start
def setup_handlers(application):
    """Настройка обработчиков команд и сообщений."""
    # Обработчик команды /start
    logger.info("Setting up handlers...")
    application.add_handler(CommandHandler("start", start))
    logger.info("Added start handler")


    # Обработчики для добавления студии
    studio_conversation = ConversationHandler(
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
        conversation_timeout=1200
    )

    # Обработчики для создания занятия
    class_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^📅 Добавить занятие$"), start_creating_yoga_class)
        ],
        states={
            ENTER_CLASS_STUDIO: [
                CallbackQueryHandler(select_studio, pattern=r"^select_studio_\d+$"),
                CallbackQueryHandler(handle_pagination, pattern=r"^(studio_next_page|studio_prev_page)$")
            ],
            ENTER_CLASS_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_time)],
            ENTER_CLASS_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_duration)],
            ENTER_CLASS_CAPACITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_capacity)]
        },
        fallbacks=[CommandHandler('cancel', cancel_creating_yoga_class)],
        conversation_timeout=1200
    )

    # Основные обработчики сообщений и callback-запросов
    application.add_handler(studio_conversation)
    application.add_handler(class_conversation)
    application.add_handler(MessageHandler(filters.TEXT, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

def main():
    """Основная функция запуска бота."""
    try:
        # Инициализация метрик Prometheus
        start_http_server(8000)
        logger.info("Prometheus metrics server started on port 8000")

        # Инициализация планировщика задач
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            func=update_database_metrics,
            trigger='interval',
            minutes=15
        )
        scheduler.start()

        # Инициализация базы данных
        initialize_db()

        # Создание и настройка приложения бота
        application = Application.builder().token(BOT_TOKEN).build()
        setup_handlers(application)

        logger.info("Bot started successfully")
        # Запуск бота
        application.run_polling()

    except Exception as e:
        errors_counter.inc()
        logger.error(f"Fatal error: {e}")
        raise

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок."""
    logger.error(f"Update {update} caused error {context.error}")

if __name__ == "__main__":
    main()
