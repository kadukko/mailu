"""
Mailu Backup Worker

Runs as a container inside the Mailu stack.
Backs up Docker volumes and uploads to S3 on a configurable schedule.

Environment variables:
    BACKUP_SCHEDULE     - Cron-like time to run (default: "02:00")
    BACKUP_DIR          - Local backup directory (default: /backups)
    BACKUP_RETENTION    - Days to keep local backups (default: 30)
    COMPOSE_PROJECT     - Docker compose project name (default: auto-detect)
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

import gzip
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
COMPOSE_PROJECT = os.getenv("COMPOSE_PROJECT", "")

S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "mailu-backups")
S3_STORAGE_CLASS = os.getenv("S3_STORAGE_CLASS", "STANDARD_IA")
S3_RETENTION_DAYS = int(os.getenv("S3_RETENTION_DAYS", "90"))
S3_REGION = os.getenv("S3_REGION", "sa-east-1")

RUN_ON_STARTUP = os.getenv("RUN_ON_STARTUP", "false").lower() in ("true", "1", "yes")

VOLUMES = [
    "mail",
    "data",
    "dkim",
    "certs",
    "webmail",
    "filter",
    "redis",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    log.debug("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def detect_compose_project() -> str:
    if COMPOSE_PROJECT:
        return COMPOSE_PROJECT
    result = run(
        ["docker", "ps", "--format", "{{.Labels}}", "--filter", "label=com.docker.compose.project"],
        check=False,
    )
    for line in result.stdout.splitlines():
        for label in line.split(","):
            if "com.docker.compose.project=" in label:
                return label.split("=", 1)[1]
    return "mailu"


def volume_exists(volume_name: str) -> bool:
    result = run(["docker", "volume", "inspect", volume_name], check=False)
    return result.returncode == 0


def sizeof_fmt(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


# ---------------------------------------------------------------------------
# Backup volume
# ---------------------------------------------------------------------------


def backup_volume(volume_name: str, dest_dir: Path) -> Path | None:
    if not volume_exists(volume_name):
        log.warning("Volume %s not found, skipping", volume_name)
        return None

    archive = dest_dir / f"{volume_name}.tar.gz"
    log.info("Backing up volume: %s", volume_name)

    result = run([
        "docker", "run", "--rm",
        "-v", f"{volume_name}:/source:ro",
        "-v", f"{dest_dir}:/backup",
        "alpine",
        "tar", "czf", f"/backup/{volume_name}.tar.gz", "-C", "/source", ".",
    ], check=False)

    if result.returncode != 0:
        log.error("Failed to backup %s: %s", volume_name, result.stderr)
        return None

    size = sizeof_fmt(archive.stat().st_size)
    log.info("  -> %s (%s)", archive.name, size)
    return archive


# ---------------------------------------------------------------------------
# Database dump
# ---------------------------------------------------------------------------


def dump_admin_db(project: str, dest_dir: Path) -> Path | None:
    result = run(
        ["docker", "ps", "-q", "--filter", f"name={project}.*admin"],
        check=False,
    )
    container_id = result.stdout.strip().split("\n")[0]
    if not container_id:
        log.warning("Admin container not found, skipping DB dump")
        return None

    dump_file = dest_dir / "admin_db.sql"
    log.info("Dumping admin database...")

    result = run(
        ["docker", "exec", container_id, "sqlite3", "/data/main.db", ".dump"],
        check=False,
    )
    if result.returncode != 0:
        log.warning("Could not dump admin DB: %s", result.stderr)
        return None

    dump_file.write_text(result.stdout)
    size = sizeof_fmt(dump_file.stat().st_size)
    log.info("  -> admin_db.sql (%s)", size)
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

    # Verify
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


def run_backup() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = BACKUP_DIR / timestamp
    project = detect_compose_project()

    log.info("=" * 50)
    log.info("Backup started at %s", timestamp)
    log.info("Compose project: %s", project)
    log.info("=" * 50)

    try:
        work_dir.mkdir(parents=True, exist_ok=True)

        # 1. Backup volumes
        for vol in VOLUMES:
            full_vol = f"{project}_{vol}"
            backup_volume(full_vol, work_dir)

        # 2. Dump admin DB
        dump_admin_db(project, work_dir)

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
        # Remove temp work dir
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
