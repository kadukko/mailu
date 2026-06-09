#!/bin/bash
# Instala o cronjob de backup automatico do Mailu
# Usage: ./install-cron.sh
#
# O backup roda diariamente as 2h da manha.
# Configure via variaveis de ambiente:
#   S3_BUCKET        - Nome do bucket (deixe vazio para backup apenas local)
#   S3_PREFIX        - Prefixo no bucket (default: mailu-backups)
#   S3_STORAGE_CLASS - Classe de armazenamento (default: STANDARD_IA)
#   S3_RETENTION_DAYS - Retencao no S3 em dias (default: 90)
#   BACKUP_DIR       - Diretorio local dos backups (default: ./backups)
#   AWS_PROFILE      - Perfil AWS CLI (opcional)

set -euo pipefail

MAILU_DIR="$(cd "$(dirname "$0")" && pwd)"
CRON_SCHEDULE="0 2 * * *"
ENV_FILE="${MAILU_DIR}/backup.env"
LOG_FILE="/var/log/mailu-backup.log"
CRON_ID="# mailu-backup-job"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Criar arquivo de variaveis de ambiente se nao existir
if [ ! -f "$ENV_FILE" ]; then
    log "Criando ${ENV_FILE} ..."
    cat > "$ENV_FILE" <<'EOF'
# Backup - Variaveis de ambiente
# Edite este arquivo para configurar o backup.
# Depois rode: ./install-cron.sh

# S3 (deixe S3_BUCKET vazio para backup apenas local)
S3_BUCKET=
S3_PREFIX=mailu-backups
S3_STORAGE_CLASS=STANDARD_IA
S3_RETENTION_DAYS=90

# Local
BACKUP_DIR=./backups

# AWS (opcional)
AWS_PROFILE=
EOF
    log "Edite ${ENV_FILE} com suas configuracoes e rode este script novamente."
    exit 0
fi

# Carregar variaveis
source "$ENV_FILE"

# Montar a linha de environment para o cron
CRON_ENV=""
[ -n "${S3_BUCKET:-}" ]         && CRON_ENV="${CRON_ENV}S3_BUCKET=${S3_BUCKET} "
[ -n "${S3_PREFIX:-}" ]         && CRON_ENV="${CRON_ENV}S3_PREFIX=${S3_PREFIX} "
[ -n "${S3_STORAGE_CLASS:-}" ]  && CRON_ENV="${CRON_ENV}S3_STORAGE_CLASS=${S3_STORAGE_CLASS} "
[ -n "${S3_RETENTION_DAYS:-}" ] && CRON_ENV="${CRON_ENV}S3_RETENTION_DAYS=${S3_RETENTION_DAYS} "
[ -n "${AWS_PROFILE:-}" ]       && CRON_ENV="${CRON_ENV}AWS_PROFILE=${AWS_PROFILE} "

# Montar comando do cron
CRON_CMD="${CRON_SCHEDULE} cd ${MAILU_DIR} && ${CRON_ENV}${MAILU_DIR}/backup.sh ${BACKUP_DIR:-./backups} >> ${LOG_FILE} 2>&1 ${CRON_ID}"

# Remover job anterior se existir
EXISTING_CRON=$(crontab -l 2>/dev/null | grep -v "$CRON_ID" || true)

# Adicionar novo job
echo "${EXISTING_CRON}
${CRON_CMD}" | crontab -

log "Cronjob instalado com sucesso!"
log ""
log "Configuracao:"
log "  Horario:    Diariamente as 2h"
log "  Diretorio:  ${MAILU_DIR}"
log "  Log:        ${LOG_FILE}"
if [ -n "${S3_BUCKET:-}" ]; then
    log "  Destino:    s3://${S3_BUCKET}/${S3_PREFIX}/"
    log "  Storage:    ${S3_STORAGE_CLASS}"
    log "  Retencao:   ${S3_RETENTION_DAYS} dias (S3) / 30 dias (local)"
else
    log "  Destino:    Apenas local (${BACKUP_DIR:-./backups})"
    log "  Retencao:   30 dias"
    log "  S3:         Desativado (configure S3_BUCKET em backup.env para ativar)"
fi
log ""
log "Para verificar:  crontab -l"
log "Para remover:    crontab -l | grep -v 'mailu-backup-job' | crontab -"
log "Para editar:     nano ${ENV_FILE} && ./install-cron.sh"
