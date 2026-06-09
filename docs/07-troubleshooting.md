# Troubleshooting

## Backup falha com "aws: command not found"

```bash
# Verifique se o AWS CLI esta instalado
which aws
aws --version
```

## Backup falha com "Access Denied"

```bash
# Verifique as credenciais
aws sts get-caller-identity

# Verifique acesso ao bucket
aws s3 ls s3://seu-bucket/
```

## E-mails nao estao sendo enviados (SES)

```bash
# Verificar logs do SMTP
docker compose logs smtp | grep -i relay

# Verificar se o relay esta configurado
docker compose exec smtp postconf relayhost

# Testar conexao com o SES
docker compose exec smtp sh -c 'openssl s_client -connect email-smtp.us-east-1.amazonaws.com:587 -starttls smtp'
```

Causas comuns:
- Credenciais SMTP incorretas no `mailu.env`
- Conta SES ainda em sandbox (so envia para e-mails verificados)
- Regiao do endpoint SMTP diferente da regiao onde o dominio foi verificado

## Logs do Mailu

```bash
docker compose logs -f          # todos os servicos
docker compose logs -f smtp     # apenas SMTP
docker compose logs -f admin    # apenas admin
docker compose logs -f front    # proxy/TLS
docker compose logs -f imap     # Dovecot
docker compose logs -f antispam # Rspamd
```

## Verificar status dos containers

```bash
docker compose ps
```

## Testar envio de e-mail

```bash
docker compose exec smtp sh -c 'echo "teste" | mail -s "Teste" usuario@seudominio.com'
```

## Certificado TLS nao gerou (Let's Encrypt)

```bash
# Verificar logs do front (nginx)
docker compose logs front | grep -i cert

# Verificar se a porta 80 esta acessivel externamente
curl -I http://mail.seudominio.com
```

Causas comuns:
- Porta 80 bloqueada no firewall
- DNS ainda nao propagou (A record nao aponta para o servidor)
- Rate limit do Let's Encrypt (maximo 5 certificados por semana por dominio)
