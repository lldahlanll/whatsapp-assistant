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
        is_admin = await ctx.group_mgmt_uc.is_admin(ctx.message.chat_jid, sender)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not verify group admin", chat=str(ctx.message.chat_jid), error=str(exc))
        await ctx.reply("❌ Tidak bisa memastikan status admin grup. Coba lagi nanti.")
        return False

    if is_admin:
        return True

    logger.info(
        "Rejected group command from non-admin",
        command=ctx.command.name,
        sender=str(sender),
        chat=str(ctx.message.chat_jid),
    )
    await ctx.reply(GROUP_ADMIN_ONLY_TEXT)
    return False
