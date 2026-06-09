#!/usr/bin/env python3
"""Force an immediate backup outside the regular schedule."""

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

from backup_worker import run_backup, BACKUP_DIR

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
run_backup()
