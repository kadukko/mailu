"""
Mailu Backup Worker

Runs as a container inside the Mailu stack.
Backs up mounted volumes and PostgreSQL database, uploads to S3.

Environment variables:
    BACKUP_SCHEDULE     - Time to run daily backup (default: "02:00")
    BACKUP_DIR          - Local backup directory (default: /backups)
    BACKUP_RETENTION    - Days to keep local backups (default: 30)
    DB_HOST             - PostgreSQL host (default: database)
    DB_NAME             - PostgreSQL database name (default: mailu)
    DB_USER             - PostgreSQL user (default: mailu)
    S3_BUCKET           - S3 bucket name (empty = skip S3)
    S3_PREFIX           - S3 key prefix (default: mailu-backups)
    S3_STORAGE_CLASS    - S3 storage class (default: STANDARD_IA)
    S3_RETENTION_DAYS   - Days to keep S3 backups (default: 90)
    S3_REGION           - AWS region (default: sa-east-1)
    AWS_ACCESS_KEY_ID   - AWS credentials
    AWS_SECRET_ACCESS_KEY - AWS credentials
    LOG_LEVEL           - Logging level (default: INFO)
    RUN_ON_STARTUP      - Run backup immediately on start (default: false)
"""

import logging
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import schedule

log = logging.getLogger("backup-worker")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/backups"))
BACKUP_SCHEDULE = os.getenv("BACKUP_SCHEDULE", "02:00")
BACKUP_RETENTION = int(os.getenv("BACKUP_RETENTION", "30"))

SOURCES_DIR = Path("/sources")

DB_HOST = os.getenv("DB_HOST", "database")
DB_NAME = os.getenv("DB_NAME", "mailu")
DB_USER = os.getenv("DB_USER", "mailu")

S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "mailu-backups")
S3_STORAGE_CLASS = os.getenv("S3_STORAGE_CLASS", "STANDARD_IA")
S3_RETENTION_DAYS = int(os.getenv("S3_RETENTION_DAYS", "90"))
S3_REGION = os.getenv("S3_REGION", "sa-east-1")

RUN_ON_STARTUP = os.getenv("RUN_ON_STARTUP", "false").lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sizeof_fmt(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


# ---------------------------------------------------------------------------
# Backup volume (direct from mounted path)
# ---------------------------------------------------------------------------


def backup_volume(name: str, dest_dir: Path) -> Path | None:
    source = SOURCES_DIR / name
    if not source.exists():
        log.warning("Source %s not found, skipping", source)
        return None

    archive = dest_dir / f"{name}.tar.gz"
    log.info("Backing up: %s", name)

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(str(source), arcname=".")

    size = sizeof_fmt(archive.stat().st_size)
    log.info("  -> %s (%s)", archive.name, size)
    return archive


# ---------------------------------------------------------------------------
# Database dump (pg_dump via network)
# ---------------------------------------------------------------------------


def dump_database(dest_dir: Path) -> Path | None:
    dump_file = dest_dir / "database.sql"
    log.info("Dumping PostgreSQL (%s@%s/%s)...", DB_USER, DB_HOST, DB_NAME)

    result = subprocess.run(
        ["pg_dump", "-h", DB_HOST, "-U", DB_USER, "-d", DB_NAME],
        capture_output=True, text=True, check=False,
        env={**os.environ, "PGPASSWORD": os.getenv("DB_PW", "")},
    )

    if result.returncode != 0:
        log.error("pg_dump failed: %s", result.stderr)
        return None

    dump_file.write_text(result.stdout)
    size = sizeof_fmt(dump_file.stat().st_size)
    log.info("  -> database.sql (%s)", size)
    return dump_file


# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------


def get_s3_client():
    import boto3

    return boto3.client("s3", region_name=S3_REGION)


def upload_to_s3(archive_path: Path) -> bool:
    if not S3_BUCKET:
        log.info("S3_BUCKET not set, skipping upload")
        return False

    s3 = get_s3_client()
    s3_key = f"{S3_PREFIX}/{archive_path.name}"

    log.info("Uploading to s3://%s/%s ...", S3_BUCKET, s3_key)
    log.info("  Storage class: %s", S3_STORAGE_CLASS)

    file_size = archive_path.stat().st_size

    s3.upload_file(
        str(archive_path),
        S3_BUCKET,
        s3_key,
        ExtraArgs={"StorageClass": S3_STORAGE_CLASS},
    )

    response = s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
    remote_size = response["ContentLength"]

    if remote_size == file_size:
        log.info("  -> Upload verified (%s)", sizeof_fmt(file_size))
        return True
    else:
        log.error(
            "Upload verification failed! Local: %d, S3: %d",
            file_size,
            remote_size,
        )
        return False


def cleanup_s3() -> None:
    if not S3_BUCKET or S3_RETENTION_DAYS <= 0:
        return

    s3 = get_s3_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=S3_RETENTION_DAYS)

    log.info("Cleaning S3 backups older than %d days...", S3_RETENTION_DAYS)

    paginator = s3.get_paginator("list_objects_v2")
    deleted = 0

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=f"{S3_PREFIX}/"):
        for obj in page.get("Contents", []):
            if obj["LastModified"] < cutoff:
                log.info("  Deleting: %s", obj["Key"])
                s3.delete_object(Bucket=S3_BUCKET, Key=obj["Key"])
                deleted += 1

    if deleted:
        log.info("  Removed %d old S3 backup(s)", deleted)
    else:
        log.info("  No old S3 backups to clean")


