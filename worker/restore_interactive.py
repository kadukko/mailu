"""
Mailu Interactive Restore

Execute via SSH:
    docker compose exec backup python restore_interactive.py

Lists local and S3 backups, lets you pick one, and restores it.

Environment variables (same as backup_worker.py):
    S3_BUCKET, S3_PREFIX, S3_REGION
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
    DB_HOST, DB_NAME, DB_USER, DB_PW
"""

import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/backups"))
SOURCES_DIR = Path("/sources")

S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "mailu-backups")
S3_REGION = os.getenv("S3_REGION", "sa-east-1")

DB_HOST = os.getenv("DB_HOST", "database")
DB_NAME = os.getenv("DB_NAME", "mailu")
DB_USER = os.getenv("DB_USER", "mailu")
DB_PW = os.getenv("DB_PW", "")

VOLUME_NAMES = ["mail", "data", "dkim", "certs", "webmail", "filter", "redis"]
TIMESTAMP_RE = re.compile(r"(\d{8})_(\d{6})")

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------


class C:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    NC = "\033[0m"


def info(msg: str) -> None:
    print(f"{C.GREEN}[INFO]{C.NC}  {msg}")


def warn(msg: str) -> None:
    print(f"{C.YELLOW}[WARN]{C.NC}  {msg}")


def error(msg: str) -> None:
    print(f"{C.RED}[ERRO]{C.NC}  {msg}")


def header(msg: str) -> None:
    print(f"\n{C.CYAN}--- {msg} ---{C.NC}\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, **kwargs)


def sizeof_fmt(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def parse_date(filename: str) -> str:
    m = TIMESTAMP_RE.search(filename)
    if not m:
        return "???"
    d, t = m.group(1), m.group(2)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}:{t[4:6]}"


def find_compose_project() -> str:
    result = run(
        ["docker", "ps", "--format", "{{.Labels}}", "--filter", "label=com.docker.compose.project"],
        check=False,
    )
    for line in result.stdout.splitlines():
        for label in line.split(","):
            if "com.docker.compose.project=" in label:
                return label.split("=", 1)[1]
    return "mailu"


# ---------------------------------------------------------------------------
# Backup entry
# ---------------------------------------------------------------------------


@dataclass
class Backup:
    name: str
    source: str  # "local" or "s3"
    size: str
    date: str


# ---------------------------------------------------------------------------
# List backups
# ---------------------------------------------------------------------------


def list_local_backups() -> list[Backup]:
    backups = []

    if not BACKUP_DIR.exists():
        warn(f"Diretorio {BACKUP_DIR} nao encontrado")
        return backups

    files = sorted(BACKUP_DIR.glob("mailu_backup_*.tar.gz"), reverse=True)

    for f in files:
        backups.append(Backup(
            name=f.name,
            source="local",
            size=sizeof_fmt(f.stat().st_size),
            date=parse_date(f.name),
        ))

    return backups


def list_s3_backups(exclude: set[str]) -> list[Backup]:
    backups = []

    if not S3_BUCKET:
        return backups

    try:
        import boto3
    except ImportError:
        warn("boto3 nao instalado, ignorando S3")
        return backups

    try:
        s3 = boto3.client("s3", region_name=S3_REGION)
        paginator = s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=f"{S3_PREFIX}/"):
            for obj in page.get("Contents", []):
                name = obj["Key"].split("/")[-1]
                if not name.startswith("mailu_backup_"):
                    continue
                if name in exclude:
                    continue

                backups.append(Backup(
                    name=name,
                    source="s3",
                    size=sizeof_fmt(obj["Size"]),
                    date=parse_date(name),
                ))

    except Exception as e:
        warn(f"Erro ao listar S3: {e}")

    backups.sort(key=lambda b: b.name, reverse=True)
    return backups


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def show_list(backups: list[Backup]) -> None:
    header("Backups Disponiveis")

    print(f"  {C.BOLD}{'#':<4} {'Origem':<8} {'Data':<22} {'Tamanho':<10} {'Arquivo'}{C.NC}")
    print(f"  {'----'} {'--------'} {'----------------------'} {'----------'} {'----------------------------------------'}")

    for i, b in enumerate(backups, 1):
        if b.source == "local":
            source = f"{C.GREEN}local{C.NC} "
        else:
            source = f"{C.YELLOW}  s3  {C.NC}"

        print(f"  {C.BOLD}{i:<4}{C.NC} {source}  {b.date:<22} {b.size:<10} {b.name}")

    print(f"\n  Total: {len(backups)} backup(s)")


