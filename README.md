# Mailu - Servidor de E-mail Completo

Servidor de e-mail self-hosted com suporte a multi-dominio, webmail, anti-spam, envio via AWS SES e backup automatizado para AWS S3.

## Arquivos do projeto

| Arquivo | Descricao |
|---|---|
| `docker-compose.yml` | Stack completa (Postfix, Dovecot, Rspamd, Roundcube, etc.) |
| `mailu.env` | Configuracao principal do Mailu |
| `setup.sh` | Script de setup inicial (gera SECRET_KEY) |
| `backup.sh` | Backup local + upload para S3 |
| `restore.sh` | Restauracao a partir de arquivo local ou S3 |
| `install-cron.sh` | Instala backup automatico via cron |
| `backup.env` | Variaveis de ambiente do backup (criado pelo install-cron.sh) |

## Quick start

```bash
chmod +x setup.sh backup.sh restore.sh install-cron.sh
./setup.sh
nano mailu.env                # configurar dominio e credenciais SES
docker compose up -d
docker compose exec admin flask mailu admin admin seudominio.com SENHA
```

## Documentacao

| Doc | Conteudo |
|---|---|
| [Setup](docs/01-setup.md) | Instalacao, primeiro acesso, multi-dominio |
| [DNS](docs/02-dns.md) | Registros A, MX, SPF, DKIM, DMARC, rDNS |
| [AWS SES](docs/03-aws-ses.md) | Configurar envio de e-mail via SES (relay SMTP) |
| [AWS S3](docs/04-aws-s3.md) | Configurar bucket S3 para backup (IAM, policy, CLI) |
| [Backup](docs/05-backup.md) | Backup manual, automatico (cron) e restauracao |
| [Custos](docs/06-custos.md) | Estimativa de custos AWS (SES + S3) |
| [Troubleshooting](docs/07-troubleshooting.md) | Problemas comuns e solucoes |
