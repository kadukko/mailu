# Configuracao AWS SES (envio de e-mail)

O Mailu usa o AWS SES como relay SMTP para enviar todos os e-mails. Isso melhora a entregabilidade e evita problemas com IP em blacklist.

## 1. Ativar o SES no console AWS

1. Acesse **AWS Console** -> **Amazon SES**
2. Escolha a regiao mais proxima (ex: `us-east-1` ou `sa-east-1`)
3. A conta comeca em **sandbox mode** (so envia para e-mails verificados)

## 2. Verificar dominio no SES

1. SES -> **Verified identities** -> **Create identity**
2. Selecione **Domain**
3. Digite: `seudominio.com`
4. Marque **Easy DKIM** -> **RSA_2048_BIT**
5. Clique em **Create identity**
6. O SES gera 3 registros CNAME para DKIM. Adicione no seu DNS:

| Tipo | Nome | Valor |
|---|---|---|
| CNAME | `xxxx._domainkey.seudominio.com` | `xxxx.dkim.amazonses.com` |
| CNAME | `yyyy._domainkey.seudominio.com` | `yyyy.dkim.amazonses.com` |
| CNAME | `zzzz._domainkey.seudominio.com` | `zzzz.dkim.amazonses.com` |

*(os valores exatos aparecem no console do SES)*

7. Aguarde a verificacao (geralmente leva de 5 minutos a 72 horas)
8. O status muda para **Verified**

## 3. Criar credenciais SMTP do SES

1. SES -> **SMTP settings** -> **Create SMTP credentials**
2. Nome do usuario IAM: `ses-smtp-mailu`
3. Clique em **Create user**
4. Guarde o **SMTP Username** e **SMTP Password** (so aparece uma vez)

> **Importante:** As credenciais SMTP do SES sao diferentes das Access Keys normais do IAM. Use as geradas nesta tela.

## 4. Configurar no Mailu

Edite o `mailu.env`:

```bash
# AWS SES SMTP relay
RELAYHOST=[email-smtp.us-east-1.amazonaws.com]:587
RELAY_USER=AKIA_SEU_SMTP_USERNAME
RELAY_PASSWORD=SEU_SMTP_PASSWORD
```

Regioes disponiveis:

| Regiao | Endpoint SMTP |
|---|---|
| US East (N. Virginia) | `email-smtp.us-east-1.amazonaws.com` |
| South America (Sao Paulo) | `email-smtp.sa-east-1.amazonaws.com` |
| Europe (Ireland) | `email-smtp.eu-west-1.amazonaws.com` |
| Europe (Frankfurt) | `email-smtp.eu-central-1.amazonaws.com` |

Apos editar, reinicie o Mailu:

```bash
docker compose down && docker compose up -d
```

## 5. Sair do Sandbox (producao)

No sandbox, o SES so envia para e-mails verificados manualmente. Para enviar para qualquer destinatario:

1. SES -> **Account dashboard** -> **Request production access**
2. Preencha:
   - **Mail type**: Transactional
   - **Website URL**: seu dominio
   - **Use case description**: Explique que e um servidor de e-mail corporativo/pessoal
3. A AWS analisa em ate 24 horas

## 6. Configurar notificacoes de bounce/complaint (recomendado)

1. SES -> **Verified identities** -> seu dominio -> **Notifications**
2. Crie um topico SNS para **Bounces** e **Complaints**
3. Inscreva seu e-mail admin para receber alertas

Isso evita que sua conta SES seja suspensa por taxa alta de bounces.

## 7. Testar envio via SES

```bash
# Verificar se o relay esta funcionando
docker compose logs smtp | grep -i relay

# Enviar e-mail de teste
docker compose exec admin flask mailu test-email admin@seudominio.com destinatario@gmail.com
```

## 8. Estimativa de custo SES

| Item | Preco |
|---|---|
| Primeiros 62.000 e-mails/mes (de EC2) | Gratis |
| Apos 62.000 | $0.10 a cada 1.000 e-mails |
| Anexos | $0.12 por GB |

Para uso pessoal/pequena empresa, o custo e praticamente **zero**.
