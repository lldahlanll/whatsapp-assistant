"""SessionManager orchestrates session feature behavior."""

import structlog

from whatsapp_platform.application.use_cases.manage_session import ManageSessionUseCase
from whatsapp_platform.infrastructure.config.settings import Settings

logger = structlog.get_logger()


class SessionManager:
    def __init__(self, use_case: ManageSessionUseCase, settings: Settings) -> None:
        self.use_case = use_case
        self.settings = settings

    async def start(self) -> None:
        session_id = self.settings.session_name
        method = self.settings.pairing_method
        phone = self.settings.pairing_phone_number

        logger.info("Starting SessionManager", session_id=session_id, method=method)

        if method == "code" and phone:
            logger.info("Requesting pairing code for number", phone=phone)
            code = await self.use_case.pair_by_code(session_id, phone)
            print("\n" + "=" * 50)
            print(f" WHATSAPP PAIRING CODE: {code} ")
            print(" Enter this code in WhatsApp on your phone ")
            print("=" * 50 + "\n")
        else:
            await self.use_case.connect_session(session_id)