# ---------------------------------------------------------------------------
# Local cleanup
# ---------------------------------------------------------------------------


def cleanup_local() -> None:
    if BACKUP_RETENTION <= 0:
        return

    cutoff = time.time() - (BACKUP_RETENTION * 86400)
    deleted = 0

    log.info("Cleaning local backups older than %d days...", BACKUP_RETENTION)

    for f in BACKUP_DIR.glob("mailu_backup_*.tar.gz"):
        if f.stat().st_mtime < cutoff:
            log.info("  Deleting: %s", f.name)
            f.unlink()
            deleted += 1

    if deleted:
        log.info("  Removed %d old local backup(s)", deleted)
    else:
        log.info("  No old local backups to clean")


# ---------------------------------------------------------------------------
# Main backup
# ---------------------------------------------------------------------------


VOLUME_NAMES = ["mail", "data", "dkim", "certs", "webmail", "filter", "redis"]


def run_backup() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = BACKUP_DIR / timestamp

    log.info("=" * 50)
    log.info("Backup started at %s", timestamp)
    log.info("=" * 50)

    try:
        work_dir.mkdir(parents=True, exist_ok=True)

        # 1. Backup mounted volumes
        for name in VOLUME_NAMES:
            backup_volume(name, work_dir)

        # 2. Dump PostgreSQL
        dump_database(work_dir)

        # 3. Create final archive
        archive_name = f"mailu_backup_{timestamp}.tar.gz"
        archive_path = BACKUP_DIR / archive_name

        log.info("Creating archive: %s", archive_name)
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(str(work_dir), arcname=timestamp)

        total_size = sizeof_fmt(archive_path.stat().st_size)
        log.info("Archive created: %s (%s)", archive_name, total_size)

        # 4. Upload to S3
        upload_to_s3(archive_path)

        # 5. Cleanup local
        cleanup_local()

        # 6. Cleanup S3
        cleanup_s3()

        log.info("Backup completed successfully!")

    except Exception:
        log.exception("Backup failed!")

    finally:
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def main() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Mailu Backup Worker started")
    log.info("Schedule: daily at %s", BACKUP_SCHEDULE)
    log.info("Local retention: %d days", BACKUP_RETENTION)
    log.info("S3 bucket: %s", S3_BUCKET or "(disabled)")
    if S3_BUCKET:
        log.info("S3 prefix: %s", S3_PREFIX)
        log.info("S3 retention: %d days", S3_RETENTION_DAYS)
        log.info("S3 storage class: %s", S3_STORAGE_CLASS)
        log.info("S3 region: %s", S3_REGION)

    if RUN_ON_STARTUP:
        log.info("RUN_ON_STARTUP=true, running backup now...")
        run_backup()

    schedule.every().day.at(BACKUP_SCHEDULE).do(run_backup)

    log.info("Waiting for next scheduled run...")
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
