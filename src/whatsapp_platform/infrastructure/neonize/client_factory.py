"""Neonize NewClient Factory for neonize==0.4.3.post0."""

import os

import structlog
from neonize.client import NewClient  # type: ignore[import-untyped]

logger = structlog.get_logger()

# Directory where Neonize session SQLite files are stored.
# Default to "./storage" so it works seamlessly both locally and inside Docker.
_SESSION_DIR = os.environ.get("NEONIZE_SESSION_DIR", "./storage")



class NeonizeClientFactory:
    @staticmethod
    def create_client(session_name: str = "default_session") -> NewClient:
        """Create and configure Neonize NewClient instance.

        The ``name`` argument passed to ``NewClient`` is used as the SQLite
        database file path.  We store it inside ``_SESSION_DIR`` so that the
        file sits alongside other app data rather than in the working directory,
        and to avoid conflicts with any Docker volume mount that creates a
        *directory* at the same path as the session name.
        """
        os.makedirs(_SESSION_DIR, exist_ok=True)
        db_path = os.path.join(_SESSION_DIR, f"{session_name}.db")
        logger.info(
            "Initializing Neonize NewClient (v0.4.3.post0)",
            session_name=session_name,
            db_path=db_path,
        )
        client = NewClient(name=db_path)
        return client
