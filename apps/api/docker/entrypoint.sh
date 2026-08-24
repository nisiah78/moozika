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

# Le worker Messenger partage cette image et cet entrypoint : il a besoin de l'attente
# Postgres ci-dessus, mais PAS de gérer le schéma. Deux conteneurs lançant
# `schema:update --force` en parallèle se marchent dessus.
if [ "${SKIP_SCHEMA_UPDATE:-0}" = "1" ]; then
  echo "Schema management skipped (SKIP_SCHEMA_UPDATE=1)"
else
  php bin/console doctrine:database:create --if-not-exists --no-interaction 2>/dev/null || true
  php bin/console doctrine:schema:update --force --no-interaction
  # MESSENGER_TRANSPORT_DSN porte auto_setup=0 : la table messenger_messages n'est donc
  # jamais créée à la volée, on la crée ici explicitement (commande idempotente).
  php bin/console messenger:setup-transports --no-interaction
fi

exec "$@"