# ---------------------------------------------------------------------------
# Select
# ---------------------------------------------------------------------------


def select_backup(backups: list[Backup]) -> Backup:
    total = len(backups)
    print(f"\n{C.BOLD}Opcoes:{C.NC}")
    print(f"  [1-{total}]  Selecionar backup pelo numero")
    print(f"  [q]       Sair\n")

    while True:
        try:
            choice = input("Selecione o backup para restaurar: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nOperacao cancelada.")
            sys.exit(0)

        if choice.lower() == "q":
            print("Operacao cancelada.")
            sys.exit(0)

        try:
            idx = int(choice)
            if 1 <= idx <= total:
                return backups[idx - 1]
        except ValueError:
            pass

        error(f"Opcao invalida. Digite um numero entre 1 e {total}, ou 'q' para sair.")


# ---------------------------------------------------------------------------
# Prepare backup
# ---------------------------------------------------------------------------


def prepare_backup(backup: Backup, temp_dir: str) -> str:
    header("Backup Selecionado")
    print(f"  Arquivo: {backup.name}")
    print(f"  Origem:  {backup.source}")
    print(f"  Data:    {backup.date}")
    print(f"  Tamanho: {backup.size}")

    archive = os.path.join(temp_dir, backup.name)

    if backup.source == "local":
        info("Copiando backup local...")
        src = BACKUP_DIR / backup.name
        shutil.copy2(str(src), archive)

    elif backup.source == "s3":
        info("Baixando backup do S3...")
        import boto3
        s3 = boto3.client("s3", region_name=S3_REGION)
        s3.download_file(S3_BUCKET, f"{S3_PREFIX}/{backup.name}", archive)

    if not os.path.exists(archive):
        error("Falha ao preparar o backup")
        sys.exit(1)

    info(f"Backup pronto: {archive}")
    return archive


# ---------------------------------------------------------------------------
# Show contents
# ---------------------------------------------------------------------------


def show_contents(archive: str) -> None:
    header("Conteudo do Backup")

    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getnames()

    for entry in members[:30]:
        print(f"  {entry}")

    if len(members) > 30:
        print(f"  ... e mais {len(members) - 30} arquivo(s)")


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


def confirm(msg: str) -> bool:
    print(f"\n{C.RED}{C.BOLD}ATENCAO:{C.NC} {msg}\n")
    try:
        answer = input("Digite 'sim' para confirmar: ").strip()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer == "sim"


def stop_mailu_services(project: str) -> list[str]:
    """Stop all Mailu containers except the backup container. Returns container IDs."""
    result = run(
        ["docker", "ps", "--format", "{{.ID}} {{.Names}}", "--filter", f"label=com.docker.compose.project={project}"],
        check=False,
    )
    containers = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        cid, name = line.split(None, 1)
        if "backup" not in name:
            containers.append(cid)

    if containers:
        info(f"Parando {len(containers)} container(s)...")
        run(["docker", "stop"] + containers, check=False)
    else:
        warn("Nenhum container Mailu encontrado para parar")

    return containers


