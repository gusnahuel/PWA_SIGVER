#!/bin/sh
# ==========================================
# SIGVER - Entrypoint
# ==========================================
set -e

echo "Esperando a la base de datos..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" > /dev/null 2>&1; do
    sleep 1
done
echo "Base de datos disponible."

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

echo "Iniciando aplicación..."
exec "$@"