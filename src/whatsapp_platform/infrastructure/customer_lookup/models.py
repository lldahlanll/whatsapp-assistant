"""Customer lookup domain models / DTOs."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CustomerRecord:
    kode_kustomer: str
    no_hp: str
    add_user: str
    add_date: datetime
