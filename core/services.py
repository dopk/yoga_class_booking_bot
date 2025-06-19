from datetime import datetime
import logging
from core.models import User, Studio, YogaClass, Booking
from peewee import DoesNotExist



# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class UserService:
    @staticmethod
    def get_or_create(messenger_id: int, username: str = 'unknown', display_name: str = 'unknown'):
        user, created = User.get_or_create(
            messenger_id=messenger_id,
            defaults={
                'display_name': display_name,
                'username': username
            }
        )
        return user, created
    
    @staticmethod
    def get_no_teachers_w_pagination(page: int, page_size: int) -> list:
        return list(User.select().where(User.is_teacher == False)
                        .order_by(User.username)
                        .paginate(page, page_size))
    
    @staticmethod
    def get_user_by_messenger_id(messenger_id: int):
        return User.get(User.messenger_id == messenger_id)

    @staticmethod
    def make_teacher(messenger_id: int):
        target_user, _ = UserService.get_or_create(messenger_id=messenger_id)
        try:
            if target_user.is_teacher:
                return target_user, False
            target_user.is_teacher = True
            target_user.save()
            return target_user, True
        except Exception as e:
            logger.warning("Error while making teacher: %s", e)
            return None, False


class StudioService:
    @staticmethod
    def create_studio(name: str, address: str, capacity: int, has_shower: bool, created_by: int):
        try:
            return Studio.create(
                name=name,
                address=address,
                capacity=capacity,
                has_shower=has_shower,
                created_by=created_by)
        except IntegrityError:
            return None
    @staticmethod
    def get_studios():
        return list(Studio.select().order_by(Studio.created_at))
    @staticmethod
    def get_studio_by_id(id:int):
        return Studio.get_by_id(id)


class YogaClassService:
    @staticmethod
    def create_yoga_class(name: str,
                          studio_id: int,
                          teacher_id: int,
                          start_time: datetime,
                          duration: int,
                          capacity: int):
        return YogaClass.create(
            name=name,
            studio=studio_id,
            teacher=teacher_id,
            start_time=start_time,
            duration=duration,
            capacity=capacity)

    @staticmethod
    def show_future_class_by_teacher(teacher_id: int):
        return YogaClass.select().where(
            YogaClass.start_time > datetime.now().where(teacher=teacher_id)
        ).order_by(YogaClass.start_time)

    @staticmethod
    def show_future_class_by_studio(studio_id: int):
        return YogaClass.select().where(
            YogaClass.start_time > datetime.now().where(studio=studio_id)
        ).order_by(YogaClass.start_time)


class BookingService:
    @staticmethod
    def get_booking_by_id(booking_id: int):
        return Booking.get_by_id(booking_id)
