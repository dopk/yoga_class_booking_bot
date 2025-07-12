from datetime import datetime

from prometheus_client import start_http_server
from telegram import Update
from telegram.ext import ContextTypes
from config import logger
from core.services import UserService, BookingService
from monitoring import *
from .helpers import (
    get_user,
    get_user_from_query,
    is_admin,
    send_notification,
    create_reply_keyboard
)
from .conversations import *

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
        booking = BookingService.get_booking_by_id(booking_id)
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
    target_user, is_maked_teacher = UserService.make_teacher(messenger_id=messenger_id)
    if target_user:
        if is_maked_teacher:
            await query.edit_message_text(
                text=f"✅ Пользователь @{target_user.username} успешно назначен учителем!"
            )
            await send_notification(
                context,
                messenger_id,
                "🎉 Вы были назначены учителем в системе!"
            )
        else:
            await query.answer("⚠️ Этот пользователь уже учитель")
    else:
        await query.edit_message_text(
                text="❌ Что-то пошло не так, попробуйте снова позднее."
            )

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Studio choise pagination."""
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

@track_command('show_schedule')
async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ расписания занятий."""
    # TODO: должен быть выбор показывать занятия по препроду или по студии.
    try:
        # Получаем будущие занятия
        classes = YogaClassService.show_future_class_by_teacher(1)

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
    non_teachers = UserService.get_no_teachers_w_pagination(page, page_size)

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
