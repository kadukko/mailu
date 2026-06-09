# Backup e Restauracao

## Backup manual

```bash
# Backup local + S3
S3_BUCKET=mailu-backup-seudominio ./backup.sh

# Backup apenas local (sem S3)
./backup.sh
```

## Backup automatico (cron)

Use o script `install-cron.sh`:

```bash
# Primeira execucao: cria o backup.env para configurar
./install-cron.sh

# Edite as variaveis (S3 ou apenas local)
nano backup.env

# Segunda execucao: instala o cronjob (diario as 2h)
./install-cron.sh
```

Para configurar manualmente:

```bash
crontab -e
```

Adicione:

```
# Backup diario as 2h da manha
0 2 * * * cd /caminho/para/mailu && S3_BUCKET=mailu-backup-seudominio ./backup.sh >> /var/log/mailu-backup.log 2>&1
```

## O que o backup inclui

| Volume | Conteudo | Criticidade |
|---|---|---|
| `mail` | Caixas de e-mail de todos os usuarios | Alta |
| `data` | Banco admin (usuarios, dominios, aliases) | Alta |
| `dkim` | Chaves DKIM de cada dominio | Alta |
| `certs` | Certificados TLS / Let's Encrypt | Media |
| `webmail` | Contatos e configs do Roundcube | Media |
| `filter` | Dados aprendidos pelo Rspamd | Baixa |
| `redis` | Sessoes e rate-limiting | Baixa |

## Restauracao

```bash
# Listar backups disponiveis no S3
S3_BUCKET=mailu-backup-seudominio ./restore.sh --list

# Restaurar o backup mais recente do S3
S3_BUCKET=mailu-backup-seudominio ./restore.sh --latest

# Restaurar um backup especifico do S3
./restore.sh s3://mailu-backup-seudominio/mailu-backups/mailu_backup_20260609_020000.tar.gz

# Restaurar de arquivo local
./restore.sh ./backups/mailu_backup_20260609_020000.tar.gz
```

O script de restore:
1. Baixa o arquivo do S3 (se necessario)
2. Para o Mailu
3. Restaura todos os volumes e configuracoes
4. Inicia o Mailu novamente
