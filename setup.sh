#!/bin/bash
# Mailu setup helper script
# Run: chmod +x setup.sh && ./setup.sh

set -e

echo "=== Mailu Setup ==="
echo ""

# Generate SECRET_KEY
SECRET=$(openssl rand -hex 16)
echo "Generated SECRET_KEY: $SECRET"
sed -i "s/ChangeMeToA16ByteRandomString/$SECRET/" mailu.env
echo "SECRET_KEY updated in mailu.env"

echo ""
echo "=== Next steps ==="
echo ""
echo "1. Edit mailu.env and set your domain:"
echo "   DOMAIN=yourdomain.com"
echo "   HOSTNAMES=mail.yourdomain.com"
echo ""
echo "2. Configure DNS records for your domain:"
echo "   A     mail.yourdomain.com  -> your_server_ip"
echo "   MX    yourdomain.com       -> mail.yourdomain.com (priority 10)"
echo "   TXT   yourdomain.com       -> v=spf1 mx a:mail.yourdomain.com -all"
echo "   TXT   _dmarc.yourdomain.com -> v=DMARC1; p=reject; rua=mailto:admin@yourdomain.com"
echo ""
echo "3. Start the stack:"
echo "   docker compose up -d"
echo ""
echo "4. Create the first admin account:"
echo "   docker compose exec admin flask mailu admin admin yourdomain.com PASSWORD"
echo ""
echo "5. Access the admin at: https://mail.yourdomain.com/admin"
echo "   Access webmail at:   https://mail.yourdomain.com/webmail"
echo ""
echo "6. To add more domains: Admin UI -> Domains -> Add domain"
echo ""
echo "=== Multi-domain notes ==="
echo "   - Add each domain via the admin UI"
echo "   - Configure MX/SPF/DKIM/DMARC DNS records for each domain"
echo "   - DKIM keys are generated per domain in the admin UI"
echo ""
