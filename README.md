# Mailu - Servidor de E-mail Completo

Servidor de e-mail self-hosted com suporte a multi-dominio, webmail, anti-spam, envio via AWS SES e backup automatizado para AWS S3.

## Arquivos do projeto

| Arquivo | Descricao |
|---|---|
| `docker-compose.yml` | Stack completa (Postfix, Dovecot, Rspamd, Roundcube, etc.) |
| `.env.example` | Exemplo de variaveis de ambiente para o deploy |
| `worker/` | Worker Python de backup automatico e restore interativo |

## Quick start

```bash
# 1. Copiar e preencher variaveis de ambiente
cp .env.example .env
nano .env

# 2. Subir a stack
docker compose up -d

# 3. Criar usuario admin
docker compose exec admin flask mailu admin admin seudominio.com SENHA
```

## Backup e Restore

```bash
# Backup roda automaticamente (container backup, default 2h)
# Ver logs do backup:
docker compose logs -f backup

# Restore interativo via SSH:
docker compose exec backup python restore_interactive.py
```

## Documentacao

| Doc | Conteudo |
|---|---|
| [Setup](docs/01-setup.md) | Instalacao, primeiro acesso, multi-dominio |
| [DNS](docs/02-dns.md) | Registros A, MX, SPF, DKIM, DMARC, rDNS |
| [AWS SES](docs/03-aws-ses.md) | Configurar envio de e-mail via SES (relay SMTP) |
| [AWS S3](docs/04-aws-s3.md) | Configurar bucket S3 para backup (IAM, policy, CLI) |
| [Backup](docs/05-backup.md) | Backup automatico e restauracao |
| [Custos](docs/06-custos.md) | Estimativa de custos AWS (SES + S3) |
| [Troubleshooting](docs/07-troubleshooting.md) | Problemas comuns e solucoes |
| [Easypanel](docs/08-easypanel.md) | Deploy completo no Easypanel passo a passo |
