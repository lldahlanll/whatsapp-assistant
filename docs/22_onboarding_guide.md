# DOC-025 · Developer Onboarding Guide

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Technical Writer + Senior Developer  

---

## 🎯 Objective

Panduan ini bertujuan untuk membawa developer baru agar dapat memahami arsitektur, menjalankan lingkungan lokal, dan mulai menulis kode dalam **kurang dari 1 jam**.

---

## 🚀 15-Minute Environment Setup

### 1. Prerequisites Check
Pastikan sistem Anda sudah memiliki:
- macOS / Linux (Windows via WSL2 disarankan)
- Python 3.13+ (`python3 --version`)
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Git & Docker Desktop

### 2. Repository Initialization
```bash
git clone https://github.com/your-org/whatsapp-platform.git
cd whatsapp-platform

# Install virtualenv & all dependencies via uv
uv sync

# Install pre-commit hooks
uv run pre-commit install
```

### 3. Verification Run
Jalankan test suite untuk memastikan environment berfungsi 100%:
```bash
uv run pytest
```

---

## 💡 How to Add a New Bot Command (In 5 Steps)

Salah satu tugas pengembang paling umum adalah menambahkan command baru (misal: `!quote`).

### Step 1: Create Handler File
Buat file baru di `src/whatsapp_platform/features/commands/handlers/quote.py`:

```python
from whatsapp_platform.features.commands.context import CommandContext

class QuoteHandler:
    @property
    def name(self) -> str:
        return "quote"

    @property
    def description(self) -> str:
        return "Dapatkan kutipan inspiratif acak"

    @property
    def usage(self) -> str:
        return "!quote"

    async def handle(self, ctx: CommandContext) -> None:
        quote = "Coding is turned into art when architecture is clean."
        await ctx.reply(quote)
```

### Step 2: Register in Feature Module
Buka `src/whatsapp_platform/features/commands/__init__.py` dan daftarkan handler baru:

```python
command_registry.register(
    command_name="quote",
    handler=QuoteHandler(),
    aliases=["q"],
    description="Random quote"
)
```

### Step 3: Add Unit Test
Buat test di `tests/unit/features/test_quote_handler.py`:
```python
import pytest
from whatsapp_platform.features.commands.handlers.quote import QuoteHandler

@pytest.mark.asyncio
async def test_quote_handler_replies_quote(mock_context):
    handler = QuoteHandler()
    await handler.handle(mock_context)
    mock_context.reply.assert_called_once()
```

---

## 🛠️ Common Troubleshooting

| Trouble | Penyebab | Solusi |
|---|---|---|
| Mypy error `Cannot find implementation module` | Subpackage belum terinstall | Jalankan `uv sync` ulang |
| QR Code tidak muncul | Terminal tidak mendukung ANSI color | Jalankan di terminal iTerm2 / VSCode terminal standar |
| `DatabaseLockedError` | SQLite dibuka oleh proses lain | Pastikan tidak ada instance platform lain berjalan |

---

## References

- [DOC-017: Project Structure](./15_project_structure.md)
- [DOC-018: Coding Standards](./16_coding_standards.md)
