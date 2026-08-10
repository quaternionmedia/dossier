"""Centralized database configuration for Dossier.

Provides:
- DatabaseManager: Class for managing database connections
- get_session(): Convenience function for getting a session
- init_db(): Convenience function for initializing the database
- get_db_path(): Get the configured database path

Configuration priority:
1. DOSSIER_DB_PATH environment variable
2. database_path in ~/.dossier/config.json
3. Default: ~/.dossier/dossier.db
"""

import os
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine


class DatabaseManager:
    """Manages database connections and sessions.

    Usage:
        manager = DatabaseManager.get_instance()
        with manager.get_session() as session:
            # do stuff
    """

    _instance: Optional["DatabaseManager"] = None

    def __init__(self, path: Optional[Path] = None):
        """Initialize with optional explicit path (for testing)."""
        self._explicit_path = path
        self._engine: Optional[Engine] = None

    @classmethod
    def get_instance(cls) -> "DatabaseManager":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        if cls._instance is not None:
            if cls._instance._engine is not None:
                cls._instance._engine.dispose()
            cls._instance = None

    @property
    def path(self) -> Path:
        """Get the database path, resolving configuration."""
        if self._explicit_path:
            return self._explicit_path
        return get_db_path()

    @property
    def engine(self) -> Engine:
        """Get or create the database engine (lazy initialization)."""
        if self._engine is None:
            db_path = self.path
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._engine = create_engine(
                f"sqlite:///{db_path}",
                echo=False,
            )
        return self._engine

    def get_session(self) -> Session:
        """Get a new database session."""
        return Session(self.engine)

    def init_db(self) -> None:
        """Create all tables if they don't exist."""
        # Import all models to ensure they're registered
        from dossier.models import (  # noqa: F401
            DeltaLink,
            DeltaNote,
            DocumentSection,
            Project,
            ProjectBranch,
            ProjectComponent,
            ProjectContributor,
            ProjectDelta,
            ProjectDependency,
            ProjectIssue,
            ProjectLanguage,
            ProjectPullRequest,
            ProjectRelease,
            ProjectVersion,
        )

        SQLModel.metadata.create_all(self.engine)


def get_db_path() -> Path:
    """Get database path from config/environment.

    Priority:
    1. DOSSIER_DB_PATH environment variable
    2. database_path in DossierConfig
    3. Default: ~/.dossier/dossier.db
    """
    # Check environment variable first
    env_path = os.environ.get("DOSSIER_DB_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    # Check config file
    from dossier.config import DossierConfig

    config = DossierConfig.load()
    if config.database_path:
        return Path(config.database_path).expanduser().resolve()

    # Default path
    return Path.home() / ".dossier" / "dossier.db"


# Convenience functions for backward compatibility


def get_session() -> Session:
    """Get a database session (convenience function)."""
    return DatabaseManager.get_instance().get_session()


def init_db() -> None:
    """Initialize database tables (convenience function)."""
    DatabaseManager.get_instance().init_db()


def get_engine() -> Engine:
    """Get the database engine (convenience function)."""
    return DatabaseManager.get_instance().engine
