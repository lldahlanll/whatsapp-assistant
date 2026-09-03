"""FinanceCommandHandler — !finance command with sub-command routing."""

from __future__ import annotations

from decimal import Decimal

from whatsapp_platform.domain.entities.finance import AccountType
from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.finance.formatter import (
    format_accounts_list,
    format_balance,
    format_budget_list,
    format_budget_progress,
    format_finance_error,
    format_monthly_report,
    format_transaction_added,
    format_transactions_list,
)
from whatsapp_platform.features.finance.parser import (
    parse_amount_from_text,
    parse_description_without_amount,
)
from whatsapp_platform.features.finance.service import (
    FinanceService,
    FinanceServiceError,
)

_HELP_TEXT = (
    "💰 *PANDUAN PERINTAH FINANCE*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📥 *Pemasukan:*\n"
    "  `!finance masuk 5jt gaji`\n"
    "  `!finance masuk 500rb freelance`\n"
    "\n"
    "📤 *Pengeluaran:*\n"
    "  `!finance keluar 50rb makan siang`\n"
    "  `!finance keluar 150k bensin`\n"
    "\n"
    "🔄 *Transfer:*\n"
    "  `!finance transfer 100rb BCA BRI`\n"
    "\n"
    "🎯 *Budget / Anggaran:*\n"
    "  `!finance budget` — lihat semua budget bulan ini\n"
    "  `!finance budget makan 1jt` — atur budget kategori\n"
    "  `!finance budget makan` — cek progres budget\n"
    "  `!finance budget hapus makan` — hapus budget\n"
    "\n"
    "💰 *Saldo & Laporan:*\n"
    "  `!finance saldo` — lihat semua saldo\n"
    "  `!finance riwayat [n]` — transaksi terakhir\n"
    "  `!finance laporan [bulan]` — laporan bulanan\n"
    "\n"
    "🏦 *Rekening:*\n"
    "  `!finance rekening` — daftar rekening\n"
    "  `!finance rekening baru BCA bank 5jt`\n"
    "  `!finance rekening baru GoPay ewallet 200rb`\n"
    "  _Format: baru <nama> [tipe] [saldo_awal]_\n"
    "  _Tipe: cash · bank · ewallet · savings · investment_\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "💡 _Atau cukup ngobrol natural dengan Nara:_\n"
    "  _'budget makan bulan ini 1 juta'_\n"
    "  _'berapa sisa budget makan?'_\n"
    "  _'tampilkan budget bulan ini'_\n"
    "  _'catat pengeluaran 50rb buat makan'_\n"
    "  _'berapa saldo aku sekarang?'_\n"
    "  _'laporan keuangan bulan ini'_\n"
    "  _'buat rekening BCA dengan saldo awal 5 juta'_"
)


