# Deploy no Easypanel - Passo a Passo

## Visao geral

O Easypanel gerencia o deploy via Docker Compose. O Mailu roda como um servico "Docker Compose" dentro de um projeto. O Easypanel usa Traefik como proxy reverso, mas o Mailu tem seu proprio nginx, entao as portas de e-mail (SMTP, IMAP, POP3) sao expostas diretamente no host.

## 1. Criar o projeto no Easypanel

1. Acesse o painel do Easypanel (`https://seu-servidor:3000`)
2. Clique em **Create Project**
3. Nome do projeto: `mail-server` (ou o nome que preferir)

## 2. Criar o servico Docker Compose

1. Dentro do projeto, clique em **+ Create Service**
2. Selecione **Docker Compose**
3. Nome do servico: `mailu`

## 3. Colar o docker-compose.yml

1. Na aba **Source** do servico, selecione **Docker Compose**
2. Cole o conteudo do arquivo `docker-compose.yml` deste repositorio
3. Salve

## 4. Configurar variaveis de ambiente

Na aba **Environment** do servico, adicione as variaveis abaixo.

### Variaveis obrigatorias

| Variavel | Valor | Descricao |
|---|---|---|
| `SECRET_KEY` | *(gerar com `openssl rand -hex 16`)* | Chave secreta do Mailu (16 bytes hex) |
| `DOMAIN` | `seudominio.com` | Dominio principal de e-mail |
| `HOSTNAMES` | `mail.seudominio.com` | Hostname do servidor (FQDN) |
| `WEBSITE` | `https://mail.seudominio.com` | URL do site |
| `RELAYHOST` | `[email-smtp.us-east-1.amazonaws.com]:587` | Endpoint SMTP do AWS SES |
| `RELAY_USER` | `AKIA...` | SMTP Username do SES |
| `RELAY_PASSWORD` | `...` | SMTP Password do SES |

### Variaveis opcionais (com defaults)

| Variavel | Default | Descricao |
|---|---|---|
| `SUBNET` | `192.168.203.0/24` | Subnet da rede Docker interna |
| `POSTMASTER` | `admin` | Parte local do postmaster (postmaster@DOMAIN) |
| `TLS_FLAVOR` | `mail` | Tipo de TLS (ver secao TLS abaixo) |
| `WEB_ADMIN` | `/admin` | Path do painel admin |
| `WEB_WEBMAIL` | `/webmail` | Path do webmail |
| `WEBMAIL` | `roundcube` | Cliente webmail (roundcube, snappymail, none) |
| `SITENAME` | `Mailu` | Nome exibido no admin |
| `ADMIN` | `true` | Habilitar painel admin |
| `LOG_LEVEL` | `WARNING` | Nivel de log (DEBUG, INFO, WARNING, ERROR) |
| `MESSAGE_SIZE_LIMIT` | `50000000` | Tamanho maximo de e-mail em bytes (50MB) |
| `MESSAGE_RATELIMIT` | `200/day` | Limite de envio por usuario/dia |
| `ANTIVIRUS` | `none` | Antivirus (clamav ou none, clamav usa +2GB RAM) |
| `DB_FLAVOR` | `sqlite` | Banco de dados (sqlite, mysql, postgresql) |
| `FETCHMAIL_DELAY` | `600` | Intervalo do fetchmail em segundos |
| `AUTH_RATELIMIT_IP` | `60/hour` | Rate limit de auth por IP |
| `AUTH_RATELIMIT_USER` | `100/day` | Rate limit de auth por usuario |
| `RECIPIENT_DELIMITER` | `+` | Delimitador de sub-endereco (user+tag@domain) |
| `DISABLE_STATISTICS` | `True` | Desativar envio de estatisticas anonimas |
| `DKIM_SELECTOR` | `dkim` | Seletor DKIM |
| `RELAYNETS` | *(vazio)* | CIDRs com permissao de relay |

### Exemplo completo no Easypanel

```
SECRET_KEY=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6
DOMAIN=seudominio.com
HOSTNAMES=mail.seudominio.com
WEBSITE=https://mail.seudominio.com
TLS_FLAVOR=mail
RELAYHOST=[email-smtp.sa-east-1.amazonaws.com]:587
RELAY_USER=AKIAXXXXXXXXXXXXXXXXX
RELAY_PASSWORD=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
LOG_LEVEL=INFO
```

> **Gerar SECRET_KEY:** Execute no terminal do servidor:
> ```bash
> openssl rand -hex 16
> ```

## 5. Configuracao de TLS

O Easypanel usa Traefik que ja gerencia certificados SSL para o dominio web. Porem, o Mailu precisa de TLS proprio para as portas de e-mail (SMTP, IMAP, POP3).

### Opcao A: TLS gerenciado pelo Mailu (recomendado)

```
TLS_FLAVOR=letsencrypt
```

O Mailu gera seus proprios certificados Let's Encrypt. Para isso:
- A porta **80** precisa estar acessivel (o Mailu usa para o desafio ACME)
- Se o Traefik do Easypanel ja usa a porta 80, mude o front do Mailu para outra porta e use `TLS_FLAVOR=mail` (auto-assinado)

### Opcao B: TLS auto-assinado (mais simples)

```
TLS_FLAVOR=mail
```

O Mailu gera certificados auto-assinados. Funciona para SMTP relay via SES (o envio e autenticado no SES, nao depende do certificado local). Clientes de e-mail podem mostrar aviso de certificado na primeira conexao.

