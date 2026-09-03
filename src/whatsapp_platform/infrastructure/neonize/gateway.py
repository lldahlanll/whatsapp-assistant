"""NeonizeGateway implementation of IMessagingGateway using neonize==0.4.3.post0."""

import asyncio
import inspect
import threading
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import structlog
from neonize.client import ChatPresence, ChatPresenceMedia, NewClient  # type: ignore[import-untyped]
from neonize.events import (  # type: ignore[import-untyped]
    ConnectedEv,
    DisconnectedEv,
    LoggedOutEv,
    MessageEv,
    PairStatusEv,
    QREv,
)
from neonize.utils import (  # type: ignore[import-untyped]
    Jid2String,
    ParticipantChange,
    build_jid,
)

from whatsapp_platform.application.interfaces.event_bus import IEventBus
from whatsapp_platform.application.interfaces.messaging_gateway import (
    EventHandler,
    IMessagingGateway,
)
from whatsapp_platform.domain.events.base import DomainEvent
from whatsapp_platform.domain.exceptions.exceptions import GatewayException
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import (
    MediaContent,
    MediaType,
    TextContent,
)
from whatsapp_platform.infrastructure.neonize.client_factory import NeonizeClientFactory
from whatsapp_platform.infrastructure.neonize.event_mapper import NeonizeEventMapper

logger = structlog.get_logger()


