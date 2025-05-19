import logging
from email.policy import default
from functools import wraps
import re

from apscheduler.schedulers.background import BackgroundScheduler
from prometheus_client import start_http_server, Counter, Gauge, Histogram
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
    ENTER_STUDIO_HAS_SHOWER,
    ENTER_CLASS_STUDIO,
    ENTER_CLASS_TIME,
    ENTER_CLASS_DURATION,
    ENTER_CLASS_CAPACITY
) = range(8)


# Инициализация метрик Prometheus
commands_counter = Counter(
    'bot_commands_total', 
    'Total number of commands processed', 
    ['command']
)
errors_counter = Counter('bot_errors_total', 'Total number of errors occurred')
database_entities = Gauge(
    'bot_database_entities',
    'Number of entities in database',
    ['entity']
)
request_duration = Histogram(
    'bot_request_duration_seconds',
    'Duration of bot requests',
    ['command']
)


# region monitorng
def track_command(command_name):
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context):
            start_time = time()
            try:
                result = await func(update, context)
                request_duration.labels(command=command_name).observe(time() - start_time)
                return result
            except Exception as e:
                errors_counter.inc()
                raise
        return wrapper
    return decorator


def update_database_metrics():
    try:
        database_entities.labels(entity='user').set(User.select().count())
        database_entities.labels(entity='studio').set(Studio.select().count())
        database_entities.labels(entity='yoga_class').set(YogaClass.select().count())
        database_entities.labels(entity='booking').set(Booking.select().count())
    except Exception as e:
        logger.error("Error updating database metrics: %s", e)
# endregion


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
        logger.info("New user registered: %s", user.id)
    return db_user


def is_admin(user: User) -> bool:
    return user.telegram_id in ADMINS


def check_yes(entered_str: str):
    words = re.findall(r'\w+', str(entered_str).lower())
    return any (word in {"да", "yes", "true", "1"} for word in words)


def check_no(entered_str: str):
    words = re.findall(r'\w+', str(entered_str).lower())
    return any (word in {"нет", "no", "false", "0"} for word in words)

@track_command('send_notification')
async def send_notification(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str):
    await context.bot.send_message(chat_id=user_id, text=text)
# endregion

# region Handlers
@track_command('start')
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands_counter.labels(command='start').inc()
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
        commands_counter.labels(command='schedule').inc()
        await show_schedule(update, context)
    elif text == "🎟 Мои записи":
        commands_counter.labels(command='my_bookings').inc()
        await show_my_bookings(update, context)
    elif text == "👑 Админ-панель" and is_admin(user):
        commands_counter.labels(command='admin_panel').inc()
        await admin_panel(user, update, context)
    elif text == "🙋‍♀️ Добавить учителя" and is_admin(user):
        commands_counter.labels(command='teacher_selection').inc()
        await show_teacher_selection(update, context)
    elif text == "🎟 Вернуться в меню":
        await start(update, context)
    elif text == "🎓 Управление занятиями" and user.is_teacher:
        commands_counter.labels(command='yoga_class_panel').inc()
        await yoga_class_panel(user, update, context)
    elif text == "🏟️ Редактировать студии" and user.is_teacher:
        commands_counter.labels(command='studios_management_panel').inc()
        await studios_management_panel(user, update, context)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    try:
        if data.startswith('confirm_') or data.startswith('reject_'):
            action, _, booking_id = query.data.partition('_')
            try: 
                booking = Booking.get_by_id(booking_id)
            except DoesNotExist:
                errors_counter.inc()
                logger.error("Booking %s not found", booking_id)
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
        errors_counter.inc()
        await query.answer("❌ Пользователь не найден")
    except ValueError as e:
        errors_counter.inc()
        logger.error("Invalid data format: %s", e)
        await query.answer("⚠️ Ошибка формата данных")
    except Exception as e:
        errors_counter.inc()
        logger.error("Error in callback handler: %s", e)
        await query.answer("⚠️ Произошла ошибка, попробуйте позже")


async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current_page = context.user_data['current_page']
    if query.data == "studio_next_page":
        current_page += 1
    elif query.data == "studio_prev_page":
        current_page -= 1
    context.user_data["current_page"] = current_page
    return await show_studio_page(update, context, current_page)
