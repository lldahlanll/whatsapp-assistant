#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Update WhatsApp Assistant di VPS dengan aman.
#
# Alur:
#   1. git pull (fast-forward saja)
#   2. Tandai image yang sedang jalan sebagai :previous (untuk rollback cepat)
#   3. Build image baru & restart container
#   4. Saat startup, app otomatis backup DB lalu menjalankan `alembic upgrade head`
#   5. Tunggu sampai migrasi sukses; jika gagal, tampilkan log + cara rollback
#
# Usage:
#   ./scripts/deploy.sh             # deploy versi terbaru dari branch aktif
#   ./scripts/deploy.sh --rollback  # kembali ke image sebelumnya
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE="whatsapp-platform"
SERVICE="app"
CONTAINER="whatsapp-platform"
TIMEOUT="${DEPLOY_TIMEOUT:-120}"

log() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[deploy]\033[0m %s\n' "$*" >&2; exit 1; }

if [[ "${1:-}" == "--rollback" ]]; then
    docker image inspect "$IMAGE:previous" >/dev/null 2>&1 || fail "Image $IMAGE:previous tidak ditemukan."
    log "Rollback ke image sebelumnya..."
    docker tag "$IMAGE:previous" "$IMAGE:latest"
    docker compose up -d --no-build "$SERVICE"
    log "Rollback selesai. Jika skema DB sudah terlanjur berubah, restore backup dari storage/backups/ (lihat DEPLOY.md)."
    exit 0
fi

[[ -f .env.docker ]] || fail ".env.docker belum ada. Salin dari .env.example lalu isi credentials."
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail "Ada perubahan lokal di VPS. Commit/stash dulu agar git pull aman."

PREV_COMMIT="$(git rev-parse --short HEAD)"
log "Commit saat ini: $PREV_COMMIT — menarik update..."
git pull --ff-only
NEW_COMMIT="$(git rev-parse --short HEAD)"
log "Commit baru: $NEW_COMMIT"

if docker image inspect "$IMAGE:latest" >/dev/null 2>&1; then
    docker tag "$IMAGE:latest" "$IMAGE:previous"
    log "Image lama disimpan sebagai $IMAGE:previous"
fi

log "Build image..."
docker compose build "$SERVICE"

log "Restart container (migrasi DB berjalan otomatis saat startup)..."
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
docker compose up -d "$SERVICE"

log "Menunggu migrasi selesai (maks ${TIMEOUT}s)..."
for ((i = 0; i < TIMEOUT; i += 3)); do
    LOGS="$(docker logs --since "$STARTED_AT" "$CONTAINER" 2>&1 || true)"
    if grep -q "Alembic migrations completed" <<<"$LOGS"; then
        grep -q "Database backed up before migration" <<<"$LOGS" && log "Backup DB dibuat sebelum migrasi (storage/backups/)."
        log "✅ Deploy $PREV_COMMIT → $NEW_COMMIT berhasil."
        exit 0
    fi
    if grep -qE "Alembic migration failed|Database backup before migration failed" <<<"$LOGS"; then
        break
    fi
    sleep 3
done

docker logs --since "$STARTED_AT" --tail 50 "$CONTAINER" 2>&1 || true
fail "Deploy gagal atau migrasi belum selesai. Kembali ke versi sebelumnya: ./scripts/deploy.sh --rollback"
