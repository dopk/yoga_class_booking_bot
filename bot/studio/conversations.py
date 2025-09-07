from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from core.services import UserService, StudioService
from bot.helpers import get_user, check_yes, check_no
from monitoring import track_command, errors_counter

(
    ENTER_STUDIO_NAME,
    ENTER_STUDIO_ADDRESS,
    ENTER_STUDIO_CAPACITY,
    ENTER_STUDIO_HAS_SHOWER
) = range(4)

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
    await update.message.reply_text(
        "Отправьте мне вместимость студии (максимальное количество человек):"
        )
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
    created_by = UserService.get_user_by_messenger_id(user.messenger_id).id

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

    studio = StudioService.create_studio(
        name=name,
        address=address,
        capacity=capacity,
        has_shower=has_shower,
        created_by=created_by)
    if studio:
        await update.message.reply_text(f"✅ Студия '{name}' успешно добавлена")
    else:
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