def restore_volumes(backup_path: str) -> tuple[int, int]:
    """Restore volumes by copying directly to mounted paths."""
    restored = 0
    skipped = 0

    for vol in VOLUME_NAMES:
        tarfile_path = os.path.join(backup_path, f"{vol}.tar.gz")
        target = SOURCES_DIR / vol

        if not os.path.exists(tarfile_path):
            warn(f"SKIP: {vol}.tar.gz nao encontrado no backup")
            skipped += 1
            continue

        if not target.exists():
            warn(f"SKIP: {vol} nao montado em {target}")
            skipped += 1
            continue

        info(f"Restaurando: {vol}")

        # Clear target and extract
        for item in target.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        with tarfile.open(tarfile_path, "r:gz") as tar:
            tar.extractall(str(target))

        info(f"  -> {vol} restaurado")
        restored += 1

    return restored, skipped


def restore_database(backup_path: str) -> None:
    """Restore PostgreSQL database from SQL dump."""
    dump_file = os.path.join(backup_path, "database.sql")

    # Fallback to old name from previous backup format
    if not os.path.exists(dump_file):
        dump_file = os.path.join(backup_path, "admin_db.sql")

    if not os.path.exists(dump_file):
        warn("Dump do banco nao encontrado no backup, pulando restore do DB")
        return

    info(f"Restaurando PostgreSQL ({DB_HOST}/{DB_NAME})...")

    env = {**os.environ, "PGPASSWORD": DB_PW}

    # Drop and recreate database
    run(
        ["psql", "-h", DB_HOST, "-U", DB_USER, "-d", "postgres",
         "-c", f"DROP DATABASE IF EXISTS {DB_NAME};"],
        check=False, env=env,
    )
    run(
        ["psql", "-h", DB_HOST, "-U", DB_USER, "-d", "postgres",
         "-c", f"CREATE DATABASE {DB_NAME} OWNER {DB_USER};"],
        check=False, env=env,
    )

    # Restore dump
    with open(dump_file, "r") as f:
        result = subprocess.run(
            ["psql", "-h", DB_HOST, "-U", DB_USER, "-d", DB_NAME],
            stdin=f, capture_output=True, text=True, check=False, env=env,
        )

    if result.returncode != 0:
        error(f"Erro no restore do banco: {result.stderr[:500]}")
    else:
        info("  -> Banco restaurado")


def restore(archive: str, temp_dir: str) -> None:
    if not confirm("Isso vai PARAR o Mailu e SOBRESCREVER todos os dados atuais."):
        print("Operacao cancelada.")
        sys.exit(0)

    project = find_compose_project()
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    info("Extraindo backup...")
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(extract_dir)

    backup_subdir = os.listdir(extract_dir)[0]
    backup_path = os.path.join(extract_dir, backup_subdir)

    # 1. Stop services
    header("Parando Mailu")
    containers = stop_mailu_services(project)

    # 2. Restore volumes
    header("Restaurando Volumes")
    restored, skipped = restore_volumes(backup_path)

    # 3. Restore database
    header("Restaurando Banco de Dados")
    restore_database(backup_path)

    # 4. Start services
    header("Iniciando Mailu")
    if containers:
        info(f"Iniciando {len(containers)} container(s)...")
        run(["docker", "start"] + containers, check=False)

    header("Resultado")
    print(f"  Volumes restaurados: {C.GREEN}{restored}{C.NC}")
    if skipped:
        print(f"  Volumes ignorados:   {C.YELLOW}{skipped}{C.NC}")
    print()
    info("Restore concluido! Mailu esta iniciando.")
    print()
    print("  Verificar status:  docker compose ps")
    print("  Verificar logs:    docker compose logs -f")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"\n{C.BOLD}============================================{C.NC}")
    print(f"{C.BOLD}  Mailu - Restore Interativo{C.NC}")
    print(f"{C.BOLD}============================================{C.NC}")

    local = list_local_backups()
    local_names = {b.name for b in local}
    remote = list_s3_backups(exclude=local_names)
    all_backups = local + remote

    if not all_backups:
        error("Nenhum backup encontrado (local ou S3)")
        sys.exit(1)

    show_list(all_backups)
    selected = select_backup(all_backups)

    temp_dir = tempfile.mkdtemp()
    try:
        archive = prepare_backup(selected, temp_dir)
        show_contents(archive)
        restore(archive, temp_dir)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
