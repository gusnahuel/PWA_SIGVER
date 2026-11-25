#!/usr/bin/env bash
# Publica SIGVER por internet con ngrok para que los supervisores prueben
# desde su celular (wifi o datos móviles), con HTTPS válido y sin instalar nada.
#
# Una sola vez:
#   1. Crear una cuenta gratis en https://dashboard.ngrok.com
#   2. Copiar el authtoken (Getting Started > Your Authtoken) y correr:
#        ngrok config add-authtoken <TOKEN>
#   3. Copiar el dominio fijo gratis (Universal Gateway > Domains), por ejemplo
#      algo-al-azar.ngrok-free.app, y agregarlo al .env:
#        NGROK_DOMAIN=algo-al-azar.ngrok-free.app
#
# Cada vez que se quiera probar:
#   scripts/ngrok.sh            (Ctrl+C para cortar)
#
# Mientras corre, Django usa la configuración de producción (sin DEBUG) y
# no se publican los puertos 8000 ni 5432. Al cortar con Ctrl+C vuelve solo
# al modo desarrollo. Esta PC tiene que quedar prendida y con internet.
#
# El dominio es siempre el mismo: la app instalada en los celulares y las
# verificaciones que esperan en su cola siguen funcionando entre una sesión
# de pruebas y la siguiente.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v ngrok >/dev/null || { echo "Falta ngrok: sudo snap install ngrok"; exit 1; }

NGROK_DOMAIN="${NGROK_DOMAIN:-$(grep -E '^NGROK_DOMAIN=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ' || true)}"
if [[ ! "$NGROK_DOMAIN" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)*\.ngrok(-free)?\.(app|dev)$ ]]; then
    echo "Falta el dominio de ngrok (o no es válido): '${NGROK_DOMAIN}'."
    echo "Agregá al .env una línea como:  NGROK_DOMAIN=algo-al-azar.ngrok-free.app"
    exit 1
fi
export NGROK_DOMAIN

COMPOSE_PRUEBAS=(docker compose -f docker-compose.yml -f docker-compose.ngrok.yml)

volver_a_desarrollo() {
    echo
    echo "Volviendo al modo desarrollo..."
    docker compose up -d db web >/dev/null
    echo "Listo: SIGVER ya no está publicado en internet."
}

echo "Pasando SIGVER a modo pruebas (producción, sin DEBUG)..."
"${COMPOSE_PRUEBAS[@]}" up -d db web nginx >/dev/null
trap volver_a_desarrollo EXIT

echo -n "Esperando a Django"
for _ in $(seq 60); do
    codigo=$(curl -sk -o /dev/null -w '%{http_code}' -H "Host: $NGROK_DOMAIN" https://localhost/admin/login/ || true)
    [[ "$codigo" == 200 ]] && break
    echo -n .; sleep 2
done
echo
if [[ "$codigo" != 200 ]]; then
    echo "Django no respondió (último código: $codigo). Revisá: docker compose logs web"
    exit 1
fi

echo "Revisión de seguridad de Django:"
"${COMPOSE_PRUEBAS[@]}" exec -T web python manage.py check --deploy --fail-level ERROR 2>&1 | sed 's/^/  /' || true

cat <<MSG

  SIGVER publicado en:  https://$NGROK_DOMAIN/
  Admin:                https://$NGROK_DOMAIN/admin/

  La primera vez, ngrok muestra una página de aviso: tocar "Visit Site".
  Ctrl+C para cortar y volver al modo desarrollo.

MSG
# ngrok habla con nginx por HTTPS (puerto 443), así nginx y Django saben que
# la conexión es segura; ngrok no exige que el certificado local sea de confianza.
ngrok http https://localhost:443 --url "https://$NGROK_DOMAIN" --log stdout --log-level warn
