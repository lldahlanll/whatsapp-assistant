# app/auth/__init__.py
from app.auth.admin_handler import AdminHandler, admin_handler
from app.auth.credential_store import (
    CredentialStore,
    UserCredential,
    credential_store,
)
from app.auth.login_handler import LoginHandler, login_handler
from app.auth.middleware import (
    AuthResult,
    AuthState,
    check_admin,
    check_auth,
    cleanup_user,
)
from app.auth.session_manager import Session, SessionManager, session_manager
from app.auth.whitelist import Whitelist, WhitelistedUser, whitelist

__all__ = [
    # Singletons — storage
    "credential_store",
    "session_manager",
    "whitelist",
    # Singletons — command handlers
    "login_handler",
    "admin_handler",
    # Storage classes
    "CredentialStore",
    "SessionManager",
    "Whitelist",
    # Handler classes
    "LoginHandler",
    "AdminHandler",
    # Data models
    "UserCredential",
    "Session",
    "WhitelistedUser",
    # Middleware
    "AuthResult",
    "AuthState",
    "check_auth",
    "check_admin",
    "cleanup_user",
]