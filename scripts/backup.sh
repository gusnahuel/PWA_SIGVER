#!/usr/bin/env bash
# ==========================================
# SIGVER - Copia de seguridad
# Guarda la base de datos (pg_dump) y las fotos (media) en backups/,
# con la fecha en el nombre, y borra las copias de más de DIAS_A_GUARDAR días.
#
# Uso:            scripts/backup.sh
# Automático:     ver "Copia de seguridad" en el README (cron)
# Otra carpeta:   BACKUP_DIR=/media/disco/sigver scripts/backup.sh
# ==========================================
set -euo pipefail

cd "$(dirname "$0")/.."
DESTINO="${BACKUP_DIR:-$PWD/backups}"
DIAS_A_GUARDAR="${DIAS_A_GUARDAR:-14}"
FECHA="$(date +%Y-%m-%d_%H%M)"
mkdir -p "$DESTINO"

echo "[$(date '+%F %T')] Copia de seguridad en $DESTINO"

# 1. Base de datos: formato comprimido de PostgreSQL (se restaura con pg_restore)
BASE="$DESTINO/sigver_db_$FECHA.dump"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BASE.tmp"
# Si el archivo está roto, pg_restore --list falla: así nunca queda una copia inservible
docker compose exec -T db pg_restore --list < "$BASE.tmp" > /dev/null
mv "$BASE.tmp" "$BASE"
echo "  base de datos: $(du -h "$BASE" | cut -f1)"

# 2. Fotos de verificaciones, reclamos y equipos
FOTOS="$DESTINO/sigver_media_$FECHA.tar.gz"
docker compose exec -T web tar czf - -C /app media > "$FOTOS.tmp"
mv "$FOTOS.tmp" "$FOTOS"
echo "  fotos:         $(du -h "$FOTOS" | cut -f1)"

# 3. Borrar las copias viejas
BORRADAS=$(find "$DESTINO" -name 'sigver_*' -mtime +"$DIAS_A_GUARDAR" -print -delete | wc -l)
echo "  copias de más de $DIAS_A_GUARDAR días borradas: $BORRADAS"
echo "[$(date '+%F %T')] Listo"