class FinanceCommandHandler(BaseCommandHandler):

    def __init__(self, finance_service: FinanceService) -> None:
        self._svc = finance_service

    @property
    def command_name(self) -> str:
        return "finance"

    @property
    def description(self) -> str:
        return "Pencatatan keuangan pribadi (!finance saldo/masuk/keluar/transfer/laporan)"

    async def handle(self, ctx: CommandContext) -> None:
        owner_jid = str(ctx.message.sender_jid)
        args = ctx.command.args

        if not args or args[0].lower() in ("help", "bantuan", "panduan"):
            await ctx.reply(_HELP_TEXT)
            return

        sub = args[0].lower()
        rest = args[1:]

        try:
            if sub in ("saldo", "balance", "cek"):
                await self._handle_saldo(ctx, owner_jid)

            elif sub in ("masuk", "income", "pemasukan", "in"):
                await self._handle_income(ctx, owner_jid, rest)

            elif sub in ("keluar", "expense", "pengeluaran", "out", "catat"):
                await self._handle_expense(ctx, owner_jid, rest)

            elif sub in ("transfer", "tf", "pindah"):
                await self._handle_transfer(ctx, owner_jid, rest)

            elif sub in ("riwayat", "histori", "history", "list"):
                await self._handle_history(ctx, owner_jid, rest)

            elif sub in ("laporan", "report", "rekap", "summary"):
                await self._handle_report(ctx, owner_jid, rest)

            elif sub in ("rekening", "akun", "account"):
                await self._handle_account(ctx, owner_jid, rest)

            elif sub in ("kategori", "category"):
                await self._handle_categories(ctx, owner_jid)

            elif sub in ("budget", "anggaran"):
                await self._handle_budget(ctx, owner_jid, rest)

            else:
                await ctx.reply(
                    f"❓ Sub-command `!finance {sub}` tidak dikenal.\n"
                    "Ketik `!finance help` untuk melihat panduan."
                )

        except FinanceServiceError as exc:
            await ctx.reply(format_finance_error(exc))
        except Exception as exc:
            await ctx.reply(format_finance_error(exc))

    # ── Sub-command handlers ──────────────────────────────────────────────────

    async def _handle_saldo(self, ctx: CommandContext, owner_jid: str) -> None:
        data = await self._svc.get_total_balance(owner_jid)
        await ctx.reply(format_balance(data))

    async def _handle_income(
        self, ctx: CommandContext, owner_jid: str, rest: list[str]
    ) -> None:
        if not rest:
            await ctx.reply("❌ Contoh: `!finance masuk 5jt gaji bulan ini`")
            return
        text = " ".join(rest)
        amount = parse_amount_from_text(text)
        if not amount or amount <= 0:
            await ctx.reply(
                "❌ Jumlah tidak terbaca. Contoh: `!finance masuk 5jt gaji`"
            )
            return
        description = parse_description_without_amount(text) or None
        tx = await self._svc.add_income(
            owner_jid=owner_jid,
            amount=amount,
            description=description,
        )
        await ctx.reply(format_transaction_added(tx))

    async def _handle_expense(
        self, ctx: CommandContext, owner_jid: str, rest: list[str]
    ) -> None:
        if not rest:
            await ctx.reply("❌ Contoh: `!finance keluar 50rb makan siang`")
            return
        text = " ".join(rest)
        amount = parse_amount_from_text(text)
        if not amount or amount <= 0:
            await ctx.reply(
                "❌ Jumlah tidak terbaca. Contoh: `!finance keluar 50rb makan`"
            )
            return
        description = parse_description_without_amount(text) or None
        tx = await self._svc.add_expense(
            owner_jid=owner_jid,
            amount=amount,
            description=description,
        )
        await ctx.reply(format_transaction_added(tx))

    async def _handle_transfer(
        self, ctx: CommandContext, owner_jid: str, rest: list[str]
    ) -> None:
        if len(rest) < 3:
            await ctx.reply(
                "❌ Format: `!finance transfer <jumlah> <dari> <ke>`\n"
                "Contoh: `!finance transfer 500rb BCA BRI`"
            )
            return
        text = " ".join(rest)
        amount = parse_amount_from_text(text)
        if not amount or amount <= 0:
            await ctx.reply("❌ Jumlah tidak terbaca.")
            return

        from_name = rest[-2]
        to_name = rest[-1]

        from_acc = await self._svc.find_account_by_name(owner_jid, from_name)
        to_acc = await self._svc.find_account_by_name(owner_jid, to_name)

        if not from_acc:
            await ctx.reply(
                f"❌ Rekening *{from_name}* tidak ditemukan.\n"
                "Lihat rekening dengan `!finance rekening`."
            )
            return
        if not to_acc:
            await ctx.reply(
                f"❌ Rekening *{to_name}* tidak ditemukan.\n"
                "Lihat rekening dengan `!finance rekening`."
            )
            return

        tx = await self._svc.transfer(
            owner_jid=owner_jid,
            amount=amount,
            from_account_id=from_acc.id,
            to_account_id=to_acc.id,
        )
        await ctx.reply(format_transaction_added(tx))

    async def _handle_history(
        self, ctx: CommandContext, owner_jid: str, rest: list[str]
    ) -> None:
        limit = 10
        if rest:
            try:
                limit = min(int(rest[0]), 30)
            except ValueError:
                pass
        transactions = await self._svc.get_recent_transactions(owner_jid, limit=limit)
        await ctx.reply(format_transactions_list(transactions))

    async def _handle_report(
        self, ctx: CommandContext, owner_jid: str, rest: list[str]
    ) -> None:
        import calendar

        month = None
        year = None
        if rest:
            month_map = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
            month_map_id = {
                "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "jun": 6,
                "jul": 7, "agu": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
                "januari": 1, "februari": 2, "maret": 3, "april": 4,
                "juni": 6, "juli": 7, "agustus": 8, "september": 9,
                "oktober": 10, "november": 11, "desember": 12,
            }
            arg = rest[0].lower()
            if arg in month_map:
                month = month_map[arg]
            elif arg in month_map_id:
                month = month_map_id[arg]
            else:
                try:
                    month = int(arg)
                except ValueError:
                    pass

        summary = await self._svc.get_monthly_report(owner_jid, year=year, month=month)
        await ctx.reply(format_monthly_report(summary))

    async def _handle_account(
        self, ctx: CommandContext, owner_jid: str, rest: list[str]
    ) -> None:
        if not rest or rest[0].lower() in ("list", "daftar", "semua"):
            accounts = await self._svc.get_accounts(owner_jid)
            await ctx.reply(format_accounts_list(accounts))
            return

        if rest[0].lower() == "baru":
            if len(rest) < 2:
                await ctx.reply(
                    "❌ Format: `!finance rekening baru <nama> [tipe] [saldo_awal]`\n"
                    "Tipe: `cash`, `bank`, `ewallet`, `savings`, `investment`\n"
                    "Contoh:\n"
                    "  `!finance rekening baru BCA bank 5jt`\n"
                    "  `!finance rekening baru GoPay ewallet 200rb`\n"
                    "  `!finance rekening baru Kas` _(saldo awal 0)_"
                )
                return
            name = rest[1]
            acc_type = AccountType.CASH
            initial_balance = Decimal("0")

            type_map = {
                "cash": AccountType.CASH, "kas": AccountType.CASH,
                "bank": AccountType.BANK,
                "ewallet": AccountType.EWALLET, "dompet": AccountType.EWALLET,
                "savings": AccountType.SAVINGS, "tabungan": AccountType.SAVINGS,
                "investment": AccountType.INVESTMENT, "investasi": AccountType.INVESTMENT,
            }

            # Parse tipe dan saldo awal dari sisa argumen (urutan bebas)
            for token in rest[2:]:
                parsed = parse_amount_from_text(token)
                if parsed is not None and parsed > 0:
                    initial_balance = parsed
                elif token.lower() in type_map:
                    acc_type = type_map[token.lower()]

            acc = await self._svc.create_account(
                owner_jid, name, acc_type, initial_balance
            )
            saldo_str = f"Rp {int(initial_balance):,}".replace(",", ".")
            await ctx.reply(
                f"✅ *Rekening baru berhasil dibuat!*\n"
                f"🏦 Nama: {acc.name}\n"
                f"📋 Tipe: {acc.account_type.value}\n"
                f"💰 Saldo awal: {saldo_str}"
            )
            return

        accounts = await self._svc.get_accounts(owner_jid)
        await ctx.reply(format_accounts_list(accounts))

    async def _handle_categories(self, ctx: CommandContext, owner_jid: str) -> None:
        await self._svc.ensure_defaults(owner_jid)
        categories = await self._svc._repo.get_categories(owner_jid)

        expense_cats = [c for c in categories if c.category_type.value == "expense"]
        income_cats = [c for c in categories if c.category_type.value == "income"]

        lines = ["📁 *Kategori Keuangan*", "━━━━━━━━━━━━━━━━━━"]
        lines.append("📤 *Pengeluaran:*")
        for cat in expense_cats:
            lines.append(f"  {cat.icon or '•'} {cat.name}")
        lines.append("")
        lines.append("📥 *Pemasukan:*")
        for cat in income_cats:
            lines.append(f"  {cat.icon or '•'} {cat.name}")

        await ctx.reply("\n".join(lines))

    async def _handle_budget(
        self, ctx: CommandContext, owner_jid: str, rest: list[str]
    ) -> None:
        from datetime import UTC, datetime
        now = datetime.now(UTC)

        # 1. List budgets: "!finance budget" or "!finance budget list" or "!finance budget semua"
        if not rest or rest[0].lower() in ("list", "daftar", "semua"):
            budgets = await self._svc.list_budgets(owner_jid)
            await ctx.reply(format_budget_list(budgets, now.month, now.year))
            return

        # 2. Delete budget: "!finance budget hapus <kategori>"
        if rest[0].lower() in ("hapus", "delete", "remove"):
            if len(rest) < 2:
                await ctx.reply("❌ Format: `!finance budget hapus <kategori>`\nContoh: `!finance budget hapus makan`")
                return
            category_name = " ".join(rest[1:])
            await self._svc.delete_budget(owner_jid, category_name)
            await ctx.reply(f"✅ Budget untuk kategori *{category_name}* bulan ini berhasil dihapus.")
            return

        # 3. Check if an amount is present -> Create / Update budget
        text = " ".join(rest)
        amount = parse_amount_from_text(text)
        if amount is not None and amount > 0:
            category_name = parse_description_without_amount(text)
            if not category_name:
                category_name = rest[0]
            progress = await self._svc.set_budget(owner_jid, category_name, amount)
            await ctx.reply(f"✅ *Budget Berhasil Diatur!*\n\n{format_budget_progress(progress)}")
            return

        # 4. No amount -> View single budget progress: "!finance budget <kategori>"
        category_name = text
        progress = await self._svc.get_budget_progress(owner_jid, category_name)
        if not progress:
            await ctx.reply(
                f"ℹ️ Belum ada budget untuk kategori *{category_name}* bulan ini.\n"
                f"Gunakan `!finance budget {category_name} <nominal>` untuk membuatnya."
            )
        else:
            await ctx.reply(format_budget_progress(progress))

