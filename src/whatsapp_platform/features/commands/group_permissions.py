"""Permission check for group management commands (!kick, !add, !promote, ...)."""

import structlog

from whatsapp_platform.features.commands.context import CommandContext

logger = structlog.get_logger()

GROUP_ADMIN_ONLY_TEXT = "⛔ Perintah ini hanya bisa dipakai oleh admin grup."


async def require_group_admin(ctx: CommandContext) -> bool:
    """Return True if the sender is an admin of the current group; otherwise reply and return False.

    Fails closed: if the group participant list cannot be fetched, the command is refused.
    """
    sender = ctx.message.sender_jid
    try:
        if ctx.group_mgmt_uc is None:
            raise RuntimeError("group management not configured")
        info = await ctx.group_mgmt_uc.get_group_info(ctx.message.chat_jid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not verify group admin", chat=str(ctx.message.chat_jid), error=str(exc))
        await ctx.reply("❌ Tidak bisa memastikan status admin grup. Coba lagi nanti.")
        return False

    for participant in info.get("participants", []):
        if not participant.get("is_admin"):
            continue
        # Participant bisa tercatat sebagai nomor HP maupun LID; cocokkan keduanya.
        ids = {participant.get("phone") or "", (participant.get("jid") or "").split("@")[0]}
        if sender.user in ids:
            return True

    logger.info(
        "Rejected group command from non-admin",
        command=ctx.command.name,
        sender=str(sender),
        chat=str(ctx.message.chat_jid),
    )
    await ctx.reply(GROUP_ADMIN_ONLY_TEXT)
    return False
