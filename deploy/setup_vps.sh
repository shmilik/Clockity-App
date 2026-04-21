#!/bin/bash
# ============================================================
# JobTracker VPS Setup Script — run as root on Ubuntu 24.04
# Usage: bash deploy/setup_vps.sh
# ============================================================
set -e

# ---------- EDIT THESE ----------
DOMAIN="clockity.us"              # e.g. clockity.com
DB_PASSWORD="YOUR_DB_PASSWORD"    # choose a strong password
SECRET_KEY="$(openssl rand -hex 32)"
# --------------------------------

APP_DIR="/var/www/jobtracker"
DB_NAME="jobtracker"
DB_USER="jobuser"

echo "=== 1. System packages ==="
apt update && apt upgrade -y
apt install -y python3-pip python3-venv nginx certbot python3-certbot-nginx git postgresql postgresql-contrib

echo "=== 2. Clone repo ==="
mkdir -p "$APP_DIR"
git clone https://github.com/shmilik/SlimeTime.git "$APP_DIR"
chown -R www-data:www-data "$APP_DIR"

echo "=== 3. Python venv ==="
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "=== 4. Postgres ==="
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME;" || true
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" || true
sudo -u postgres psql -c "ALTER DATABASE $DB_NAME OWNER TO $DB_USER;" || true

echo "=== 5. systemd service ==="
sed \
  -e "s|YOUR_DB_PASSWORD|$DB_PASSWORD|g" \
  -e "s|REPLACE_WITH_A_LONG_RANDOM_STRING|$SECRET_KEY|g" \
  "$APP_DIR/deploy/jobtracker.service" > /etc/systemd/system/jobtracker.service

systemctl daemon-reload
systemctl enable jobtracker
systemctl start jobtracker

echo "=== 6. Nginx ==="
sed "s|YOUR_DOMAIN|$DOMAIN|g" "$APP_DIR/deploy/jobtracker.nginx.conf" \
  > /etc/nginx/sites-available/jobtracker
ln -sf /etc/nginx/sites-available/jobtracker /etc/nginx/sites-enabled/jobtracker
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "=== 7. SSL ==="
certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN"

echo ""
echo "=============================="
echo " Done! Visit https://$DOMAIN"
echo "=============================="
echo " SECRET_KEY (save this): $SECRET_KEY"
