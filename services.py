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
    def create_studio(name: srt, address: str, capacity: int, has_shower: bool, created_by: int):
        try:
            Studio.create(
                name=name,
                address=address,
                capacity=capacity,
                has_shower=has_shower,
                created_by=created_by
            )
        except IntegrityError:
            return None


def main():
    pass

if __name__ == "__main__":
    main()
