from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from pathlib import Path
import logging
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception for database-related errors"""


@dataclass
class BaseModel:
    """
    Base class for data models.
    Inherit from this class and add your fields.
    """

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaseModel:
        """Creates a model instance from a dictionary"""
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Converts the model to a dictionary"""
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}


class DatabaseManager:
    """Manager for SQLite database operations"""

    def __init__(self, db_path: str = "app_database.db"):
        """
        Initialize the database manager.
        
        :param db_path: Path to the database file
        """
        self.db_path = Path(db_path)
        self._connection: sqlite3.Connection | None = None
        self._ensure_db_exists()

    def _ensure_db_exists(self) -> None:
        """Ensures the database file exists, creates if needed"""
        if not self.db_path.exists():
            logger.info("Creating new database: %s", self.db_path)
            self.db_path.touch()

    def connect(self) -> sqlite3.Connection:
        """Establishes a database connection"""
        if self._connection is None:
            try:
                self._connection = sqlite3.connect(self.db_path)
                self._connection.row_factory = sqlite3.Row  # For field access by name
                logger.info("Database connection established successfully")
            except sqlite3.Error as e:
                logger.error("Database connection error: %s", e)
                raise DatabaseError(f"Failed to connect to database: {e}") from e
        return self._connection

    def disconnect(self) -> None:
        """Closes the database connection"""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    def execute_query(
        self,
        query: str,
        params: tuple[Any, ...] = (),
        commit: bool = False
    ) -> sqlite3.Cursor:
        """
        Executes an SQL query
        
        :param query: SQL query string
        :param params: Query parameters
        :param commit: Whether to commit after execution
        :return: Cursor with results
        """
        conn = self.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if commit:
                conn.commit()
            return cursor
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("Query execution error: {query}. Error: %s", e)
            raise DatabaseError(f"Query execution failed: {e}") from e

    def __enter__(self):
        """Context manager support"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support"""
        self.disconnect()


class BaseRepository:
    """Base repository for CRUD operations"""

    def __init__(self, db_manager: DatabaseManager, table_name: str):
        """
        Initialize the repository
        
        :param db_manager: DatabaseManager instance
        :param table_name: Name of the database table
        """
        self.db = db_manager
        self.table_name = table_name

    def create_table(self, schema: str) -> None:
        """
        Creates a table with the specified schema
        
        :param schema: SQL string defining the table structure
        """
        query = f"CREATE TABLE IF NOT EXISTS {self.table_name} ({schema})"
        self.db.execute_query(query, commit=True)
        logger.info("Table %s created or already exists", self.table_name)

    def insert(self, data: dict[str, Any]) -> int:
        """
        Inserts a new record into the table
        
        :param data: Dictionary with field-value pairs
        :return: ID of the inserted record
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?'] * len(data))
        query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        cursor = self.db.execute_query(query, tuple(data.values()), commit=True)
        return cursor.lastrowid

    def get_by_id(self, record_id: int) -> dict[str, Any] | None:
        """
        Retrieves a record by ID
        
        :param record_id: ID of the record to retrieve
        :return: Dictionary with record data or None if not found
        """
        query = f"SELECT * FROM {self.table_name} WHERE id = ?"
        cursor = self.db.execute_query(query, (record_id,))
        result = cursor.fetchone()
        return dict(result) if result else None

    def get_all(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Retrieves all records from the table (with limit)
        
        :param limit: Maximum number of records to retrieve
        :return: List of dictionaries with record data
        """
        query = f"SELECT * FROM {self.table_name} LIMIT ?"
        cursor = self.db.execute_query(query, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def update(self, record_id: int, data: dict[str, Any]) -> bool:
        """
        Updates a record in the table
        
        :param record_id: ID of the record to update
        :param data: Dictionary with field-value pairs to update
        :return: True if update was successful
        """
        set_clause = ', '.join([f"{key} = ?" for key in data.keys()])
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?"

        params = tuple(data.values()) + (record_id,)
        self.db.execute_query(query, params, commit=True)
        return True

    def delete(self, record_id: int) -> bool:
        """
        Deletes a record from the table
        
        :param record_id: ID of the record to delete
        :return: True if deletion was successful
        """
        query = f"DELETE FROM {self.table_name} WHERE id = ?"
        self.db.execute_query(query, (record_id,), commit=True)
        return True


# Usage Example:

# 1. Define your data model
@dataclass(kw_only=True)
class User(BaseModel):
    username: str
    email: str
    age: int | None = None
    id: int | None = None


# 2. Create a specialized repository
class UserRepository(BaseRepository):
    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, "users")
        self.create_table("""
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            age INTEGER
        """)

    def get_by_username(self, username: str) -> User | None:
        """Example of a specialized method - finds user by username"""
        query = f"SELECT * FROM {self.table_name} WHERE username = ?"
        cursor = self.db.execute_query(query, (username,))
        result = cursor.fetchone()
        return User.from_dict(dict(result)) if result else None

    def get_adults(self, min_age: int = 18) -> list[User]:
        """Another specialized method - finds adult users"""
        query = f"SELECT * FROM {self.table_name} WHERE age >= ?"
        cursor = self.db.execute_query(query, (min_age,))
        return [User.from_dict(dict(row)) for row in cursor.fetchall()]


# 3. Example of using the system
def example_usage():
    with DatabaseManager("example.db") as db_manager:
        user_repo = UserRepository(db_manager)

        # Create a user
        new_user = User(username="john_doe", email="john@example.com", age=30)
        user_id = user_repo.insert(new_user.to_dict())
        print(f"Created user with ID: {user_id}")

        # Retrieve user
        user = user_repo.get_by_id(user_id)
        print(f"Retrieved user: {user}")

        # Update user
        user_repo.update(user_id, {"age": 31})
        updated_user = user_repo.get_by_id(user_id)
        print(f"Updated age: {updated_user['age']}")

        # Find by username
        found_user = user_repo.get_by_username("john_doe")
        print(f"Found user: {found_user}")

        # Get all adult users
        adults = user_repo.get_adults()
        print(f"All adult users: {adults}")


if __name__ == "__main__":
    example_usage()
