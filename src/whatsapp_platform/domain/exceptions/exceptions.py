"""Domain exceptions hierarchy."""


class WhatsAppPlatformException(Exception):
    """Base exception for all platform errors."""


class DomainException(WhatsAppPlatformException):
    """Base exception for domain layer errors."""


class InvalidJIDError(DomainException):
    """Raised when a WhatsApp JID string has an invalid format."""

    def __init__(self, jid_str: str, reason: str = "Invalid JID format"):
        super().__init__(f"Invalid JID '{jid_str}': {reason}")
        self.jid_str = jid_str
        self.reason = reason


class SessionStateException(DomainException):
    """Raised when an invalid session state transition is attempted."""

    def __init__(self, current_status: str, action: str):
        super().__init__(
            f"Cannot perform action '{action}' on session in status '{current_status}'"
        )
        self.current_status = current_status
        self.action = action


class CommandParseError(DomainException):
    """Raised when command parsing fails."""


class ApplicationException(WhatsAppPlatformException):
    """Base exception for application layer errors."""


class InfrastructureException(WhatsAppPlatformException):
    """Base exception for infrastructure layer errors."""


class GatewayException(InfrastructureException):
    """Raised when WhatsApp Gateway encounters an error."""


class FinanceBalanceConflictError(DomainException):
    """Perubahan saldo ditolak: rekening tidak ditemukan atau saldo akan menjadi minus."""

    def __init__(self, account_id: str):
        self.account_id = account_id
        super().__init__(f"Balance update rejected for account '{account_id}'")


class FinanceTransactionConflictError(DomainException):
    """Transaksi sudah berubah status (mis. sudah di-reverse) saat akan diproses."""

    def __init__(self, transaction_id: str):
        self.transaction_id = transaction_id
        super().__init__(f"Transaction '{transaction_id}' is no longer in the expected state")
