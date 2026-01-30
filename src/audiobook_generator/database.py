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
        logger.info(f"Database initialized: {database_url}")

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
