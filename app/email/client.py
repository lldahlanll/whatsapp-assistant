# app/email/client.py

import asyncio
import concurrent.futures
import email as email_lib
import imaplib
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from typing import Optional

from loguru import logger

from app.auth.credential_store import UserCredential
from app.config import settings


_IMAP_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

_EMAIL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=10,
    thread_name_prefix="email-io",
)


def imap_date(dt: datetime) -> str:
    """Tanggal IMAP (bahasa Inggris) — %b locale-aware bisa salah di server ID."""
    return f"{dt.day:02d}-{_IMAP_MONTHS[dt.month - 1]}-{dt.year}"


def local_email_now() -> datetime:
    """Waktu 'lokal' email (naive) menurut email_timezone_offset di settings."""
    tz = timezone(timedelta(hours=settings.email_timezone_offset))
    return datetime.now(tz).replace(tzinfo=None)


def local_day_bounds(
    day: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    """Awal dan akhir hari kalender di zona email (mis. WIB)."""
    d = day or local_email_now()
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59)
    return start, end


def to_local_email_time(dt: datetime) -> datetime:
    """Normalisasi timestamp email ke zona settings (untuk filter hari ini)."""
    if dt.tzinfo is not None:
        tz = timezone(timedelta(hours=settings.email_timezone_offset))
        return dt.astimezone(tz).replace(tzinfo=None)
    return dt


