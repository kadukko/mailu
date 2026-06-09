# Setup Inicial do Mailu

## Pre-requisitos

- Docker e Docker Compose instalados
- Servidor com IP publico e portas 25, 80, 443, 465, 587, 993 abertas
- Dominio com acesso ao painel DNS

## Instalacao

```bash
# Gerar SECRET_KEY e ver instrucoes
chmod +x setup.sh backup.sh restore.sh install-cron.sh
./setup.sh

# Editar o dominio no mailu.env
nano mailu.env
# Alterar: DOMAIN, HOSTNAMES, WEBSITE

# Subir a stack
docker compose up -d

# Criar usuario admin
docker compose exec admin flask mailu admin admin seudominio.com SENHA_SEGURA
```

Acesse:
- Admin: `https://mail.seudominio.com/admin`
- Webmail: `https://mail.seudominio.com/webmail`

## Adicionar dominios extras

1. Admin UI -> Mail domains -> Add domain
2. Configure os registros DNS para cada dominio (ver [DNS](02-dns.md))
3. Gere as chaves DKIM pelo admin
