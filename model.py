from dataclasses import dataclass
from datetime import date, timedelta
import logging
from typing import Any, Self

from storage import BaseModel, BaseRepository, DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ... (keep all the previous imports and base classes from our original code) ...

@dataclass
class Teacher(BaseModel):
    """Teacher data model"""
    username: str
    display_name: str
    registration_date: date
    payment_end_date: date
    notes: str = ""
    id: int | None = None


@dataclass
class Studio(BaseModel):
    """Yoga halls data model"""
    name: str
    address: str
    has_shower: bool
    added_date: date
    capacity: int
    notes: str = ""
    id: int | None = None

@dataclass
class YogaClass(BaseModel):
    """Yoga class data model"""
    name: str
    studio_id: int
    teacher_id: int
    start_time: date
    duration: int
    capacity: int # in minutes
    notes: str = ""
    id: int | None = None


@dataclass
class Student(BaseModel):
    """Student data model"""
    display_name: str
    username: str
    registration_date: date
    notes: str = ""
    id: int | None = None


@dataclass
class YogaClassBooking(BaseModel):
    """Yoga class booking data model"""
    class_id: int
    student_id: int
    approved: bool = False
    notes: str = ''
    id: int | None = None


class TeacherRepository(BaseRepository):
    """Repository for teacher operations"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "teachers")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            registration_date DATE NOT NULL,
            payment_end_date DATE NOT NULL,
            notes TEXT DEFAULT ''
        """)

    def add_teacher(self, teacher: Teacher) -> int:
        """Insert a new teacher with validation
        returns teacher.id"""
        searched_teacher = self.get_teachers_by_username(teacher.username)
        if searched_teacher:
            logger.info("teacher with username %s already exist",teacher.username)
            return searched_teacher.id
        return self.insert(teacher.to_dict())

    def get_teachers_by_username(self, username: str) -> Teacher | None:
        """Get teacher by username"""
        query = """
            SELECT id, username, display_name, registration_date, payment_end_date, notes FROM %s
            WHERE username = "%s"
        """ %(self.table_name, username)
        teacher = self.db.execute_query(query).fetchone()
        if teacher:
            return Teacher.from_dict(dict(teacher))
        return None

    def get_teachers_by_payment_status(self, active: bool = True) -> list[Teacher]:
        """Get teachers with active/expired payments"""
        comparison = ">=" if active else "<"
        query = f"""
            SELECT * FROM {self.table_name}
            WHERE payment_end_date {comparison} CURRENT_DATE
            ORDER BY payment_end_date DESC
        """
        cursor = self.db.execute_query(query)
        return [Teacher.from_dict(dict(row)) for row in cursor.fetchall()]


class StudioRepository(BaseRepository):
    """Repository for studio operations"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "studios")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            address TEXT NOT NULL,
            has_shower BOOLEAN NOT NULL DEFAULT 0,
            added_date DATE NOT NULL,
            notes TEXT DEFAULT ''
        """)

    def get_studio_by_name(self, name: str) -> Studio | None:
        """Get studio by name"""
        query = f"""
            SELECT id, name, address, has_shower, added_date, notes FROM {self.table_name}
            WHERE name = "{name}"
        """
        studio = self.db.execute_query(query).fetchone()
        if studio:
            return Studio.from_dict(dict(studio))
        return None

    def add_studio(self, studio: Studio) -> int:
        """Insert a new studio with validation
        returns studio.id"""
        searched_studio = self.get_studio_by_name(studio.name)
        if searched_studio:
            logger.info("Studio with name %s already exist", studio.name)
            return searched_studio.id
        return self.insert(studio.to_dict())

    def get_studios_with_showers(self) -> list[Studio]:
        """Get studios that have showers"""
        query = f"SELECT * FROM {self.table_name} WHERE has_shower = 1"
        cursor = self.db.execute_query(query)
        return [Studio.from_dict(dict(row)) for row in cursor.fetchall()]


