#!/usr/bin/env bash
# Publica una versión nueva de la PWA.
#
# nginx sirve /static/ como "immutable" cuando la URL lleva ?v=, y el service
# worker guarda la app en su caché: si la URL no cambia, los celulares siguen
# con el código viejo. Este script cambia el número en todos los lugares a la vez.
#
# Uso:  scripts/version.sh            -> sube a la versión siguiente
#       scripts/version.sh 120        -> fija la versión 120
set -euo pipefail
cd "$(dirname "$0")/.."

SW=frontend/sw.js
actual=$(grep -oE "sigver-v[0-9]+" "$SW" | head -1 | grep -oE "[0-9]+")
nueva=${1:-$((actual + 1))}
if ! [[ "$nueva" =~ ^[0-9]+$ ]] || (( nueva <= actual )); then
    echo "La versión nueva ($nueva) tiene que ser un número mayor que la actual ($actual)." >&2
    exit 1
fi

# Solo los recursos propios versionados (css/js de /static/css y /static/js);
# los íconos y las librerías de vendor/ tienen su propio esquema.
sed -i -E "s#(/static/(css|js)/[a-z0-9_-]+\.(css|js))\?v=[0-9]+#\1?v=${nueva}#g" frontend/index.html "$SW"
# Imports entre módulos: todos con el mismo ?v= (si dos imports del mismo
# archivo difieren, el navegador lo carga dos veces y se duplica su estado)
sed -i -E "s#((from|import) '\./[a-z0-9_-]+\.js)\?v=[0-9]+'#\1?v=${nueva}'#g" frontend/static/js/*.js
sed -i -E "s#'sigver-v[0-9]+'#'sigver-v${nueva}'#" "$SW"

echo "Versión $actual -> $nueva"
grep -cE "\?v=${nueva}|sigver-v${nueva}" frontend/index.html "$SW" frontend/static/js/*.js | sed 's/^/  /'
# Control: ningún archivo puede quedar con otra versión
if grep -rnE "\.(js|css)\?v=[0-9]+" frontend/index.html "$SW" frontend/static/js/*.js | grep -v "v=${nueva}"; then
    echo "¡Quedaron referencias con otra versión!" >&2; exit 1
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^sigver_web$'; then
    docker exec sigver_web python manage.py collectstatic --noinput | tail -1
else
    echo "Recordá correr: python manage.py collectstatic --noinput"
fi
