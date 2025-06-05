from core.models import User, Studio, YogaClass, Booking

class UserService:
    @staticmethod
    def get_or_create(messenger_id: int, username: str = '', display_name: str = '') -> User:
        user, created = User.get_or_create(
            messenger_id=messenger_id,
            defaults={
                'display_name': display_name,
                'username': username
            }
        )
        return user, created

def main():
    pass

if __name__ == "__main__":
    main()
