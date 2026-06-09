#!/bin/bash
# Mailu Restore Script
# Usage: ./restore.sh <backup_archive_or_s3_uri>
#
# Examples:
#   ./restore.sh ./backups/mailu_backup_20260609_020000.tar.gz
#   ./restore.sh s3://my-bucket/mailu-backups/mailu_backup_20260609_020000.tar.gz
#   ./restore.sh --list                     # List available S3 backups
#   ./restore.sh --latest                   # Restore the most recent S3 backup
#
# Environment variables:
#   S3_BUCKET   - S3 bucket (required for --list/--latest)
#   S3_PREFIX   - Path prefix (default: mailu-backups)
#   AWS_PROFILE - AWS CLI profile (optional)

set -euo pipefail

ARCHIVE="${1:-}"
COMPOSE_PROJECT=$(basename "$(pwd)")
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-mailu-backups}"
AWS_PROFILE_FLAG=""
if [ -n "${AWS_PROFILE:-}" ]; then
    AWS_PROFILE_FLAG="--profile $AWS_PROFILE"
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    log "ERROR: $1" >&2
    exit 1
}

[ -z "$ARCHIVE" ] && error "Usage: $0 <backup_archive.tar.gz | s3://... | --list | --latest>"

# List available S3 backups
if [ "$ARCHIVE" = "--list" ]; then
    [ -z "$S3_BUCKET" ] && error "S3_BUCKET not set"
    log "Available backups in s3://${S3_BUCKET}/${S3_PREFIX}/:"
    aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" $AWS_PROFILE_FLAG | \
        grep "mailu_backup_" | \
        awk '{printf "  %s %s  %s\n", $1, $2, $4}'
    exit 0
fi

# Download from S3 if needed
if [ "$ARCHIVE" = "--latest" ] || [[ "$ARCHIVE" == s3://* ]]; then
    command -v aws >/dev/null 2>&1 || error "aws cli not found"

    if [ "$ARCHIVE" = "--latest" ]; then
        [ -z "$S3_BUCKET" ] && error "S3_BUCKET not set"
        ARCHIVE=$(aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" $AWS_PROFILE_FLAG | \
            grep "mailu_backup_" | sort | tail -1 | awk '{print $4}')
        [ -z "$ARCHIVE" ] && error "No backups found in S3"
        ARCHIVE="s3://${S3_BUCKET}/${S3_PREFIX}/${ARCHIVE}"
        log "Latest backup: $ARCHIVE"
    fi

    LOCAL_FILE="/tmp/$(basename "$ARCHIVE")"
    log "Downloading from S3..."
    aws s3 cp "$ARCHIVE" "$LOCAL_FILE" $AWS_PROFILE_FLAG --only-show-errors
    ARCHIVE="$LOCAL_FILE"
    log "Downloaded to $LOCAL_FILE"
fi

[ -f "$ARCHIVE" ] || error "Archive not found: $ARCHIVE"

VOLUMES=(mail data dkim certs webmail filter redis)

# Extract archive to temp dir
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

log "Extracting archive..."
tar xzf "$ARCHIVE" -C "$TEMP_DIR"
BACKUP_DIR=$(ls "$TEMP_DIR")

log "=== WARNING ==="
log "This will STOP Mailu and OVERWRITE all current data."
log "Volumes to restore: ${VOLUMES[*]}"
read -rp "Continue? (yes/no): " CONFIRM
[ "$CONFIRM" = "yes" ] || error "Aborted by user"

# Stop Mailu
log "Stopping Mailu..."
docker compose down

# Restore config files
if [ -f "$TEMP_DIR/$BACKUP_DIR/mailu.env" ]; then
    log "Restoring mailu.env..."
    cp "$TEMP_DIR/$BACKUP_DIR/mailu.env" ./mailu.env
fi

if [ -f "$TEMP_DIR/$BACKUP_DIR/docker-compose.yml" ]; then
    log "Restoring docker-compose.yml..."
    cp "$TEMP_DIR/$BACKUP_DIR/docker-compose.yml" ./docker-compose.yml
fi

# Restore each volume
for vol in "${VOLUMES[@]}"; do
    FULL_VOL="${COMPOSE_PROJECT}_${vol}"
    TARFILE="$TEMP_DIR/$BACKUP_DIR/${vol}.tar.gz"

    if [ ! -f "$TARFILE" ]; then
        log "SKIP: ${vol}.tar.gz not found in backup"
        continue
    fi

    log "Restoring volume: $FULL_VOL ..."

    # Create volume if it doesn't exist
    docker volume create "$FULL_VOL" >/dev/null 2>&1 || true

    # Clear and restore
    docker run --rm \
        -v "${FULL_VOL}:/target" \
        -v "$(cd "$TEMP_DIR/$BACKUP_DIR" && pwd):/backup:ro" \
        alpine \
        sh -c "rm -rf /target/* /target/..?* /target/.[!.]* 2>/dev/null; tar xzf /backup/${vol}.tar.gz -C /target"

    log "  -> $vol restored"
done

# Start Mailu
log "Starting Mailu..."
docker compose up -d

log ""
log "Restore complete! Mailu is starting up."
log "Check status: docker compose ps"
log "Check logs:   docker compose logs -f"
