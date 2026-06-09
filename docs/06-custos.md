# Estimativa de Custos AWS

## SES (envio de e-mail)

| Item | Preco |
|---|---|
| Primeiros 62.000 e-mails/mes (de EC2) | Gratis |
| Apos 62.000 | $0.10 a cada 1.000 e-mails |
| Anexos | $0.12 por GB |

Para uso pessoal/pequena empresa, o custo e praticamente **zero**.

## S3 (backup)

Para um servidor com ~50 contas de e-mail:

| Item | Custo estimado |
|---|---|
| Armazenamento Standard-IA (30 backups x ~10GB) | ~$1.25/mes |
| Requests (PUT/GET) | ~$0.15/mes |
| Transfer OUT (somente no restore) | $0.09/GB |
| **Total mensal** | **~$1.50/mes** |

Com lifecycle policy (Glacier), o custo cai para ~$0.30/mes apos o primeiro mes.

## Total combinado

| Servico | Custo mensal |
|---|---|
| SES | ~$0.00 (uso normal) |
| S3 (Standard-IA) | ~$1.50 |
| S3 (com Glacier) | ~$0.30 |
| **Total** | **~$0.30 - $1.50/mes** |
