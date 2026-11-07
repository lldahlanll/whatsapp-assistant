"""Eksekutor tool reminder_* terhadap SchedulerService."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

from whatsapp_platform.features.scheduler.formatter import (
    format_recurrence,
    format_when,
    task_title,
)
from whatsapp_platform.features.scheduler.service import SchedulerError
from whatsapp_platform.shared.utils.timezone import parse_local_datetime

if TYPE_CHECKING:
    from whatsapp_platform.domain.value_objects.jid import JID
    from whatsapp_platform.features.scheduler.service import SchedulerService

logger = structlog.get_logger()


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SchedulerError(f"Angka '{value}' tidak valid.") from exc


def _is_group(chat_jid: Any) -> bool:
    if hasattr(chat_jid, "is_group"):
        return bool(chat_jid.is_group)
    return str(chat_jid).endswith("@g.us")


# (group_jid, member_jid) -> True jika admin grup. Exception = tidak bisa dipastikan (fail closed).
AdminCheck = Callable[[Any, Any], Awaitable[bool]]

GROUP_ADMIN_ONLY_MESSAGE = "Di grup, pengingat hanya bisa dibuat atau dihapus oleh admin grup."


class ReminderToolExecutor:
    def __init__(self, scheduler: SchedulerService, is_group_admin: AdminCheck | None = None) -> None:
        self._svc = scheduler
        self._is_group_admin = is_group_admin

    async def _require_admin(self, chat_jid: Any, user_jid: Any) -> None:
        if self._is_group_admin is None:
            raise SchedulerError(GROUP_ADMIN_ONLY_MESSAGE)
        try:
            ok = await self._is_group_admin(chat_jid, user_jid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not verify group admin for reminder", chat=str(chat_jid), error=str(exc))
            raise SchedulerError("Tidak bisa memastikan status admin grup. Coba lagi nanti.") from exc
        if not ok:
            raise SchedulerError(GROUP_ADMIN_ONLY_MESSAGE)

    @property
    def is_enabled(self) -> bool:
        return True

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_jid: JID,
        chat_jid: JID,
        message_id: str | None = None,
        user_text: str | None = None,
    ) -> str:
        owner, chat, is_group = str(user_jid), str(chat_jid), _is_group(chat_jid)
        try:
            if is_group and tool_name in ("reminder_create", "reminder_cancel"):
                await self._require_admin(chat_jid, user_jid)
            if tool_name == "reminder_create":
                return await self._create(owner, chat, is_group, arguments)
            if tool_name == "reminder_list":
                tasks = await self._svc.list_tasks(owner, chat, is_group)
                return json.dumps({
                    "status": "success",
                    "reminders": [
                        {
                            "number": t.short_id,
                            "title": task_title(t),
                            "next_run": format_when(t.next_run_at),
                            "repeat": format_recurrence(t),
                        }
                        for t in tasks
                    ],
                }, ensure_ascii=False)
            if tool_name == "reminder_cancel":
                number = _opt_int(arguments.get("number"))
                if number is None:
                    raise SchedulerError("Sebutkan nomor pengingat yang ingin dihapus.")
                task = await self._svc.cancel_task(owner, number, chat, is_group)
                return json.dumps({
                    "status": "success",
                    "message": f"Pengingat {task.short_id} ('{task_title(task)}') dihapus.",
                }, ensure_ascii=False)
        except SchedulerError as exc:
            return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
        except Exception as exc:
            logger.error("Reminder tool failed", tool=tool_name, error=str(exc), exc_info=True)
            return json.dumps({"status": "error", "message": "Gagal memproses pengingat."})

        return json.dumps({"status": "error", "message": f"Tool '{tool_name}' tidak dikenali."})

    async def _create(self, owner: str, chat: str, is_group: bool, args: dict[str, Any]) -> str:
        run_at = None
        date = args.get("date")
        if date:
            time = args.get("time") or "08:00"
            run_at = parse_local_datetime(f"{date}T{time}" if "T" not in str(date) else str(date))
            if run_at is None:
                raise SchedulerError(f"Tanggal '{date}' tidak valid. Gunakan format YYYY-MM-DD.")

        task = await self._svc.create_task(
            owner,
            chat,
            message=str(args.get("message") or ""),
            kind=args.get("kind") or "reminder",
            recurrence=args.get("recurrence"),
            is_group=is_group,
            delay_minutes=_opt_int(args.get("delay_minutes")),
            run_at=run_at,
            time_of_day=None if run_at else args.get("time"),
            weekday=args.get("weekday") or None,
            day_of_month=_opt_int(args.get("day_of_month")),
        )
        return json.dumps({
            "status": "success",
            "number": task.short_id,
            "title": task_title(task),
            "next_run": format_when(task.next_run_at),
            "repeat": format_recurrence(task),
            "message": (
                f"Pengingat no. {task.short_id} tersimpan, dikirim {format_when(task.next_run_at)} "
                f"({format_recurrence(task)})."
            ),
        }, ensure_ascii=False)