# endregion


# region panels
@track_command('admin_panel')
async def admin_panel(user, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(user):
        buttons = [["🙋‍♀️ Добавить учителя", "🎟 Вернуться в меню"]]
    else:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    text = "Выберите действие из меню:"
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)


@track_command('yoga_class_panel')
async def yoga_class_panel(user, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if user.is_teacher:
        buttons = [["📅 Добавить занятие", "🎟 Вернуться в меню"]]
    else:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    text = "Выберите действие из меню:"
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)


@track_command('studios_management_panel')
async def studios_management_panel(user, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if user.is_teacher:
        buttons = [["🏟️ Добавить студию", "🎟 Вернуться в меню"]]
    else:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    text = "Выберите действие из меню:"
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)


@track_command('show_teacher_selection')
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
# endregion


# region Conversations add studio
@track_command('start_adding_studio')
async def start_adding_studio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    if not user.is_teacher:
        await update.message.reply_text("❌ Доступно только учителям")
        return ConversationHandler.END
    await update.message.reply_text("Отправьте мне название студии")
    return ENTER_STUDIO_NAME


@track_command('get_studio_name')
async def get_studio_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['studio_name'] = update.message.text
    await update.message.reply_text("Отправьте мне адрес студии:")
    return ENTER_STUDIO_ADDRESS


@track_command('get_studio_address')
async def get_studio_address(update: Update, context = ContextTypes.DEFAULT_TYPE):
    context.user_data['studio_address'] = update.message.text
    await update.message.reply_text("Отправьте мне сколько студия вмещает человек (максимум):")
    return ENTER_STUDIO_CAPACITY


@track_command('get_studio_capacity')
async def get_studio_capacity(update: Update, context = ContextTypes.DEFAULT_TYPE):
    context.user_data['capacity'] = update.message.text
    await update.message.reply_text("В студии есть душ (да/нет)?:")
    return ENTER_STUDIO_HAS_SHOWER


@track_command('get_studio_has_shower')
async def get_studio_has_shower(update: Update, context = ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    name = context.user_data.get('studio_name')
    address = context.user_data.get('studio_address')
    capacity = context.user_data.get('capacity')
    has_shower_str = update.message.text
    created_by = User.get(User.telegram_id == user.telegram_id).id

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
    await update.message.reply_text("❌ Добавление студии отменено")
    context.user_data.clear()
    return ConversationHandler.END
# endregion


# region Conversations add yoga_class
@track_command('start_creating_yoga_class')
async def start_creating_yoga_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update)
    if not user.is_teacher:
        await update.message.reply_text("❌ Доступно только учителям")
        return ConversationHandler.END

    studios = list(Studio.select().order_by(Studio.created_at))
    if not studios:
        await update.message.reply_text("❌ Нет доступных студий. Сначала создайте студию")
        return ConversationHandler.END
    
    page_size = 10
    pages = [studios[i:i+page_size] for i in range(0, len(studios), page_size)]
    context.user_data['studio_pages'] = pages
    context.user_data['current_page'] = 0

    return await show_studio_page(update, context, 0)


@track_command('show_studio_page')
async def show_studio_page(update, context, page_number):
    pages = context.user_data['studio_pages']
    current_page = page_number
    buttons = []
    for studio in pages[current_page]:
        buttons.append([InlineKeyboardButton(studio.name, callback_data=f"select_studio_{studio.id}")])
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data="studio_prev_page"))
    if current_page < len(pages) - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data="studio_next_page"))
    if nav_buttons:
        buttons.append(nav_buttons)
    reply_markup = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.edit_message_text("Выберите студию:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Выберите студию:", reply_markup=reply_markup)
    return ENTER_CLASS_STUDIO


@track_command('select_studio')
async def select_studio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    studio_id = int(query.data.split("_")[2])
    context.user_data['studio_id'] = studio_id

    await query.edit_message_text("Отправьте мне дату и время начала занятия в формате: ДД.ММ.ГГГГ ЧЧ:ММ (например 22.11.2027 11:34):")
    return ENTER_CLASS_TIME