class YogaClassRepository(BaseRepository):
    """Repository for yoga-classes operations"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "classes")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            studio_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            start_time DATE NOT NULL,
            duration INTEGER NOT NULL,
            capacity INTEGER NOT NULL,
            notes TEXT DEFAULT ''
        """)

    def get_class_by_teacher_id(self, teacher_id: int) -> list[YogaClass]:
        query = """
            SELECT id, name, studio_id, teacher_id, start_time, duration, capacity, notes FROM %s
            WHERE teacher_id = "%s"
            AND start_time >= CURRENT_DATE
            ORDER BY start_time
        """ %(self.table_name, teacher_id)
        cursor = self.db.execute_query(query)
        return [YogaClass.from_dict(dict(row)) for row in cursor.fetchall()]

    def get_class_by_studio_id(self, studio_id: int) -> list[YogaClass]:
        query = """
            SELECT id, name, studio_id, teacher_id, start_time, duration, capacity, notes FROM %s
            WHERE studio_id = "%s"
            AND start_time >= CURRENT_DATE
            ORDER BY start_time
        """ %(self.table_name, studio_id)
        cursor = self.db.execute_query(query)
        return [YogaClass.from_dict(dict(row)) for row in cursor.fetchall()]


class StudentRepository(BaseRepository):
    """Repository for student operations"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "students")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            registration_date DATE NOT NULL,
            notes TEXT DEFAULT ''
        """)

    def get_student_by_username(self, username: str) -> Student | None:
        """Get student by username"""
        query = """
            SELECT id, username, display_name, registration_date, notes FROM %s
            WHERE username = "%s"
        """ %(self.table_name, username)
        student = self.db.execute_query(query).fetchone()
        if student:
            return Student.from_dict(dict(student))
        return None

    def add_student(self, student: Student) -> int:
        """Insert a new student with validation
        returns student.id"""
        searched_student = self.get_student_by_username(student.username)
        if searched_student:
            logger.info("student with username %s already exist",student.username)
            return searched_student.id
        return self.insert(student.to_dict())

    def get_recent_students(self, days: int = 30) -> list[Student]:
        """Get students registered in last N days"""
        query = f"""
            SELECT * FROM {self.table_name}
            WHERE registration_date >= date('now', '-{days} days')
        """
        cursor = self.db.execute_query(query)
        return [Student.from_dict(dict(row)) for row in cursor.fetchall()]


class YogaClassBookingRepository(BaseRepository):
    """Repository for Book place on class for student"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "class_booking")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            approved: BOOLEAN NOT NULL DEFAULT 0,
            notes TEXT DEFAULT ''
        """)


def example_usage():
    """Demonstration of how to use these classes"""
    with DatabaseManager("yoga_booking.db") as db:
        # Initialize repositories
        teacher_repo = TeacherRepository(db)
        studio_repo = StudioRepository(db)
        student_repo = StudentRepository(db)

        # Add sample data
        teacher_id = teacher_repo.add_teacher(Teacher(
            username="anna_ballerina911",
            display_name="Anna Petrova",
            registration_date=date(2023, 1, 15),
            payment_end_date=date(2024, 1, 15),
            notes="Ballet specialist"
        ))

        # teacher2_id = teacher_repo.add_teacher(Teacher(
        #     username="kate_ballerina",
        #     display_name="Kate Petrova",
        #     registration_date=date(2023, 1, 15),
        #     payment_end_date=date(2030, 1, 15),
        #     notes="Ballet specialist"
        # ))

        # studio_id = studio_repo.add_studio(Studio(
        #     name="Grand Ballet Hall 5",
        #     address="123 Dance Street",
        #     has_shower=True,
        #     added_date=date.today(),
        #     notes="Main studio with mirrors"dict(row)) for row in cursor.fetchall(
        # ))

        # student_id = student_repo.add_student(Student(
        #     username="little_dancer 5",
        #     display_name="Maria Ivanova",
        #     registration_date=date.today()
        # ))

        # Retrieve data
        active_teachers = teacher_repo.get_teachers_by_payment_status()
        anna_petrova = teacher_repo.get_teachers_by_username("anna_ballerina")
        studios_with_showers = studio_repo.get_studios_with_showers()
        new_students = student_repo.get_recent_students(7)

        print(f"Active teachers: {active_teachers}")
        print(f"Studios with showers: {studios_with_showers}")
        print(f"New students: {new_students}")
        print(f"Teacher by username:", anna_petrova.username)
        if anna_petrova:
            print("ticher suschestvuet")


if __name__ == "__main__":
    example_usage()