### Opcao C: Desativar TLS no front (Traefik cuida do HTTPS)

```
TLS_FLAVOR=notls
```

Use apenas se o Traefik do Easypanel faz proxy para as portas web (80/443) e voce nao precisa de TLS nas portas de e-mail. **Nao recomendado** - clientes IMAP/SMTP precisam de TLS.

> **Recomendacao para Easypanel:** Use `TLS_FLAVOR=mail` para evitar conflito com o Traefik na porta 80. Os clientes de e-mail aceitam o certificado auto-assinado apos a primeira conexao.

## 6. Configuracao de portas

O Easypanel normalmente gerencia portas via Traefik, mas o Mailu precisa de portas de e-mail expostas diretamente no host. Verifique que as seguintes portas **nao estao em uso** por outro servico:

| Porta | Protocolo | Servico |
|---|---|---|
| 25 | TCP | SMTP (recebimento de e-mail) |
| 465 | TCP | SMTPS (SMTP over TLS) |
| 587 | TCP | Submission (envio autenticado) |
| 110 | TCP | POP3 |
| 995 | TCP | POP3S (POP3 over TLS) |
| 143 | TCP | IMAP |
| 993 | TCP | IMAPS (IMAP over TLS) |
| 80 | TCP | HTTP (apenas se TLS_FLAVOR=letsencrypt) |
| 443 | TCP | HTTPS (admin + webmail) |

### Conflito de portas com Traefik

O Traefik do Easypanel ja usa as portas 80 e 443. Opcoes:

**Opcao 1 - Remover portas 80/443 do Mailu (recomendado)**

Remova as linhas de porta 80 e 443 do `docker-compose.yml` do servico `front` e configure o Traefik para rotear o trafego web. As portas de e-mail continuam expostas diretamente.

**Opcao 2 - Usar portas alternativas**

No docker-compose.yml, mude:
```yaml
ports:
  - "8080:80"
  - "8443:443"
```

E acesse o admin em `https://seu-servidor:8443/admin`.

**Opcao 3 - Parar o Traefik nas portas 80/443**

So faca isso se o Easypanel nao esta servindo outros sites neste servidor.

## 7. Deploy

1. Apos configurar o compose e as variaveis, clique em **Deploy** no Easypanel
2. Aguarde todos os containers subirem (pode levar 1-2 minutos no primeiro deploy)
3. Verifique o status na aba **Overview** - todos devem estar "Running"

## 8. Criar usuario admin

Acesse o terminal do servico no Easypanel:

1. Aba **Terminal** do servico, ou via SSH no servidor:

```bash
# Via SSH no servidor
cd /etc/easypanel/projects/SEU-PROJETO/mailu/code
docker compose exec admin flask mailu admin admin seudominio.com SENHA_SEGURA
```

Substitua:
- `SEU-PROJETO` pelo nome do projeto no Easypanel
- `seudominio.com` pelo seu dominio
- `SENHA_SEGURA` pela senha desejada

## 9. Acessar as interfaces

| Interface | URL |
|---|---|
| Admin | `https://mail.seudominio.com/admin` |
| Webmail | `https://mail.seudominio.com/webmail` |

## 10. Configurar DNS

Siga o guia em [02-dns.md](02-dns.md) para configurar os registros DNS.

## 11. Configurar AWS SES

Siga o guia em [03-aws-ses.md](03-aws-ses.md) para configurar o envio via SES.

## 12. Verificacao pos-deploy

### Checar se todos os containers estao rodando

```bash
cd /etc/easypanel/projects/SEU-PROJETO/mailu/code
docker compose ps
```

Todos devem estar com status `Up`.

### Checar logs

```bash
# Todos os servicos
docker compose logs -f

# Apenas SMTP (verificar relay SES)
docker compose logs -f smtp

# Apenas front (verificar TLS)
docker compose logs -f front
```

### Testar portas

De outra maquina, teste se as portas estao acessiveis:

```bash
# SMTP
telnet mail.seudominio.com 25

# IMAP
telnet mail.seudominio.com 993

# Submission
telnet mail.seudominio.com 587
```

### Testar envio

```bash
docker compose exec admin flask mailu test-email admin@seudominio.com destinatario@gmail.com
```

## Troubleshooting no Easypanel

### Containers reiniciando em loop

```bash
docker compose logs --tail=50 NOME_DO_CONTAINER
```

Causas comuns:
- `SECRET_KEY` nao definida ou vazia
- `DOMAIN` ou `HOSTNAMES` nao definidos
- Conflito de subnet (outro projeto usando 192.168.203.0/24)

Para conflito de subnet, mude `SUBNET` para outro range (ex: `192.168.204.0/24`) e atualize o IP do resolver no compose para `192.168.204.254`.

### Porta ja em uso

```bash
# Verificar o que esta usando a porta
ss -tlnp | grep :25
ss -tlnp | grep :443
```

### E-mails nao chegam

1. Verifique os registros MX: `dig MX seudominio.com`
2. Verifique se a porta 25 esta aberta no firewall do servidor/provedor
3. Verifique logs: `docker compose logs smtp`

### Admin nao acessivel

1. Verifique se `ADMIN=true` esta nas variaveis
2. Verifique se o container admin esta rodando: `docker compose ps admin`
3. Verifique logs: `docker compose logs admin`
