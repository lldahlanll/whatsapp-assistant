#!/usr/bin/env bash
# =============================================================================
# reset_finance.sh — Reset semua data finance ke kondisi awal (nol bersih)
#
# Usage:
#   ./scripts/reset_finance.sh              # reset data milik SEMUA user
#   ./scripts/reset_finance.sh --jid <JID>  # reset data milik user tertentu
#   ./scripts/reset_finance.sh --dry-run    # lihat preview tanpa hapus
#
# Contoh:
#   ./scripts/reset_finance.sh
#   ./scripts/reset_finance.sh --jid 628123456789@lid
#   ./scripts/reset_finance.sh --dry-run
# =============================================================================

set -euo pipefail

# ── Konfigurasi ───────────────────────────────────────────────────────────────
CONTAINER_NAME="${CONTAINER_NAME:-whatsapp-platform}"
DB_PATH="${DB_PATH:-/app/storage/session.db}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER_LOCAL="$SCRIPT_DIR/_reset_finance_helper.py"
HELPER_REMOTE="/app/_reset_finance_helper.py"

# ── Parse argumen ─────────────────────────────────────────────────────────────
TARGET_JID=""
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --jid)
            TARGET_JID="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        -h|--help)
            head -18 "$0" | tail -16
            exit 0
            ;;
        *)
            echo "❌ Argumen tidak dikenal: $1"
            echo "   Gunakan --help untuk bantuan."
            exit 1
            ;;
    esac
done

# ── Cek container berjalan ────────────────────────────────────────────────────
if ! docker inspect "$CONTAINER_NAME" &>/dev/null; then
    echo "❌ Container '$CONTAINER_NAME' tidak ditemukan."
    echo "   Jalankan: docker-compose up -d"
    exit 1
fi

if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME")" != "true" ]]; then
    echo "❌ Container '$CONTAINER_NAME' tidak sedang berjalan."
    exit 1
fi

# ── Info scope ────────────────────────────────────────────────────────────────
if [[ "$DRY_RUN" == "true" ]]; then
    echo "🔍 DRY RUN — tidak ada data yang dihapus"
fi

if [[ -n "$TARGET_JID" ]]; then
    SCOPE_MSG="untuk user: $TARGET_JID"
else
    SCOPE_MSG="untuk SEMUA user"
fi

echo ""
echo "⚠️  Reset data finance $SCOPE_MSG"
echo ""

# ── Konfirmasi (skip saat dry-run) ────────────────────────────────────────────
if [[ "$DRY_RUN" == "false" ]]; then
    read -rp "   Lanjutkan? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "   Dibatalkan."
        exit 0
    fi
    echo ""
fi

# ── Copy helper script ke container lalu jalankan ────────────────────────────
docker cp "$HELPER_LOCAL" "$CONTAINER_NAME:$HELPER_REMOTE"
docker exec "$CONTAINER_NAME" python3 "$HELPER_REMOTE" "$DB_PATH" "$TARGET_JID" "$DRY_RUN"
docker exec "$CONTAINER_NAME" rm -f "$HELPER_REMOTE"
