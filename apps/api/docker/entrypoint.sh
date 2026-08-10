#!/bin/sh
set -e

cd /var/www/api

if [ ! -f vendor/autoload.php ]; then
  echo "Installing Composer dependencies…"
  composer install --no-interaction --prefer-dist --no-security-blocking \
    || composer install --no-interaction --prefer-dist
fi

echo "Waiting for Postgres…"
i=0
until php -r '
$host = getenv("POSTGRES_HOST") ?: "postgres";
$user = getenv("POSTGRES_USER") ?: "moozika";
$pass = getenv("POSTGRES_PASSWORD") ?: "moozika";
$db = getenv("POSTGRES_DB") ?: "moozika";
new PDO("pgsql:host=$host;dbname=$db", $user, $pass);
' 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "Postgres unavailable"
    exit 1
  fi
  sleep 1
done

php bin/console doctrine:database:create --if-not-exists --no-interaction 2>/dev/null || true
php bin/console doctrine:schema:update --force --no-interaction

echo "API ready on :8080"
exec "$@"