@track_command('get_class_time')
async def get_class_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        datetime_str = update.message.text
        start_time = datetime.strptime(datetime_str, "%d.%m.%Y %H:%M")
        context.user_data['start_time'] = start_time
        if start_time < datetime.now():
            await update.message.reply_text("Начало занятия не может быть в прошлом, введите дату будущего занятия (в формате: ДД.ММ.ГГГГ ЧЧ:ММ)")
            return ENTER_CLASS_TIME
    except ValueError:
        errors_counter.inc()
        await update.message.reply_text("❌ Не смог распознать дату и время. Попробуйте ещё раз, я понимаю формат ДД.ММ.ГГГГ ЧЧ:ММ")
        return ENTER_CLASS_TIME

    await update.message.reply_text("Отправьте мне продолжительность занятия в минутах:")
    return ENTER_CLASS_DURATION


@track_command('get_class_duration')
async def get_class_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        duration = int(update.message.text)
        if duration < 15 or duration > 240:
            raise ValueError
        context.user_data['duration'] = duration
    except ValueError:
        errors_counter.inc()
        await update.message.reply_text("❌ Не смог распознять продолжительнотсь занятия, отправьте, пожалуйста только число цифрами (а ешё мой программист решил, что занятие короче 15 минут не имеет смысла, а длиннее 240 никто не выдержит)")
        return ENTER_CLASS_DURATION
    studio_capacity = Studio.get_by_id(context.user_data['studio_id']).capacity
    await update.message.reply_text(f"Отправьте мне максимальное количество участников занятия. Для зала указна вместимость {studio_capacity}, но можно указать и больше")
    return ENTER_CLASS_CAPACITY


@track_command('get_class_capacity')
async def get_class_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        capacity = int(update.message.text)
        if capacity < 1:
            raise ValueError
    except ValueError:
        errors_counter.inc()
        await update.message.reply_text("❌ Не смог распознать маскимальное количество участников, отправьте мне количество в виде числа, только цифры")
        return ENTER_CLASS_CAPACITY

    # name = context.user_data['name']
    # TODO: enter class name
    name = "test"
    studio_id = context.user_data['studio_id']
    teacher = await get_user(update)
    teacher_id = teacher.telegram_id
    start_time = context.user_data['start_time']
    duration = context.user_data['duration']
    try:
        YogaClass.create(
            name=name,
            studio = studio_id,
            teacher = teacher_id,
            start_time = start_time,
            duration = duration,
            capacity = capacity
        )
        await update.message.reply_text("✅ Занятие успешно создано!")
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        errors_counter.inc()
        await update.message.reply_text("🚫 При создании урока что-то пошло не так, поробуйте снова")
        logger.error("Ошибка при создании урока %s", e)
        context.user_data.clear()
        return ConversationHandler.END


@track_command('cancel_creating_yoga_class_callback')
async def cancel_creating_yoga_class_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query._edit_message_text("❌ Создание занятия отменено")
    context.user.data_clear()
    return ConversationHandler.END
#endregion


def main():
    try:
        # metric andpoint start
        start_http_server(8000)
        logger.info("Prometheus metrics server started on port 8000")

        # scheduler init
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            func=update_database_metrics,
             trigger='interval',
             minutes=15,
             max_instances=1)
        scheduler.start()

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
            conversation_timeout=1200
        ))
        application.add_handler(ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex(r"^📅 Добавить занятие$"), start_creating_yoga_class)
            ],
            states={
                ENTER_CLASS_STUDIO: [
                    CallbackQueryHandler(select_studio, pattern=r"^select_studio_\d+$"),
                    CallbackQueryHandler(handle_pagination, pattern=r"^(studio_next_page|studio_prev_page)$"),
                    CallbackQueryHandler(cancel_creating_yoga_class_callback, pattern=r"^cancel_creation$")
                ],
                ENTER_CLASS_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_time)],
                ENTER_CLASS_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_duration)],
                ENTER_CLASS_CAPACITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class_capacity)]
            },
            fallbacks=[CommandHandler('cancel', cancel_creating_yoga_class_callback)],
            conversation_timeout=1200
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
        errors_counter.inc()
        logger.error('Fatal error: ', e)


if __name__ == "__main__":
    main()
