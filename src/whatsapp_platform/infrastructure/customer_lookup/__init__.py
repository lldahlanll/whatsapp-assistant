"""Infrastructure layer for Customer Lookup MySQL connectivity."""

from whatsapp_platform.infrastructure.customer_lookup.models import CustomerRecord
from whatsapp_platform.infrastructure.customer_lookup.mysql_pool import close_pool, get_pool
from whatsapp_platform.infrastructure.customer_lookup.repository import (
    CustomerLookupRepository,
    CustomerLookupUnavailableError,
)

__all__ = [
    "CustomerLookupRepository",
    "CustomerLookupUnavailableError",
    "CustomerRecord",
    "close_pool",
    "get_pool",
]
