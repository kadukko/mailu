# Configuracao DNS

Para **cada dominio** configurado no Mailu, crie estes registros:

| Tipo | Nome | Valor |
|---|---|---|
| A | `mail.seudominio.com` | `IP_DO_SERVIDOR` |
| MX | `seudominio.com` | `mail.seudominio.com` (prioridade 10) |
| TXT | `seudominio.com` | `v=spf1 include:amazonses.com mx a:mail.seudominio.com -all` |
| TXT | `_dmarc.seudominio.com` | `v=DMARC1; p=reject; rua=mailto:admin@seudominio.com` |
| TXT | `dkim._domainkey.seudominio.com` | *(copiar do Admin UI apos gerar a chave DKIM)* |

> O registro SPF inclui `amazonses.com` porque o envio de e-mails e feito via AWS SES. Ver [AWS SES](03-aws-ses.md).

## rDNS (Reverse DNS)

Configure o registro PTR no seu provedor de hospedagem para que o IP do servidor aponte para `mail.seudominio.com`. Sem isso, muitos servidores rejeitam seus e-mails.

## DNS para dominios adicionais

Repita todos os registros acima para cada dominio extra adicionado pelo Admin UI. Cada dominio precisa de seus proprios registros MX, SPF, DKIM e DMARC.
