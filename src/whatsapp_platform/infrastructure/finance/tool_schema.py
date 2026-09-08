"""Finance AI Tool definitions for LLM function calling."""

from __future__ import annotations

from whatsapp_platform.infrastructure.mikrotik.tool_schema import ToolDefinition, ToolParameter

FINANCE_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="finance_add_income",
        description=(
            "Mencatat pemasukan / pendapatan ke rekening keuangan pribadi pengguna. "
            "Gunakan ketika pengguna menyebutkan gaji masuk, terima uang, dapat transfer, "
            "freelance dibayar, bonus, dll."
        ),
        parameters=[
            ToolParameter(
                name="amount",
                type="number",
                description="Jumlah pemasukan dalam Rupiah (angka saja, tanpa simbol).",
                required=True,
            ),
            ToolParameter(
                name="description",
                type="string",
                description="Deskripsi singkat pemasukan, contoh: 'gaji bulan Agustus', 'bayaran freelance'.",
                required=False,
            ),
            ToolParameter(
                name="category_name",
                type="string",
                description=(
                    "Nama kategori pemasukan, contoh: 'Gaji', 'Freelance', 'Bonus', 'Bisnis'. "
                    "Kosongkan jika tidak disebutkan."
                ),
                required=False,
            ),
            ToolParameter(
                name="account_name",
                type="string",
                description=(
                    "Nama rekening tujuan pemasukan, contoh: 'BCA', 'BRI', 'Kas'. "
                    "Jika tidak disebutkan dan pengguna belum punya default account, kosongkan."
                ),
                required=False,
            ),
            ToolParameter(
                name="date",
                type="string",
                description="Tanggal transaksi (format: YYYY-MM-DD, misal: '2026-08-20'). Kosongkan jika transaksi hari ini.",
                required=False,
            ),
            ToolParameter(
                name="idempotency_key",
                type="string",
                description="ID pesan unik untuk mencegah transaksi ganda (opsional).",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_add_expense",
        description=(
            "Mencatat pengeluaran / biaya dari rekening keuangan pribadi pengguna. "
            "Gunakan ketika pengguna menyebutkan beli sesuatu, bayar tagihan, "
            "ngeluarin uang, belanja, transfer keluar, dll."
        ),
        parameters=[
            ToolParameter(
                name="amount",
                type="number",
                description="Jumlah pengeluaran dalam Rupiah (angka saja, tanpa simbol).",
                required=True,
            ),
            ToolParameter(
                name="description",
                type="string",
                description="Deskripsi singkat pengeluaran, contoh: 'makan siang', 'bensin motor', 'listrik'.",
                required=False,
            ),
            ToolParameter(
                name="category_name",
                type="string",
                description=(
                    "Nama kategori pengeluaran, contoh: 'Makanan & Minuman', 'Transport', "
                    "'Tagihan & Utilitas', 'Belanja', 'Kesehatan'. Kosongkan jika tidak disebutkan."
                ),
                required=False,
            ),
            ToolParameter(
                name="account_name",
                type="string",
                description=(
                    "Nama rekening sumber pengeluaran, contoh: 'BCA', 'Kas', 'GoPay'. "
                    "Jika tidak disebutkan dan pengguna tidak punya default account, kosongkan."
                ),
                required=False,
            ),
            ToolParameter(
                name="date",
                type="string",
                description="Tanggal transaksi (format: YYYY-MM-DD, misal: '2026-08-20'). Kosongkan jika transaksi hari ini.",
                required=False,
            ),
            ToolParameter(
                name="idempotency_key",
                type="string",
                description="ID pesan unik untuk mencegah transaksi ganda (opsional).",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_transfer",
        description=(
            "Memindahkan dana antar rekening milik pengguna, "
            "contoh: transfer dari rekening BCA ke GoPay, dari Kas ke tabungan."
        ),
        parameters=[
            ToolParameter(
                name="amount",
                type="number",
                description="Jumlah yang ditransfer dalam Rupiah.",
                required=True,
            ),
            ToolParameter(
                name="from_account_name",
                type="string",
                description="Nama rekening asal dana.",
                required=True,
            ),
            ToolParameter(
                name="to_account_name",
                type="string",
                description="Nama rekening tujuan dana.",
                required=True,
            ),
            ToolParameter(
                name="description",
                type="string",
                description="Catatan transfer (opsional).",
                required=False,
            ),
            ToolParameter(
                name="date",
                type="string",
                description="Tanggal transaksi (format: YYYY-MM-DD, misal: '2026-08-20'). Kosongkan jika transaksi hari ini.",
                required=False,
            ),
            ToolParameter(
                name="idempotency_key",
                type="string",
                description="ID pesan unik untuk mencegah transaksi ganda (opsional).",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_get_balance",
        description=(
            "Mengambil saldo terkini semua rekening keuangan pribadi pengguna. "
            "Gunakan ketika pengguna bertanya soal saldo, kondisi keuangan, ada berapa uang, dll."
        ),
        parameters=[],
    ),
    ToolDefinition(
        name="finance_get_monthly_report",
        description=(
            "Mengambil laporan keuangan bulanan: total pemasukan, total pengeluaran, "
            "nett cashflow, dan top kategori pengeluaran. "
            "Gunakan ketika pengguna meminta laporan, rekap bulan ini, atau summary keuangan."
        ),
        parameters=[
            ToolParameter(
                name="month",
                type="integer",
                description="Bulan (1-12). Kosongkan untuk bulan berjalan.",
                required=False,
            ),
            ToolParameter(
                name="year",
                type="integer",
                description="Tahun (contoh: 2026). Kosongkan untuk tahun berjalan.",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_get_transactions",
        description=(
            "Mengambil riwayat transaksi pengguna dengan filter opsional. "
            "Gunakan ketika pengguna ingin melihat histori transaksi, "
            "cek pengeluaran terakhir, atau mencari transaksi tertentu."
        ),
        parameters=[
            ToolParameter(
                name="limit",
                type="integer",
                description="Jumlah transaksi yang ditampilkan (default 10, maksimal 30).",
                required=False,
            ),
            ToolParameter(
                name="account_name",
                type="string",
                description="Filter berdasarkan nama rekening (opsional).",
                required=False,
            ),
            ToolParameter(
                name="transaction_type",
                type="string",
                description="Filter tipe transaksi: 'income', 'expense', atau 'transfer' (opsional).",
                required=False,
            ),
            ToolParameter(
                name="date_from",
                type="string",
                description="Filter dari tanggal (format: YYYY-MM-DD, opsional).",
                required=False,
            ),
            ToolParameter(
                name="date_to",
                type="string",
                description="Filter sampai tanggal (format: YYYY-MM-DD, opsional).",
                required=False,
            ),
            ToolParameter(
                name="category_name",
                type="string",
                description="Filter berdasarkan nama kategori (opsional).",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_get_expense_summary",
        description=(
            "Mengambil ringkasan pengeluaran per kategori untuk bulan tertentu. "
            "Berguna untuk melihat pos pengeluaran terbesar, analisis kebiasaan belanja."
        ),
        parameters=[
            ToolParameter(
                name="month",
                type="integer",
                description="Bulan (1-12). Kosongkan untuk bulan berjalan.",
                required=False,
            ),
            ToolParameter(
                name="year",
                type="integer",
                description="Tahun. Kosongkan untuk tahun berjalan.",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_create_account",
        description=(
            "Membuat rekening atau dompet baru untuk keuangan pengguna dengan saldo awal. "
            "Contoh: buat rekening BCA saldo awal 5 juta, tambah akun GoPay 200rb, dll."
        ),
        parameters=[
            ToolParameter(
                name="name",
                type="string",
                description="Nama rekening/dompet (misal: 'BCA', 'Mandiri', 'GoPay', 'OVO', 'Kas').",
                required=True,
            ),
            ToolParameter(
                name="account_type",
                type="string",
                description="Tipe rekening: 'cash', 'bank', 'ewallet', 'savings', atau 'investment'. Default 'bank'.",
                required=False,
            ),
            ToolParameter(
                name="initial_balance",
                type="number",
                description="Saldo awal saat rekening dibuat dalam Rupiah. Default 0.",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_delete_account",
        description=(
            "Menghapus atau menonaktifkan rekening/tabungan milik pengguna. "
            "PENTING: Selalu panggil dengan confirm=False terlebih dahulu untuk memeriksa sisa saldo dan mendapatkan konfirmasi dari pengguna, "
            "kecuali jika pengguna sudah secara eksplisit mengonfirmasi (misal: 'Ya saya yakin hapus rekening BCA')."
        ),
        parameters=[
            ToolParameter(
                name="name",
                type="string",
                description="Nama rekening/dompet yang ingin dihapus (misal: 'BCA', 'GoPay', 'Tabungan').",
                required=True,
            ),
            ToolParameter(
                name="confirm",
                type="boolean",
                description="Set true jika pengguna sudah memberikan konfirmasi eksplisit untuk menghapus rekening.",
                required=False,
            ),
        ],
    ),
    # ── NEW TOOLS (Level 1 additions) ─────────────────────────────────────────
    ToolDefinition(
        name="finance_get_accounts",
        description=(
            "Mengambil daftar semua rekening/dompet aktif milik pengguna. "
            "Gunakan SEBELUM mencatat transaksi jika akun tidak disebutkan, "
            "agar tidak menebak akun. Juga gunakan saat pengguna bertanya: "
            "'Rekening aku apa aja?', 'Aku punya dompet mana?', dll."
        ),
        parameters=[],
    ),
    ToolDefinition(
        name="finance_get_categories",
        description=(
            "Mengambil daftar semua kategori pemasukan dan pengeluaran yang tersedia. "
            "Gunakan SEBELUM mencatat transaksi jika tidak yakin kategori mana yang sesuai, "
            "agar tidak mengarang nama kategori yang tidak ada. "
            "Juga gunakan saat pengguna bertanya kategori apa saja yang ada."
        ),
        parameters=[
            ToolParameter(
                name="category_type",
                type="string",
                description="Filter tipe kategori: 'income' atau 'expense'. Kosongkan untuk semua kategori.",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_get_transaction_detail",
        description=(
            "Mencari dan mengambil detail transaksi berdasarkan kata kunci deskripsi atau tanggal. "
            "WAJIB dipanggil sebelum finance_update_transaction atau finance_delete_transaction "
            "untuk mendapatkan transaction_id yang tepat. "
            "Contoh: 'kopi tadi', 'makan siang kemarin', 'gaji bulan lalu'."
        ),
        parameters=[
            ToolParameter(
                name="keyword",
                type="string",
                description="Kata kunci dari deskripsi transaksi yang dicari, contoh: 'kopi', 'makan', 'gaji'.",
                required=False,
            ),
            ToolParameter(
                name="date",
                type="string",
                description="Filter tanggal transaksi (format: YYYY-MM-DD, opsional).",
                required=False,
            ),
            ToolParameter(
                name="transaction_type",
                type="string",
                description="Filter tipe: 'income', 'expense', atau 'transfer' (opsional).",
                required=False,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Jumlah hasil maksimal (default 5).",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_update_transaction",
        description=(
            "Mengubah / mengoreksi transaksi yang sudah ada. "
            "HARUS menggunakan transaction_id yang diperoleh dari finance_get_transaction_detail. "
            "Contoh penggunaan: 'kopi tadi sebenarnya 25 ribu', 'koreksi gaji jadi 7 juta'."
        ),
        parameters=[
            ToolParameter(
                name="transaction_id",
                type="string",
                description="ID transaksi yang akan diubah (human ID seperti TXN-20260820-ABC123 atau UUID).",
                required=True,
            ),
            ToolParameter(
                name="new_amount",
                type="number",
                description="Jumlah baru dalam Rupiah (opsional, isi jika jumlah berubah).",
                required=False,
            ),
            ToolParameter(
                name="new_description",
                type="string",
                description="Deskripsi baru (opsional, isi jika deskripsi berubah).",
                required=False,
            ),
            ToolParameter(
                name="new_category_name",
                type="string",
                description="Nama kategori baru (opsional, isi jika kategori berubah).",
                required=False,
            ),
            ToolParameter(
                name="new_account_name",
                type="string",
                description="Nama rekening baru (opsional, isi jika rekening berubah).",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_delete_transaction",
        description=(
            "Menghapus transaksi dari catatan keuangan. "
            "HARUS menggunakan transaction_id yang diperoleh dari finance_get_transaction_detail. "
            "Jangan menghapus berdasarkan deskripsi secara langsung — selalu resolve dulu. "
            "Contoh: 'hapus transaksi kopi tadi', 'batalkan pencatatan makan siang kemarin'."
        ),
        parameters=[
            ToolParameter(
                name="transaction_id",
                type="string",
                description="ID transaksi yang akan dihapus (human ID seperti TXN-20260820-ABC123 atau UUID).",
                required=True,
            ),
        ],
    ),
    # ── BUDGET TOOLS ──────────────────────────────────────────────────────────
    ToolDefinition(
        name="finance_create_budget",
        description=(
            "Membuat atau memperbarui (upsert) budget / anggaran pengeluaran untuk kategori tertentu. "
            "Contoh: 'Budget makan bulan ini 1 juta', 'Buat budget transport 500rb bulan ini', "
            "'Atur budget hiburan 300rb'."
        ),
        parameters=[
            ToolParameter(
                name="category_name",
                type="string",
                description="Nama kategori pengeluaran (misal: 'Makanan & Minuman', 'Transport', 'Hiburan').",
                required=True,
            ),
            ToolParameter(
                name="amount",
                type="number",
                description="Nominal budget dalam Rupiah (angka positif).",
                required=True,
            ),
            ToolParameter(
                name="month",
                type="integer",
                description="Bulan (1-12). Kosongkan jika untuk bulan berjalan.",
                required=False,
            ),
            ToolParameter(
                name="year",
                type="integer",
                description="Tahun (misal: 2026). Kosongkan jika untuk tahun berjalan.",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_get_budget",
        description=(
            "Mengambil status dan progress budget untuk kategori pengeluaran tertentu. "
            "Menampilkan nominal budget, total terpakai (spent), sisa saldo budget, dan persentase progress. "
            "Contoh: 'Berapa sisa budget makan?', 'Apakah budget transport saya hampir habis?', "
            "'Budget makan bulan ini berapa?'."
        ),
        parameters=[
            ToolParameter(
                name="category_name",
                type="string",
                description="Nama kategori pengeluaran yang ingin dicek budget-nya.",
                required=True,
            ),
            ToolParameter(
                name="month",
                type="integer",
                description="Bulan (1-12). Kosongkan untuk bulan berjalan.",
                required=False,
            ),
            ToolParameter(
                name="year",
                type="integer",
                description="Tahun. Kosongkan untuk tahun berjalan.",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_list_budgets",
        description=(
            "Mengambil daftar semua budget aktif beserta progress pengeluarannya pada bulan tertentu. "
            "Contoh: 'Tampilkan semua budget bulan ini', 'Daftar budget aktif', 'Budget bulan ini apa aja?'."
        ),
        parameters=[
            ToolParameter(
                name="month",
                type="integer",
                description="Bulan (1-12). Kosongkan untuk bulan berjalan.",
                required=False,
            ),
            ToolParameter(
                name="year",
                type="integer",
                description="Tahun. Kosongkan untuk tahun berjalan.",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="finance_delete_budget",
        description=(
            "Menghapus budget kategori pengeluaran tertentu pada bulan tertentu. "
            "Contoh: 'Hapus budget hiburan bulan ini', 'Batalkan anggaran belanja'."
        ),
        parameters=[
            ToolParameter(
                name="category_name",
                type="string",
                description="Nama kategori budget yang akan dihapus.",
                required=True,
            ),
            ToolParameter(
                name="month",
                type="integer",
                description="Bulan (1-12). Kosongkan untuk bulan berjalan.",
                required=False,
            ),
            ToolParameter(
                name="year",
                type="integer",
                description="Tahun. Kosongkan untuk tahun berjalan.",
                required=False,
            ),
        ],
    ),
    # ── Reset Tool ────────────────────────────────────────────────────────────
    ToolDefinition(
        name="finance_reset_data",
        description=(
            "Menghapus SEMUA data finance pengguna (rekening, transaksi, budget, kategori) "
            "dan mereset ke kondisi nol bersih. "
            "PERINGATAN KRITIS: Aksi ini permanen dan tidak bisa dibatalkan. "
            "WAJIB minta konfirmasi eksplisit dari pengguna sebelum memanggil dengan confirm=True. "
            "Jika confirm=False, hanya tampilkan preview jumlah data yang akan dihapus tanpa menghapus. "
            "Contoh trigger: 'reset semua data keuangan', 'hapus semua data finance', "
            "'mulai dari nol lagi', 'bersihkan semua catatan keuangan'."
        ),
        parameters=[
            ToolParameter(
                name="confirm",
                type="boolean",
                description=(
                    "Set True HANYA jika pengguna sudah memberikan konfirmasi eksplisit "
                    "(contoh: 'ya, hapus semuanya', 'iya saya yakin'). "
                    "Set False (default) untuk menampilkan preview tanpa menghapus."
                ),
                required=False,
            ),
        ],
    ),
]


