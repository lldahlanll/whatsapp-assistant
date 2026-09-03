"""MessageSender wrapper for sending messages."""

from whatsapp_platform.application.use_cases.send_media import SendMediaUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.domain.entities.message import Message
from whatsapp_platform.domain.value_objects.message_content import MediaContent


class MessageSender:
    def __init__(
        self, send_msg_uc: SendMessageUseCase, send_media_uc: SendMediaUseCase
    ) -> None:
        self.send_msg_uc = send_msg_uc
        self.send_media_uc = send_media_uc

    async def send_text(self, to_jid_str: str, text: str) -> Message:
        return await self.send_msg_uc.execute(to_jid_str, text)

    async def send_media(
        self, to_jid_str: str, media: MediaContent, caption: str | None = None
    ) -> Message:
        return await self.send_media_uc.execute(to_jid_str, media, caption=caption)
