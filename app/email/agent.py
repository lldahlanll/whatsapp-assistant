# app/email/agent.py
"""
EmailAgent — orchestrator email + AI untuk multi-user mode.

Perubahan dari versi single-user:
- Tidak ada singleton
- Setiap method butuh `credential: UserCredential`
- ZimbraEmailClient di-create per call (lightweight, no persistent connection)

Pattern:
    agent = EmailAgent()
    summary = await agent.fetch_and_summarize(
        credential=user_cred,
        since=datetime.now(),
    )
"""
import re
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from app.ai.prompts import ChatContext
from app.ai.router import route_and_generate
from app.auth.credential_store import UserCredential
from app.email.client import (
    EmailAuthError,
    EmailMessage,
    ZimbraEmailClient,
)


class EmailAgent:
    """
    Stateless agent untuk email operations.

    Tiap method:
    1. Build client per-user dari credential
    2. Execute IMAP/SMTP operation
    3. Optionally invoke AI for summarize/draft
    """

    # ── Prompt Templates (sama seperti sebelumnya) ────────────

    _SUMMARIZE_PROMPT = """\
Kamu adalah asisten email korporat. Analisis daftar email berikut dan buat \
ringkasan eksekutif yang padat.

FORMAT OUTPUT (gunakan format WhatsApp):
*📊 Total:* {count} email ({date_label})

*🔴 Perlu respons segera:*
(list email yang membutuhkan tindakan, atau tulis "Tidak ada" jika kosong)

*📋 Ringkasan per email:*
(nomor | pengirim | topik singkat | status: [Perlu Balas / FYI / Spam])

*💡 Rekomendasi:*
(1-2 kalimat action item paling penting)

DATA EMAIL:
{emails_text}

Jawab dalam Bahasa Indonesia. Ringkas dan actionable.\
"""

    _REPLY_PROMPT = """\
Kamu adalah asisten email korporat profesional.
Tulis balasan email yang tepat berdasarkan instruksi berikut.

EMAIL ASLI:
From: {sender}
Subject: {subject}
Tanggal: {date}
---
{body}
---

INSTRUKSI BALASAN: {instruction}

ATURAN:
- Gunakan bahasa yang SAMA dengan email asli (Indonesia/Inggris)
- Profesional, sopan, dan langsung ke poin
- Sertakan salam pembuka dan penutup yang tepat
- JANGAN tambahkan "[Your Name]" atau placeholder — langsung tulis nama pengirim bot
- Pengirim email ini adalah: {sender_name}

Tulis HANYA isi email balasan, mulai dari salam pembuka.\
"""

    _COMPOSE_PROMPT = """\
Kamu adalah asisten email korporat profesional.
Tulis email baru berdasarkan instruksi berikut.

DETAIL EMAIL:
Kepada: {recipients}
Subjek: {subject}
Instruksi isi: {instruction}
Pengirim (nama): {sender_name}

ATURAN:
- Profesional dan tepat sasaran
- Sertakan salam pembuka dan penutup
- JANGAN tambahkan placeholder seperti [Your Name]
- Gunakan Bahasa Indonesia kecuali instruksi menyebut bahasa lain

Tulis HANYA isi body email, mulai dari salam pembuka.\
"""

    # ── Public API ────────────────────────────────────────────

    async def fetch_and_summarize(
        self,
        credential: UserCredential,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        date_label: str = "hari ini",
        max_count: int = 20,
        unread_only: bool = False,
    ) -> str:
        """
        Fetch + summarize emails untuk user tertentu.

        Raises:
            EmailAuthError: kalau credential invalid
        """
        if since is None:
            since = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        client = ZimbraEmailClient.for_user(credential)

        logger.info(
            f"[EmailAgent/{credential.email}] Fetching since={since}, "
            f"label={date_label}"
        )

        emails = await client.fetch_emails(
            since=since,
            until=until,
            max_count=max_count,
            unread_only=unread_only,
        )

        if not emails:
            qualifier = "belum dibaca " if unread_only else ""
            return f"📭 Tidak ada email {qualifier}masuk {date_label}."

        emails_text = self._format_emails_for_llm(emails)
        prompt = self._SUMMARIZE_PROMPT.format(
            count=len(emails),
            date_label=date_label,
            emails_text=emails_text,
        )

        summary, model_used = await route_and_generate(
            history=[{"role": "user", "content": prompt}],
            user_text=prompt,
            context=ChatContext(push_name="EmailAgent", is_group=False),
        )

        if not summary:
            logger.warning(
                f"[EmailAgent/{credential.email}] AI summarize failed, fallback"
            )
            return self._fallback_summary(emails, date_label)

        logger.info(
            f"[EmailAgent/{credential.email}] ✓ Summarized {len(emails)} via {model_used}"
        )
        return summary

    async def get_email_detail(
        self,
        credential: UserCredential,
        uid: str,
        folder: str = "INBOX",
    ) -> str:
        """Detail satu email."""
        client = ZimbraEmailClient.for_user(credential)
        msg = await client.get_email_by_uid(uid, folder)

        if not msg:
            return f"⚠️ Email UID `{uid}` tidak ditemukan di folder {folder}."

        attachments_text = (
            f"\n📎 *Attachment:* {', '.join(msg.attachments)}"
            if msg.attachments else ""
        )

        return (
            f"📧 *Detail Email*\n"
            f"├ *UID*     : `{msg.uid}`\n"
            f"├ *Dari*    : {msg.sender}\n"
            f"├ *Subjek*  : {msg.subject}\n"
            f"├ *Waktu*   : {msg.received_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"├ *Status*  : {'✓ Dibaca' if msg.is_read else '🔵 Belum dibaca'}"
            f"{attachments_text}\n"
            f"{'─' * 30}\n"
            f"{msg.body[:500]}{'...' if len(msg.body) > 500 else ''}"
        )

    async def draft_reply(
        self,
        credential: UserCredential,
        uid: str,
        instruction: str,
        folder: str = "INBOX",
    ) -> tuple[str, Optional[EmailMessage]]:
        """Generate draft reply (no send)."""
        client = ZimbraEmailClient.for_user(credential)
        msg = await client.get_email_by_uid(uid, folder)

        if not msg:
            return f"⚠️ Email UID `{uid}` tidak ditemukan.", None

        bot_name = credential.display_name or credential.email

        prompt = self._REPLY_PROMPT.format(
            sender=msg.sender,
            subject=msg.subject,
            date=msg.received_at.strftime("%Y-%m-%d %H:%M"),
            body=msg.body[:1500],
            instruction=instruction,
            sender_name=bot_name,
        )

        draft, model_used = await route_and_generate(
            history=[{"role": "user", "content": prompt}],
            user_text=prompt,
            context=ChatContext(push_name="EmailAgent", is_group=False),
        )

        if not draft:
            return "⚠️ Gagal generate draft balasan. Coba lagi.", None

        logger.info(
            f"[EmailAgent/{credential.email}] ✓ Draft via {model_used}"
        )
        return draft, msg

    async def send_reply(
        self,
        credential: UserCredential,
        original_email: EmailMessage,
        draft_body: str,
    ) -> bool:
        """Send draft reply yang sudah disetujui user."""
        client = ZimbraEmailClient.for_user(credential)

        return await client.send_email(
            to=[original_email.sender_email],
            subject=original_email.subject,
            body=draft_body,
            reply_to_message_id=original_email.message_id,
            original_subject=original_email.subject,
        )

    async def compose_and_send(
        self,
        credential: UserCredential,
        to: list[str],
        subject: str,
        instruction: str,
        auto_send: bool = False,
    ) -> tuple[str, bool]:
        """AI compose email baru, optionally kirim langsung."""
        client = ZimbraEmailClient.for_user(credential)
        bot_name = credential.display_name or credential.email

        prompt = self._COMPOSE_PROMPT.format(
            recipients=", ".join(to),
            subject=subject,
            instruction=instruction,
            sender_name=bot_name,
        )

        body, model_used = await route_and_generate(
            history=[{"role": "user", "content": prompt}],
            user_text=prompt,
            context=ChatContext(push_name="EmailAgent", is_group=False),
        )

        if not body:
            return "⚠️ Gagal generate email body.", False

        sent = False
        if auto_send:
            sent = await client.send_email(to=to, subject=subject, body=body)
            logger.info(
                f"[EmailAgent/{credential.email}] compose | sent={sent}"
            )

        return body, sent

    async def ping(self, credential: UserCredential) -> str:
        """Test connection untuk user tertentu."""
        client = ZimbraEmailClient.for_user(credential)
        result = await client.test_connection()
        unread = await client.get_unread_count()

        imap_status = "✓ OK" if result["imap"] else "✗ FAIL"
        smtp_status = "✓ OK" if result["smtp"] else "✗ FAIL"
        unread_text = str(unread) if unread >= 0 else "error"

        return (
            f"📧 *Email Connection — {credential.email}*\n"
            f"├ IMAP    : {imap_status}\n"
            f"├ SMTP    : {smtp_status}\n"
            f"└ Unread  : {unread_text}"
        )

    # ── Internal Helpers ──────────────────────────────────────

    @staticmethod
    def _format_emails_for_llm(emails: list[EmailMessage]) -> str:
        lines = []
        for i, e in enumerate(emails, 1):
            att_text = f" | 📎 {len(e.attachments)} attachment" if e.attachments else ""
            read_text = "dibaca" if e.is_read else "BELUM DIBACA"
            lines.append(
                f"[{i}] UID: {e.uid}\n"
                f"    Dari    : {e.sender}\n"
                f"    Subjek  : {e.subject}\n"
                f"    Waktu   : {e.received_at.strftime('%Y-%m-%d %H:%M')}\n"
                f"    Status  : {read_text}{att_text}\n"
                f"    Preview : {e.body[:300].strip()}...\n"
            )
        return "\n".join(lines)

    @staticmethod
    def _fallback_summary(emails: list[EmailMessage], date_label: str) -> str:
        lines = [f"📧 *{len(emails)} email {date_label}* (summary manual)\n"]
        for i, e in enumerate(emails, 1):
            status = "🔵" if not e.is_read else "✓"
            att = f" 📎{len(e.attachments)}" if e.attachments else ""
            lines.append(
                f"{i}. {status} *{e.subject[:40]}*\n"
                f"   Dari: {e.sender_email}{att}\n"
                f"   {e.received_at.strftime('%H:%M')} | UID: `{e.uid}`"
            )
        return "\n".join(lines)


# Singleton instance — agent stateless, aman jadi singleton
email_agent = EmailAgent()