from telegram import Update
from telegram.ext import ContextTypes

from config import logger
from core.models import Booking
from monitoring import track_command
from core.services import YogaClassService


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
                f"🔢 Мест: {
                    Booking.select().where(
                        Booking.yoga_class == class_,
                        Booking.status == 'confirmed').count()
                        } / {class_.capacity}\n\n"
            )

        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Error showing schedule: {e}")
        await update.message.reply_text("❌ Произошла ошибка при загрузке расписания.")

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
