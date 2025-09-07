from telegram import Update, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler
)
from config import logger
from core.services import *
from monitoring import *
from ..helpers import *

(
    ENTER_CLASS_STUDIO,
    ENTER_CLASS_TIME,
    ENTER_CLASS_DURATION,
    ENTER_CLASS_CAPACITY,
    ENTER_CLASS_NAME
) = range(4,9)


@track_command('start_creating_yoga_class')
async def start_creating_yoga_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start of creating studio."""
    user = await get_user(update)

    if not user.is_teacher:
        await update.message.reply_text("❌ Доступно только учителям")
        return ConversationHandler.END

    studios = StudioService.get_studios()
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

        if duration < 15 or duration > 720:
            await update.message.reply_text("❌ е смог распознять продолжительнотсь занятия, отправьте, пожалуйста только число цифрами (а ешё мой программист решил, что занятие короче 15 минут не имеет смысла, а длиннее 720 никто не выдержит).")
            return ENTER_CLASS_DURATION

        context.user_data['duration'] = duration

        studio = StudioService.get_studio_by_id(context.user_data['studio_id'])
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
        context.user_data['capacity'] = capacity
        await update.message.reply_text(
            "Отправьте мне название для занятия")
        return ENTER_CLASS_NAME
    except ValueError:
        await update.message.reply_text("❌ Количество участников должно быть положительным числом. Отправьте снова.")
        return ENTER_CLASS_CAPACITY
    except Exception as e:
        await update.message.reply_text("❌ {e}.")
        return ENTER_CLASS_CAPACITY


@track_command('get_class_name')
async def get_class_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    try:
        user = await get_user(update)
        yoga_class = YogaClassService.create_yoga_class(
            name=name,
            studio_id=context.user_data['studio_id'],
            teacher_id=user.id,
            start_time=context.user_data['start_time'],
            duration=context.user_data['duration'],
            capacity=context.user_data['capacity']
        )
        await update.message.reply_text(f"✅ Занятие \"{yoga_class.name}\" на {yoga_class.start_time} успешно создано!")
        return ConversationHandler.END
    except Exception as e:
        errors_counter.inc()
        logger.error(f"Error creating yoga class: %s", e)
        await update.message.reply_text("❌ Ошибка при создании занятия. Попробуйте снова.")
        return ConversationHandler.END



@track_command('cancel_creating_yoga_class')
async def cancel_creating_yoga_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена процесса создания занятия."""
    await update.message.reply_text("❌ Создание занятия отменено")
    context.user_data.clear()
    return ConversationHandler.END
