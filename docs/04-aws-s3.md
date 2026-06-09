# Configuracao AWS S3 para Backup

## 1. Criar um usuario IAM

1. Acesse o **AWS Console** -> **IAM** -> **Users** -> **Create user**
2. Nome: `mailu-backup`
3. **Nao** marque acesso ao console (so precisa de acesso programatico)
4. Clique em **Next**

## 2. Criar a policy de permissoes

1. Em **Permissions**, clique em **Attach policies directly** -> **Create policy**
2. Selecione a aba **JSON** e cole:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "MailuBackupAccess",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::SEU-BUCKET-AQUI",
                "arn:aws:s3:::SEU-BUCKET-AQUI/*"
            ]
        }
    ]
}
```

3. Substitua `SEU-BUCKET-AQUI` pelo nome do seu bucket
4. Nome da policy: `MailuBackupS3Policy`
5. Salve e vincule ao usuario `mailu-backup`

## 3. Gerar Access Keys

1. IAM -> Users -> `mailu-backup` -> **Security credentials**
2. **Create access key** -> **Command Line Interface (CLI)**
3. Guarde o **Access Key ID** e **Secret Access Key** (so aparece uma vez)

## 4. Criar o bucket S3

```bash
aws s3 mb s3://mailu-backup-seudominio --region sa-east-1
```

Ou pelo console:

1. **S3** -> **Create bucket**
2. Nome: `mailu-backup-seudominio` (deve ser unico globalmente)
3. Regiao: `sa-east-1` (Sao Paulo) ou a mais proxima do servidor
4. **Block all public access**: manter ativado
5. **Bucket Versioning**: opcional (protege contra sobrescrita acidental)
6. Criar

## 5. Instalar e configurar o AWS CLI no servidor

```bash
# Instalar o AWS CLI
# Ubuntu/Debian
apt update && apt install -y awscli

# Ou instalacao oficial (qualquer Linux)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Configurar credenciais
aws configure
```

Preencha quando solicitado:

```
AWS Access Key ID:     AKIA________________
AWS Secret Access Key: ____________________
Default region name:   sa-east-1
Default output format: json
```

## 6. Testar a conexao

```bash
# Verificar se consegue acessar o bucket
aws s3 ls s3://mailu-backup-seudominio

# Teste de upload
echo "teste" > /tmp/teste.txt
aws s3 cp /tmp/teste.txt s3://mailu-backup-seudominio/teste.txt
aws s3 rm s3://mailu-backup-seudominio/teste.txt
rm /tmp/teste.txt
```

## 7. Configurar as variaveis de ambiente

Edite o `backup.env` (criado pelo `install-cron.sh`):

```bash
S3_BUCKET=mailu-backup-seudominio
S3_PREFIX=mailu-backups
S3_STORAGE_CLASS=STANDARD_IA
S3_RETENTION_DAYS=90
```

## 8. (Opcional) Lifecycle Policy - mover para Glacier

Para economizar, mova backups antigos para Glacier automaticamente.

1. S3 -> Seu bucket -> **Management** -> **Create lifecycle rule**
2. Nome: `mover-para-glacier`
3. Prefix: `mailu-backups/`
4. Regras:
   - **Transition to Glacier Instant Retrieval**: apos 30 dias
   - **Transition to Glacier Deep Archive**: apos 90 dias
   - **Expire/Delete**: apos 365 dias
5. Salvar

Com isso:
- 0-30 dias: **Standard-IA** (~$0.0125/GB)
- 30-90 dias: **Glacier Instant** (~$0.004/GB)
- 90-365 dias: **Glacier Deep Archive** (~$0.00099/GB)
- Apos 365 dias: deletado automaticamente