async def _run_email_io(fn, /, *args):
    """Jalankan blocking IMAP/SMTP di pool terpisah (tidak memakan default executor)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_EMAIL_EXECUTOR, fn, *args)


# ─────────────────────────────────────────────────────────────
# Custom Exceptions
# ─────────────────────────────────────────────────────────────

class EmailAuthError(Exception):
    """Raised saat IMAP/SMTP auth gagal — credential invalid."""
    pass


class EmailConnectionError(Exception):
    """Raised saat tidak bisa connect ke server (network issue)."""
    pass


# ─────────────────────────────────────────────────────────────
# Data Model
# ─────────────────────────────────────────────────────────────

@dataclass
class EmailMessage:
    uid: str
    subject: str
    sender: str
    sender_email: str
    recipients: list[str]
    body: str
    received_at: datetime
    is_read: bool = False
    message_id: str = ""
    in_reply_to: str = ""
    attachments: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Per-User Zimbra Client
# ─────────────────────────────────────────────────────────────

class ZimbraEmailClient:
    """
    Email client untuk SATU user.

    Server config (host, port) shared dari settings,
    Tapi username & password unique per instance.

    Usage:
        cred = UserCredential(email="user@vci.co.id", password="xxx")
        client = ZimbraEmailClient.for_user(cred)
        emails = await client.fetch_emails(...)
    """

    MAX_BODY_CHARS = 3000
    MAX_RETRIES = 2

    def __init__(self, credential: UserCredential) -> None:
        """
        Args:
            credential: User credential dari auth layer
        """
        self._credential = credential
        # Server config dari settings (shared)
        self._imap_host = settings.imap_host
        self._imap_port = settings.imap_port
        self._smtp_host = settings.smtp_host
        self._smtp_port = settings.smtp_port

        if not all([self._imap_host, self._smtp_host]):
            raise RuntimeError(
                "IMAP_HOST atau SMTP_HOST belum diset di .env"
            )

    # ── Factory Methods ───────────────────────────────────────

    @classmethod
    def for_user(cls, credential: UserCredential) -> "ZimbraEmailClient":
        """Factory method untuk readability."""
        return cls(credential)

    # ── Properties ────────────────────────────────────────────

    @property
    def email(self) -> str:
        """Email address user yang dipakai client ini."""
        return self._credential.email

    @property
    def display_name(self) -> str:
        """Display name untuk email signature."""
        return self._credential.display_name or self._credential.email

    # ── Connection Helpers ────────────────────────────────────

    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        """
        Connect & login IMAP. Raise EmailAuthError kalau credential invalid.
        """
        try:
            if self._imap_port == 993:
                ctx = ssl.create_default_context()
                conn = imaplib.IMAP4_SSL(
                    self._imap_host, self._imap_port, ssl_context=ctx
                )
            else:
                conn = imaplib.IMAP4(self._imap_host, self._imap_port)
                conn.starttls()

            try:
                conn.login(self._credential.email, self._credential.password)
            except imaplib.IMAP4.error as e:
                # Detect auth failure dari berbagai IMAP server format:
                # - Zimbra:    "LOGIN failed"
                # - Gmail:     "Username and Password not accepted"
                # - Dovecot:   "Authentication failed"
                # - Generic:   "AUTHENTICATIONFAILED ..." atau "Invalid credentials"
                err_msg = str(e).upper()
                auth_signals = [
                    "AUTHENTICATIONFAILED",
                    "AUTHENTICATION FAILED",
                    "LOGIN FAILED",
                    "INVALID CREDENTIALS",
                    "INVALID USERNAME",
                    "INVALID PASSWORD",
                    "PASSWORD NOT ACCEPTED",
                    "BAD AUTH",
                    "AUTH FAILED",
                ]
                if any(signal in err_msg for signal in auth_signals):
                    raise EmailAuthError(
                        f"IMAP auth failed for {self._credential.email}: {e}"
                    ) from e
                # Bukan auth error, re-raise as-is (network/server issue)
                raise

            logger.debug(
                f"[IMAP] Connected as {self._credential.email} "
                f"to {self._imap_host}:{self._imap_port}"
            )
            return conn

        except EmailAuthError:
            # Don't catch our own exception
            raise
        except (OSError, ConnectionError) as e:
            raise EmailConnectionError(
                f"Cannot connect to IMAP {self._imap_host}: {e}"
            ) from e

    def _connect_smtp(self) -> smtplib.SMTP:
        """Connect & login SMTP. Raise EmailAuthError kalau credential invalid."""
        try:
            if self._smtp_port == 465:
                ctx = ssl.create_default_context()
                server = smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, context=ctx)
            else:
                server = smtplib.SMTP(self._smtp_host, self._smtp_port)
                server.ehlo()
                server.starttls()
                server.ehlo()

            try:
                server.login(self._credential.email, self._credential.password)
            except smtplib.SMTPAuthenticationError as e:
                # Standard SMTP auth error
                raise EmailAuthError(
                    f"SMTP auth failed for {self._credential.email}: {e}"
                ) from e
            except smtplib.SMTPException as e:
                # Beberapa server return generic SMTPException untuk auth fail
                err_msg = str(e).upper()
                if any(s in err_msg for s in ["AUTH", "LOGIN", "INVALID", "PASSWORD"]):
                    raise EmailAuthError(
                        f"SMTP auth failed for {self._credential.email}: {e}"
                    ) from e
                raise

            logger.debug(
                f"[SMTP] Connected as {self._credential.email} "
                f"to {self._smtp_host}:{self._smtp_port}"
            )
            return server

        except EmailAuthError:
            raise
        except (OSError, ConnectionError) as e:
            raise EmailConnectionError(
                f"Cannot connect to SMTP {self._smtp_host}: {e}"
            ) from e

    # ── Public API — Async wrappers (IMAP/SMTP sync → dedicated thread pool) ──

    async def fetch_emails(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        max_count: int = 10,
        folder: str = "INBOX",
        unread_only: bool = False,
    ) -> list[EmailMessage]:
        """
        Fetch emails. Raise EmailAuthError kalau credential invalid.

        imaplib adalah blocking; kerja IMAP dijalankan di _EMAIL_EXECUTOR
        agar event loop tidak freeze dan tidak memenuhi default thread pool.
        """
        if since is None:
            since, _ = local_day_bounds()

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await _run_email_io(
                    self._sync_fetch_emails,
                    since,
                    until,
                    max_count,
                    folder,
                    unread_only,
                )
            except EmailAuthError:
                # Auth error: jangan retry, langsung propagate
                # (retry pasti gagal, dan akan kunci akun di server)
                logger.warning(
                    f"[IMAP] Auth failed for {self._credential.email} — "
                    "no retry (credential invalid)"
                )
                raise
            except (imaplib.IMAP4.error, OSError, ConnectionError) as e:
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"[IMAP] {self._credential.email} attempt {attempt+1} failed: {e}"
                    )
                    await asyncio.sleep(1.5)
                else:
                    logger.error(
                        f"[IMAP] All {self.MAX_RETRIES+1} attempts failed "
                        f"for {self._credential.email}: {e}"
                    )
                    return []

    async def send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        reply_to_message_id: Optional[str] = None,
        original_subject: Optional[str] = None,
    ) -> bool:
        """Kirim email. Raise EmailAuthError kalau credential invalid."""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await _run_email_io(
                    self._sync_send_email,
                    to,
                    subject,
                    body,
                    reply_to_message_id,
                    original_subject,
                )
            except EmailAuthError:
                logger.warning(
                    f"[SMTP] Auth failed for {self._credential.email} — "
                    "no retry (credential invalid)"
                )
                raise
            except (smtplib.SMTPException, OSError, ConnectionError) as e:
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"[SMTP] {self._credential.email} attempt {attempt+1} failed: {e}"
                    )
                    await asyncio.sleep(1.5)
                else:
                    logger.error(
                        f"[SMTP] All {self.MAX_RETRIES+1} attempts failed "
                        f"for {self._credential.email}: {e}"
                    )
                    return False

    async def get_email_by_uid(
        self,
        uid: str,
        folder: str = "INBOX",
    ) -> Optional[EmailMessage]:
        try:
            return await _run_email_io(self._sync_fetch_by_uid, uid, folder)
        except EmailAuthError:
            raise
        except Exception as e:
            logger.error(
                f"[IMAP] get_email_by_uid failed for {self._credential.email}: {e}"
            )
            return None

    async def get_unread_count(self, folder: str = "INBOX") -> int:
        try:
            return await _run_email_io(self._sync_unread_count, folder)
        except EmailAuthError:
            raise
        except Exception as e:
            logger.error(
                f"[IMAP] get_unread_count failed for {self._credential.email}: {e}"
            )
            return -1

    async def test_connection(self) -> dict[str, bool]:
        """Test IMAP+SMTP login. Dipakai saat /login untuk verify credential."""
        results = {"imap": False, "smtp": False}

        try:
            await _run_email_io(self._sync_test_imap)
            results["imap"] = True
        except EmailAuthError:
            results["imap"] = False  # Auth gagal, return False (caller handle)
        except Exception as e:
            logger.error(f"[IMAP] Test failed: {e}")

        try:
            await _run_email_io(self._sync_test_smtp)
            results["smtp"] = True
        except EmailAuthError:
            results["smtp"] = False
        except Exception as e:
            logger.error(f"[SMTP] Test failed: {e}")

        return results

    @staticmethod
    def _select_mailbox(conn: imaplib.IMAP4_SSL, folder: str) -> None:
        for mailbox in (folder, f'"{folder}"'):
            status, _ = conn.select(mailbox, readonly=True)
            if status == "OK":
                return
        raise EmailConnectionError(f"Cannot select IMAP folder: {folder}")

    @staticmethod
    def _imap_uid_search(conn: imaplib.IMAP4_SSL, criteria: list[str]) -> list[bytes]:
        typ, data = conn.uid("SEARCH", None, *criteria)
        if typ != "OK" or not data or not data[0]:
            return []
        return data[0].split()

    @staticmethod
    def _message_in_range(
        msg: EmailMessage,
        since: datetime,
        until: Optional[datetime],
    ) -> bool:
        t = to_local_email_time(msg.received_at)
        if t < since:
            return False
        if until is not None and t > until:
            return False
        return True

    # ── Sync implementations (di thread pool) ─────────────────

    def _sync_fetch_emails(
        self,
        since: datetime,
        until: Optional[datetime],
        max_count: int,
        folder: str,
        unread_only: bool,
    ) -> list[EmailMessage]:
        conn = self._connect_imap()
        try:
            self._select_mailbox(conn, folder)

            # IMAP SINCE = internal date; buffer 1 hari lalu filter pakai Date header
            imap_since = since - timedelta(days=1)
            criteria: list[str] = ["SINCE", imap_date(imap_since)]

            if until is not None:
                before_day = until.date() + timedelta(days=1)
                criteria.extend(
                    [
                        "BEFORE",
                        imap_date(
                            datetime(
                                before_day.year, before_day.month, before_day.day
                            )
                        ),
                    ]
                )

            if unread_only:
                criteria.append("UNSEEN")

            uids = self._imap_uid_search(conn, criteria)
            search_label = " ".join(criteria)

            if not uids:
                # Fallback: rentang lebih lebar, tetap filter tanggal di aplikasi
                fallback_since = since - timedelta(days=14)
                fb_criteria: list[str] = ["SINCE", imap_date(fallback_since)]
                if unread_only:
                    fb_criteria.append("UNSEEN")
                uids = self._imap_uid_search(conn, fb_criteria)
                search_label = f"fallback: {' '.join(fb_criteria)}"

            if not uids:
                logger.info(
                    f"[IMAP/{self._credential.email}] No emails for: {search_label} "
                    f"(filter since={since:%Y-%m-%d %H:%M}"
                    f"{f' until={until:%Y-%m-%d %H:%M}' if until else ''})"
                )
                return []

            # Ambil lebih banyak kandidat; sisakan yang lolos filter tanggal lokal
            uids_to_fetch = uids[-(max_count * 5) :][::-1]
            logger.info(
                f"[IMAP/{self._credential.email}] UID search {len(uids)} hit, "
                f"fetching up to {len(uids_to_fetch)} ({search_label})"
            )

            messages: list[EmailMessage] = []
            for uid in uids_to_fetch:
                try:
                    msg = self._fetch_and_parse_uid(conn, uid)
                    if msg and self._message_in_range(msg, since, until):
                        messages.append(msg)
                    if len(messages) >= max_count:
                        break
                except Exception as e:
                    logger.warning(f"[IMAP] Parse failed UID {uid}: {e}")
                    continue

            if not messages and uids:
                logger.warning(
                    f"[IMAP/{self._credential.email}] {len(uids)} UID(s) from server "
                    f"but 0 passed date filter since={since:%Y-%m-%d %H:%M}"
                    f"{f' until={until:%Y-%m-%d %H:%M}' if until else ''}"
                )

            return messages
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _sync_fetch_by_uid(self, uid: str, folder: str) -> Optional[EmailMessage]:
        conn = self._connect_imap()
        try:
            self._select_mailbox(conn, folder)
            return self._fetch_and_parse_uid(conn, uid.encode())
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _fetch_and_parse_uid(
        self,
        conn: imaplib.IMAP4_SSL,
        uid: bytes,
    ) -> Optional[EmailMessage]:
        _, msg_data = conn.uid("FETCH", uid, "(RFC822 FLAGS)")
        if not msg_data or msg_data[0] is None:
            return None

        raw_bytes = msg_data[0][1]
        flags = msg_data[0][0].decode() if msg_data[0][0] else ""
        is_read = "\\Seen" in flags

        msg = email_lib.message_from_bytes(raw_bytes)

        subject = self._decode_header_value(msg.get("Subject", "(no subject)"))
        sender_full = self._decode_header_value(msg.get("From", ""))
        sender_email = self._extract_email_address(sender_full)
        recipients_raw = msg.get("To", "")
        recipients = [
            self._extract_email_address(r.strip())
            for r in recipients_raw.split(",")
            if r.strip()
        ]
        message_id = msg.get("Message-ID", "").strip()
        in_reply_to = msg.get("In-Reply-To", "").strip()

        received_at = datetime.now()
        date_str = msg.get("Date", "")
        if date_str:
            try:
                received_at = to_local_email_time(parsedate_to_datetime(date_str))
            except Exception:
                pass

        body, attachments = self._extract_body_and_attachments(msg)

        return EmailMessage(
            uid=uid.decode() if isinstance(uid, bytes) else str(uid),
            subject=subject,
            sender=sender_full,
            sender_email=sender_email,
            recipients=recipients,
            body=body[:self.MAX_BODY_CHARS],
            received_at=received_at,
            is_read=is_read,
            message_id=message_id,
            in_reply_to=in_reply_to,
            attachments=attachments,
        )

    def _sync_send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        reply_to_message_id: Optional[str],
        original_subject: Optional[str],
    ) -> bool:
        final_subject = subject
        if reply_to_message_id and original_subject:
            orig = original_subject.strip()
            final_subject = orig if orig.startswith("Re:") else f"Re: {orig}"

        msg = MIMEMultipart("alternative")
        # From: pakai display_name kalau ada
        if self._credential.display_name:
            msg["From"] = f"{self._credential.display_name} <{self._credential.email}>"
        else:
            msg["From"] = self._credential.email
        msg["To"] = ", ".join(to)
        msg["Subject"] = final_subject

        if reply_to_message_id:
            msg["In-Reply-To"] = reply_to_message_id
            msg["References"] = reply_to_message_id

        msg.attach(MIMEText(body, "plain", "utf-8"))

        server = self._connect_smtp()
        try:
            server.sendmail(self._credential.email, to, msg.as_string())
            logger.info(
                f"[SMTP/{self._credential.email}] ✓ Sent to {to}"
            )
            return True
        finally:
            try:
                server.quit()
            except Exception:
                pass

    def _sync_unread_count(self, folder: str) -> int:
        conn = self._connect_imap()
        try:
            self._select_mailbox(conn, folder)
            uids = self._imap_uid_search(conn, ["UNSEEN"])
            return len(uids)
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _sync_test_imap(self) -> None:
        conn = self._connect_imap()
        conn.noop()
        conn.logout()

    def _sync_test_smtp(self) -> None:
        server = self._connect_smtp()
        server.noop()
        server.quit()

    # ── Parsing Helpers (sama seperti versi sebelumnya) ───────

    @staticmethod
    def _decode_header_value(value: str) -> str:
        if not value:
            return ""
        try:
            parts = decode_header(value)
            decoded = []
            for part, charset in parts:
                if isinstance(part, bytes):
                    decoded.append(part.decode(charset or "utf-8", errors="replace"))
                else:
                    decoded.append(part)
            return "".join(decoded).strip()
        except Exception:
            return value

    @staticmethod
    def _extract_email_address(full: str) -> str:
        match = re.search(r"<([^>]+)>", full)
        if match:
            return match.group(1).strip()
        return full.strip()

    @staticmethod
    def _strip_html(html: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"</?(p|div|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = (
            text.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&nbsp;", " ")
                .replace("&quot;", '"')
        )
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _extract_body_and_attachments(
        self,
        msg: email_lib.message.Message,
    ) -> tuple[str, list[str]]:
        body = ""
        attachments = []
        plain_parts = []
        html_parts = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in disposition:
                    filename = part.get_filename()
                    if filename:
                        attachments.append(self._decode_header_value(filename))
                    continue

                if content_type == "text/plain":
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        plain_parts.append(
                            part.get_payload(decode=True).decode(
                                charset, errors="replace"
                            )
                        )
                    except Exception:
                        pass

                elif content_type == "text/html" and not plain_parts:
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        html_parts.append(
                            part.get_payload(decode=True).decode(
                                charset, errors="replace"
                            )
                        )
                    except Exception:
                        pass
        else:
            content_type = msg.get_content_type()
            charset = msg.get_content_charset() or "utf-8"
            try:
                raw = msg.get_payload(decode=True).decode(charset, errors="replace")
                if content_type == "text/html":
                    html_parts.append(raw)
                else:
                    plain_parts.append(raw)
            except Exception:
                pass

        if plain_parts:
            body = "\n".join(plain_parts)
        elif html_parts:
            body = self._strip_html("\n".join(html_parts))

        return body.strip(), attachments


# ─────────────────────────────────────────────────────────────
# Server Config Validator (dipanggil saat startup)
# ─────────────────────────────────────────────────────────────

def validate_email_server_config() -> bool:
    """
    Cek apakah server config (host/port) sudah lengkap di .env.
    Tidak cek credential — itu per-user.
    """
    required = {
        "IMAP_HOST": settings.imap_host,
        "SMTP_HOST": settings.smtp_host,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.error(
            f"[Email] Server config incomplete: missing {missing}. "
            "Set di .env."
        )
        return False
    logger.info(
        f"[Email] Server config OK → "
        f"IMAP {settings.imap_host}:{settings.imap_port} | "
        f"SMTP {settings.smtp_host}:{settings.smtp_port}"
    )
    return True