class NeonizeGateway(IMessagingGateway):
    """Adapter wrapping the Neonize (Whatsmeow Go) client as an IMessagingGateway.

    Architecture note
    -----------------
    Neonize runs its own internal event loop in a background thread.
    All ``@client.event`` callbacks execute on that thread, NOT on the
    Python asyncio event loop.

    ``_dispatch_domain_event`` bridges the gap:
      1. Notifies local synchronous ``_listeners`` (registered via ``subscribe_event``).
      2. Forwards the event to the application-level ``IEventBus`` so that
         use cases and feature modules can react through the domain event system.
    """

    def __init__(
        self,
        session_name: str = "default_session",
        client: NewClient | None = None,
    ) -> None:
        self.session_name = session_name
        self.client = client or NeonizeClientFactory.create_client(session_name)
        self._listeners: dict[type[DomainEvent], list[EventHandler]] = defaultdict(list)
        self._connected = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event_bus: IEventBus | None = None
        # Waktu saat bot mulai terhubung; pesan sebelum waktu ini adalah pesan
        # offline yang di-replay oleh WhatsApp dan harus diabaikan.
        self._startup_time: datetime | None = None

        self._register_neonize_event_handlers()

    # ------------------------------------------------------------------
    # EventBus bridge (injected after construction)
    # ------------------------------------------------------------------

    def set_event_bus(self, event_bus: IEventBus) -> None:
        """Inject the application EventBus so gateway events are forwarded.

        Called by SessionFeature.initialize() after the container is ready.
        Using setter injection avoids a circular dependency between
        NeonizeGateway and IEventBus at construction time.
        """
        self._event_bus = event_bus
        logger.debug(
            "IEventBus injected into NeonizeGateway", session=self.session_name
        )

    # ------------------------------------------------------------------
    # Neonize internal event handlers
    # ------------------------------------------------------------------

    def _register_neonize_event_handlers(self) -> None:
        """Register all Neonize event callbacks and map them to domain events."""

        @self.client.event(ConnectedEv)
        def on_connected(client: NewClient, ev: ConnectedEv) -> None:
            logger.info("Neonize connected to WhatsApp", session=self.session_name)
            self._connected = True
            event = NeonizeEventMapper.map_connected_ev(self.session_name)
            self._dispatch_domain_event(event)

        @self.client.event(DisconnectedEv)
        def on_disconnected(client: NewClient, ev: DisconnectedEv) -> None:
            logger.warning(
                "Neonize disconnected from WhatsApp", session=self.session_name
            )
            self._connected = False
            event = NeonizeEventMapper.map_disconnected_ev(self.session_name)
            self._dispatch_domain_event(event)

        @self.client.event(LoggedOutEv)
        def on_logged_out(client: NewClient, ev: LoggedOutEv) -> None:
            reason = str(getattr(ev, "Reason", "loggedout") or "loggedout")
            logger.warning(
                "WhatsApp session logged out remotely",
                session=self.session_name,
                reason=reason,
                on_connect=getattr(ev, "OnConnect", False),
            )
            self._connected = False
            event = NeonizeEventMapper.map_disconnected_ev(
                self.session_name, reason="loggedout"
            )
            self._dispatch_domain_event(event)

        @self.client.event(QREv)
        def on_qr(client: NewClient, ev: QREv) -> None:
            qr_code_str = ev.code if hasattr(ev, "code") else str(ev)
            logger.info("QR Code received from WhatsApp", session=self.session_name)
            event = NeonizeEventMapper.map_qr_ev(self.session_name, qr_code_str)
            self._dispatch_domain_event(event)

        @self.client.event(PairStatusEv)
        def on_pair_status(client: NewClient, ev: PairStatusEv) -> None:
            """Handle pairing success/failure event from WhatsApp."""
            # Extract phone number from PairStatusEv
            phone_number: str | None = None
            jid_obj = getattr(ev, "ID", None)
            if jid_obj and getattr(jid_obj, "User", None):
                phone_number = str(jid_obj.User)

            error_obj = getattr(ev, "Error", None)
            if error_obj:
                error_msg = str(error_obj)
                logger.error(
                    "WhatsApp pairing failed",
                    session=self.session_name,
                    error=error_msg,
                )
                return

            logger.info(
                "WhatsApp pairing succeeded",
                session=self.session_name,
                phone_number=phone_number,
            )
            # Emit SessionConnected with the paired phone number
            event = NeonizeEventMapper.map_connected_ev(
                self.session_name, phone_number=phone_number
            )
            self._dispatch_domain_event(event)

        @self.client.event(MessageEv)
        def on_message(client: NewClient, ev: MessageEv) -> None:
            domain_event = NeonizeEventMapper.map_message_ev(ev)
            msg = domain_event.message
            if not msg:
                return

            # ── Startup guard ──────────────────────────────────────────────────
            # Neonize (whatsmeow) mereplay semua pesan yang masuk saat bot
            # offline ketika reconnect. Pesan dengan timestamp sebelum
            # _startup_time adalah pesan lama dan harus di-skip agar LLM
            # tidak membalas chat yang sudah lama.
            if self._startup_time and msg.timestamp < self._startup_time:
                logger.debug(
                    "⏭️  Skipping offline replay message",
                    message_id=msg.id,
                    msg_time=msg.timestamp.isoformat(),
                    startup_time=self._startup_time.isoformat(),
                )
                return

            text_preview = (
                msg.content.text
                if isinstance(msg.content, TextContent)
                else f"[{msg.content.media_type.value}] {msg.content.caption or ''}"
            )
            sender_display = (
                f"{msg.push_name} ({msg.sender_jid.user})"
                if msg.push_name
                else str(msg.sender_jid.user)
            )
            chat_type = "Group" if msg.chat_jid.is_group else "Private"

            logger.info(
                "📩 Incoming Message",
                sender=sender_display,
                chat_type=chat_type,
                chat=str(msg.chat_jid),
                is_from_me=msg.is_from_me,
                text=text_preview.strip() if text_preview else "<media/empty>",
            )
            self._dispatch_domain_event(domain_event)

    # ------------------------------------------------------------------
    # Event dispatch bridge (Neonize thread → asyncio event loop)
    # ------------------------------------------------------------------

    def _dispatch_domain_event(self, event: DomainEvent) -> None:
        """Dispatch a domain event to local listeners AND the application EventBus.

        This method runs in the Neonize background thread. All asyncio calls
        must use ``run_coroutine_threadsafe`` to cross thread boundaries safely.
        """
        if not self._loop:
            return

        event_class = type(event)

        # 1. Dispatch to local listeners (registered via subscribe_event)
        handlers = self._listeners.get(event_class, [])
        for handler in handlers:
            if inspect.iscoroutinefunction(handler):
                asyncio.run_coroutine_threadsafe(handler(event), self._loop)
            else:
                self._loop.call_soon_threadsafe(handler, event)

        # 2. Forward to application-level IEventBus
        if self._event_bus is not None:
            asyncio.run_coroutine_threadsafe(self._event_bus.publish(event), self._loop)

    # ------------------------------------------------------------------
    # IMessagingGateway interface
    # ------------------------------------------------------------------

    def subscribe_event(
        self, event_type: type[DomainEvent], handler: EventHandler
    ) -> None:
        """Register a local handler for a specific domain event type."""
        self._listeners[event_type].append(handler)

    async def connect(self) -> None:
        """Start the Neonize client in a daemon thread, capturing the event loop."""
        self._loop = asyncio.get_running_loop()
        # Catat waktu startup sebelum connect agar pesan offline yang di-replay
        # oleh WhatsApp (whatsmeow) tidak diproses oleh AI/feature handlers.
        self._startup_time = datetime.now(UTC)
        logger.info(
            "Starting Neonize Client connection...",
            session=self.session_name,
            startup_time=self._startup_time.isoformat(),
        )

        def run_client() -> None:
            try:
                self.client.connect()
            except Exception as exc:
                logger.error("Error in Neonize client thread", error=str(exc), exc_info=True)

        client_thread = threading.Thread(
            target=run_client,
            daemon=True,
            name=f"Neonize-{self.session_name}",
        )
        client_thread.start()

    async def disconnect(self) -> None:
        """Gracefully disconnect from WhatsApp."""
        logger.info("Disconnecting Neonize Gateway...", session=self.session_name)
        try:
            self.client.disconnect()
            self._connected = False
        except Exception as exc:
            logger.error("Failed to disconnect Neonize Client", error=str(exc), exc_info=True)

    async def is_connected(self) -> bool:
        return self._connected

    async def send_text(self, to: JID, text: str, quoted: Any | None = None) -> str:
        target_jid = build_jid(to.user, to.server)
        try:
            if quoted is not None and hasattr(quoted, "Info") and hasattr(quoted, "Message"):
                resp = await asyncio.to_thread(
                    self.client.reply_message, text, quoted=quoted, to=target_jid
                )
            else:
                resp = await asyncio.to_thread(self.client.send_message, target_jid, text)
            msg_id = getattr(resp, "ID", "") if resp else ""
            return str(msg_id)
        except Exception as exc:
            logger.error("Failed to send text via Neonize", to=str(to), error=str(exc), exc_info=True)
            raise GatewayException(f"Failed to send message: {exc}") from exc

    async def send_chat_presence(self, to: JID, composing: bool) -> None:
        target_jid = build_jid(to.user, to.server)
        state = (
            ChatPresence.CHAT_PRESENCE_COMPOSING
            if composing
            else ChatPresence.CHAT_PRESENCE_PAUSED
        )
        try:
            await asyncio.to_thread(
                self.client.send_chat_presence,
                target_jid,
                state,
                ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT,
            )
        except Exception as exc:
            logger.warning("Failed to send chat presence", to=str(to), error=str(exc))

    async def send_media(
        self, to: JID, media: MediaContent, caption: str | None = None
    ) -> str:
        target_jid = build_jid(to.user, to.server)
        file_input = media.file_path or media.file_bytes
        if not file_input:
            raise GatewayException("MediaContent must provide file_path or file_bytes")

        caption_text = caption or media.caption or ""

        try:
            if media.media_type == MediaType.IMAGE:
                resp = await asyncio.to_thread(
                    self.client.send_image, target_jid, file_input, caption=caption_text
                )
            elif media.media_type == MediaType.AUDIO:
                resp = await asyncio.to_thread(
                    self.client.send_audio, target_jid, file_input, ptt=media.is_ptt
                )
            elif media.media_type == MediaType.DOCUMENT:
                resp = await asyncio.to_thread(
                    self.client.send_document,
                    target_jid,
                    file_input,
                    caption=caption_text,
                    title=media.file_name or "document",
                )
            elif media.media_type == MediaType.VIDEO:
                resp = await asyncio.to_thread(
                    self.client.send_video, target_jid, file_input, caption=caption_text
                )
            else:
                resp = await asyncio.to_thread(
                    self.client.send_message, target_jid, caption_text
                )

            msg_id = getattr(resp, "ID", "") if resp else ""
            return str(msg_id)
        except Exception as exc:
            logger.error("Failed to send media via Neonize", to=str(to), error=str(exc), exc_info=True)
            raise GatewayException(f"Failed to send media: {exc}") from exc

    async def download_media(self, raw_message: Any) -> bytes:
        """Download media attachment from a MessageEv or Protobuf message object."""
        try:
            data = await asyncio.to_thread(self.client.download_any, raw_message)
            if isinstance(data, bytes):
                return data
            elif isinstance(data, bytearray):
                return bytes(data)
            else:
                return str(data).encode("utf-8")
        except Exception as exc:
            logger.error("Failed to download media via Neonize", error=str(exc), exc_info=True)
            raise GatewayException(f"Failed to download media: {exc}") from exc

    async def pair_phone(self, phone_number: str) -> str:
        logger.info("Requesting PairPhone code from Neonize", phone_number=phone_number)
        try:
            code = await asyncio.to_thread(self.client.PairPhone, phone_number)
            return str(code)
        except Exception as exc:
            logger.error("PairPhone failed", phone_number=phone_number, error=str(exc))
            raise GatewayException(f"PairPhone failed: {exc}") from exc

    async def get_group_info(self, group_jid: JID) -> dict:
        target_jid = build_jid(group_jid.user, group_jid.server)
        try:
            info = await asyncio.to_thread(self.client.get_group_info, target_jid)

            # 1. Group Name
            group_name = ""
            if hasattr(info, "GroupName") and getattr(info.GroupName, "Name", None):
                group_name = info.GroupName.Name
            elif hasattr(info, "Name"):
                group_name = str(info.Name)

            # 2. Group Topic / Description
            topic = ""
            if hasattr(info, "GroupTopic") and getattr(info.GroupTopic, "Topic", None):
                topic = info.GroupTopic.Topic

            # 3. Owner JID (Resolve LID to Phone Number if LID)
            owner_jid_str = ""
            owner_obj = getattr(info, "OwnerJID", None)
            if owner_obj and getattr(owner_obj, "User", None):
                if getattr(owner_obj, "Server", "") == "lid":
                    try:
                        resolved_owner = self.client.get_pn_from_lid(owner_obj)
                        if resolved_owner and getattr(resolved_owner, "User", None):
                            owner_obj = resolved_owner
                    except Exception as exc:
                        logger.warning("Could not resolve LID for owner", error=str(exc))
                owner_jid_str = Jid2String(owner_obj)

            # 4. Participants (Resolve LID to Phone Number for each member)
            participant_list = []
            for p in getattr(info, "Participants", []):
                p_jid_obj = getattr(p, "JID", None)
                pn_obj = getattr(p, "PhoneNumber", None)

                phone = ""
                if pn_obj and getattr(pn_obj, "User", None):
                    phone = pn_obj.User
                elif p_jid_obj and getattr(p_jid_obj, "User", None):
                    if getattr(p_jid_obj, "Server", "") == "lid":
                        try:
                            resolved_pn = self.client.get_pn_from_lid(p_jid_obj)
                            if resolved_pn and getattr(resolved_pn, "User", None):
                                phone = resolved_pn.User
                            else:
                                phone = p_jid_obj.User
                        except Exception as exc:
                            logger.warning("Could not resolve LID for participant", error=str(exc))
                            phone = p_jid_obj.User
                    else:
                        phone = p_jid_obj.User

                p_jid_str = (
                    Jid2String(p_jid_obj)
                    if p_jid_obj and getattr(p_jid_obj, "User", None)
                    else ""
                )
                display_name = getattr(p, "DisplayName", "") or ""
                is_admin = getattr(p, "IsAdmin", False) or getattr(
                    p, "IsSuperAdmin", False
                )
                is_super_admin = getattr(p, "IsSuperAdmin", False)

                participant_list.append(
                    {
                        "jid": p_jid_str,
                        "phone": phone,
                        "display_name": display_name,
                        "is_admin": is_admin,
                        "is_super_admin": is_super_admin,
                    }
                )

            return {
                "jid": str(group_jid),
                "name": group_name,
                "owner": owner_jid_str,
                "topic": topic,
                "participants": participant_list,
            }
        except Exception as exc:
            logger.error(
                "Failed to get group info", group=str(group_jid), error=str(exc), exc_info=True
            )
            raise GatewayException(f"Failed to get group info: {exc}") from exc

    async def get_group_invite_link(self, group_jid: JID, revoke: bool = False) -> str:
        target_jid = build_jid(group_jid.user, group_jid.server)
        try:
            code = await asyncio.to_thread(
                self.client.get_group_invite_link, target_jid, revoke
            )
            if not code:
                return ""
            if code.startswith(("http://", "https://")):
                return code
            return f"https://chat.whatsapp.com/{code}"
        except Exception as exc:
            logger.error(
                "Failed to get group invite link", group=str(group_jid), error=str(exc), exc_info=True
            )
            raise GatewayException(f"Failed to get group invite link: {exc}") from exc

    async def update_group_participants(
        self, group_jid: JID, participants: list[JID], action: str
    ) -> None:
        target_group = build_jid(group_jid.user, group_jid.server)
        target_participants = [build_jid(p.user, p.server) for p in participants]
        action_map = {
            "add": ParticipantChange.ADD,
            "remove": ParticipantChange.REMOVE,
            "promote": ParticipantChange.PROMOTE,
            "demote": ParticipantChange.DEMOTE,
        }
        change_action = action_map.get(action.lower())
        if not change_action:
            raise GatewayException(f"Invalid participant action '{action}'")

        try:
            await asyncio.to_thread(
                self.client.update_group_participants,
                target_group,
                target_participants,
                change_action,
            )
        except Exception as exc:
            logger.error(
                "Failed to update group participants",
                group=str(group_jid),
                action=action,
                error=str(exc),
                exc_info=True,
            )
            raise GatewayException(
                f"Failed to update group participants: {exc}"
            ) from exc

    async def set_group_name(self, group_jid: JID, name: str) -> None:
        target_jid = build_jid(group_jid.user, group_jid.server)
        try:
            await asyncio.to_thread(self.client.set_group_name, target_jid, name)
        except Exception as exc:
            logger.error(
                "Failed to set group name",
                group=str(group_jid),
                name=name,
                error=str(exc),
                exc_info=True,
            )
            raise GatewayException(f"Failed to set group name: {exc}") from exc

    async def leave_group(self, group_jid: JID) -> None:
        target_jid = build_jid(group_jid.user, group_jid.server)
        try:
            await asyncio.to_thread(self.client.leave_group, target_jid)
        except Exception as exc:
            logger.error("Failed to leave group", group=str(group_jid), error=str(exc), exc_info=True)
            raise GatewayException(f"Failed to leave group: {exc}") from exc
