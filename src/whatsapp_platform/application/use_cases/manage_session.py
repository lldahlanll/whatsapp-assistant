"""ManageSessionUseCase."""

import structlog

from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.domain.entities.session import WhatsAppSession
from whatsapp_platform.domain.repositories.session_repository import ISessionRepository

logger = structlog.get_logger()


class ManageSessionUseCase:
    def __init__(
        self,
        gateway: IMessagingGateway,
        session_repo: ISessionRepository,
    ) -> None:
        self.gateway = gateway
        self.session_repo = session_repo

    async def connect_session(self, session_id: str) -> WhatsAppSession:
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            session = WhatsAppSession(id=session_id)
            await self.session_repo.save(session)

        logger.info("Connecting session via Gateway", session_id=session_id)
        await self.gateway.connect()
        return session

    async def pair_by_code(self, session_id: str, phone_number: str) -> str:
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            session = WhatsAppSession(id=session_id)
            await self.session_repo.save(session)

        session.set_awaiting_pairing_code()
        session.phone_number = phone_number
        await self.session_repo.save(session)

        code = await self.gateway.pair_phone(phone_number)
        logger.info(
            "Pairing code requested",
            session_id=session_id,
            phone_number=phone_number,
            code=code,
        )
        return code

    async def disconnect_session(self, session_id: str) -> None:
        logger.info("Disconnecting session", session_id=session_id)
        await self.gateway.disconnect()
        session = await self.session_repo.get_by_id(session_id)
        if session:
            session.disconnect()
            await self.session_repo.save(session)
