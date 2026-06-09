#!/bin/bash
# Mailu Backup Script
# Usage: ./backup.sh [backup_directory]
#
# Backs up all critical Mailu data locally and uploads to S3.
# Requires: docker, aws cli (configured with credentials)
#
# Environment variables (or edit below):
#   S3_BUCKET        - S3 bucket name (required for S3 upload)
#   S3_PREFIX        - Path prefix inside bucket (default: mailu-backups)
#   S3_STORAGE_CLASS - S3 storage class (default: STANDARD_IA)
#   S3_RETENTION_DAYS - Days to keep backups in S3 (default: 90)
#   AWS_PROFILE      - AWS CLI profile to use (optional)

set -euo pipefail

# Configuration
COMPOSE_PROJECT=$(basename "$(pwd)")
BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"
RETENTION_DAYS=30

# S3 Configuration
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-mailu-backups}"
S3_STORAGE_CLASS="${S3_STORAGE_CLASS:-STANDARD_IA}"
S3_RETENTION_DAYS="${S3_RETENTION_DAYS:-90}"
AWS_PROFILE_FLAG=""
if [ -n "${AWS_PROFILE:-}" ]; then
    AWS_PROFILE_FLAG="--profile $AWS_PROFILE"
fi

# Volumes to back up (order: most critical first)
VOLUMES=(
    "mail"        # User mailboxes - largest, most important
    "data"        # Admin DB (users, domains, aliases)
    "dkim"        # DKIM keys - painful to regenerate
    "certs"       # TLS certificates
    "webmail"     # Roundcube user data
    "filter"      # Rspamd learned data
    "redis"       # Sessions (less critical)
)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    log "ERROR: $1" >&2
    exit 1
}

# Check prerequisites
command -v docker >/dev/null 2>&1 || error "docker not found"
if [ -n "$S3_BUCKET" ]; then
    command -v aws >/dev/null 2>&1 || error "aws cli not found (required for S3 upload)"
fi

# Create backup directory
mkdir -p "$BACKUP_PATH"
log "Backup started -> $BACKUP_PATH"

# 1. Backup config files
log "Backing up configuration files..."
cp mailu.env "$BACKUP_PATH/mailu.env"
cp docker-compose.yml "$BACKUP_PATH/docker-compose.yml"

# 2. Backup each Docker volume
for vol in "${VOLUMES[@]}"; do
    FULL_VOL="${COMPOSE_PROJECT}_${vol}"

    # Check if volume exists
    if ! docker volume inspect "$FULL_VOL" >/dev/null 2>&1; then
        log "SKIP: Volume $FULL_VOL not found"
        continue
    fi

    log "Backing up volume: $FULL_VOL ..."
    docker run --rm \
        -v "${FULL_VOL}:/source:ro" \
        -v "$(cd "$BACKUP_PATH" && pwd):/backup" \
        alpine \
        tar czf "/backup/${vol}.tar.gz" -C /source .

    SIZE=$(du -h "${BACKUP_PATH}/${vol}.tar.gz" | cut -f1)
    log "  -> ${vol}.tar.gz ($SIZE)"
done

# 3. Export admin database separately (SQLite)
log "Exporting admin database dump..."
ADMIN_CONTAINER=$(docker compose ps -q admin 2>/dev/null || true)
if [ -n "$ADMIN_CONTAINER" ]; then
    docker compose exec -T admin sqlite3 /data/main.db ".dump" > "$BACKUP_PATH/admin_db.sql" 2>/dev/null || \
        log "  WARN: Could not dump admin DB (container may be stopped)"
fi

# 4. Create final archive
log "Creating final archive..."
ARCHIVE="${BACKUP_DIR}/mailu_backup_${TIMESTAMP}.tar.gz"
tar czf "$ARCHIVE" -C "$BACKUP_DIR" "$TIMESTAMP"
rm -rf "$BACKUP_PATH"

TOTAL_SIZE=$(du -h "$ARCHIVE" | cut -f1)
log "Backup complete: $ARCHIVE ($TOTAL_SIZE)"

# 5. Upload to S3
if [ -n "$S3_BUCKET" ]; then
    S3_DEST="s3://${S3_BUCKET}/${S3_PREFIX}/mailu_backup_${TIMESTAMP}.tar.gz"
    log "Uploading to S3: $S3_DEST ..."
    log "  Storage class: $S3_STORAGE_CLASS"

    aws s3 cp "$ARCHIVE" "$S3_DEST" \
        --storage-class "$S3_STORAGE_CLASS" \
        $AWS_PROFILE_FLAG \
        --only-show-errors

    # Verify upload
    S3_SIZE=$(aws s3 ls "$S3_DEST" $AWS_PROFILE_FLAG | awk '{print $3}')
    LOCAL_SIZE=$(stat -c%s "$ARCHIVE" 2>/dev/null || stat -f%z "$ARCHIVE")

    if [ "$S3_SIZE" = "$LOCAL_SIZE" ]; then
        log "  -> S3 upload verified ($TOTAL_SIZE)"
    else
        error "S3 upload verification failed! Local: $LOCAL_SIZE, S3: $S3_SIZE"
    fi
else
    log "S3_BUCKET not set, skipping S3 upload"
fi

# 6. Cleanup old local backups
log "Cleaning up local backups older than ${RETENTION_DAYS} days..."
if [ "$RETENTION_DAYS" -gt 0 ]; then
    DELETED=$(find "$BACKUP_DIR" -name "mailu_backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
    if [ "$DELETED" -gt 0 ]; then
        log "  Removed $DELETED local backup(s)"
    else
        log "  No local backups to clean"
    fi
fi

# 7. Cleanup old S3 backups
if [ -n "$S3_BUCKET" ] && [ "$S3_RETENTION_DAYS" -gt 0 ]; then
    log "Cleaning up S3 backups older than ${S3_RETENTION_DAYS} days..."
    CUTOFF_DATE=$(date -d "-${S3_RETENTION_DAYS} days" +%Y%m%d 2>/dev/null || \
                  date -v-${S3_RETENTION_DAYS}d +%Y%m%d)
    S3_DELETED=0

    aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" $AWS_PROFILE_FLAG 2>/dev/null | \
    while read -r line; do
        FILENAME=$(echo "$line" | awk '{print $4}')
        [ -z "$FILENAME" ] && continue
        # Extract date from filename: mailu_backup_YYYYMMDD_HHMMSS.tar.gz
        FILE_DATE=$(echo "$FILENAME" | grep -oP '\d{8}' | head -1)
        if [ -n "$FILE_DATE" ] && [ "$FILE_DATE" -lt "$CUTOFF_DATE" ]; then
            log "  Deleting: $FILENAME"
            aws s3 rm "s3://${S3_BUCKET}/${S3_PREFIX}/${FILENAME}" $AWS_PROFILE_FLAG --only-show-errors
            S3_DELETED=$((S3_DELETED + 1))
        fi
    done

    log "  S3 cleanup done"
fi

log "Done!"
