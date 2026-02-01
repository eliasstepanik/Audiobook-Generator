"""Database connection and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from pathlib import Path
import logging

from .models import Base

logger = logging.getLogger(__name__)


class Database:
    """Database connection manager."""

    def __init__(self, database_url: str = "sqlite:///./audiobook_jobs.db"):
        """
        Initialize database.

        Args:
            database_url: SQLAlchemy database URL
        """
        self.database_url = database_url
        self.engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False}
            if "sqlite" in database_url
            else {},
        )
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

        # Create tables
        Base.metadata.create_all(bind=self.engine)

        # Migrate: add new columns if missing (for existing databases)
        self._migrate()

        logger.info(f"Database initialized: {database_url}")

    def _migrate(self):
        """Add new columns to existing tables if they don't exist."""
        from sqlalchemy import inspect, text

        inspector = inspect(self.engine)
        if "audiobook_jobs" in inspector.get_table_names():
            existing_columns = {
                col["name"] for col in inspector.get_columns("audiobook_jobs")
            }
            new_columns = {
                "parent_job_id": "VARCHAR(36)",
                "chapter_index": "INTEGER",
                "is_batch": "BOOLEAN DEFAULT 0",
            }
            with self.engine.begin() as conn:
                for col_name, col_type in new_columns.items():
                    if col_name not in existing_columns:
                        conn.execute(
                            text(
                                f"ALTER TABLE audiobook_jobs ADD COLUMN {col_name} {col_type}"
                            )
                        )
                        logger.info(f"Migration: added column {col_name}")

    @contextmanager
    def get_session(self) -> Session:
        """
        Get database session context manager.

        Yields:
            Database session
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def get_session_direct(self) -> Session:
        """
        Get database session directly.

        Returns:
            Database session
        """
        return self.SessionLocal()


# Global database instance
_db = None


def get_database(database_url: str = "sqlite:///./audiobook_jobs.db") -> Database:
    """
    Get or create database instance.

    Args:
        database_url: SQLAlchemy database URL

    Returns:
        Database instance
    """
    global _db
    if _db is None:
        _db = Database(database_url)
    return _db
