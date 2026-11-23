#!/usr/bin/env bash
# Genera el certificado HTTPS para probar SIGVER en la red local (celulares reales).
#
# Por qué: fuera de "localhost", los navegadores solo permiten service worker,
# GPS y cámara con HTTPS de confianza. Un certificado autofirmado no alcanza
# (Chrome en Android no registra el service worker), así que se crea una
# autoridad certificadora (CA) propia de SIGVER y con ella se firma el del servidor.
#
#   1. Correr este script:          scripts/certificado-local.sh [ip-o-nombre-extra ...]
#   2. Reiniciar nginx:             docker compose restart nginx
#   3. En cada celular de prueba, instalar la CA UNA sola vez:
#        - Abrir  http://<IP-de-esta-PC>/sigver-ca.crt  y descargarla
#        - Android: Ajustes > Seguridad > Cifrado y credenciales >
#                   Instalar un certificado > Certificado de CA
#        - iPhone:  instalar el perfil y luego Ajustes > General > Información >
#                   Ajustes de confianza de certificados > activar "SIGVER CA local"
#   4. Entrar a  https://<IP-de-esta-PC>/
#
# En producción NO se usa esto: se copia el certificado real (de ANDE o de
# Let's Encrypt) como nginx/certs/servidor.crt y nginx/certs/servidor.key.
set -euo pipefail
cd "$(dirname "$0")/.."

DIR=nginx/certs
mkdir -p "$DIR"
chmod 755 "$DIR"   # las claves privadas quedan en 600 (abajo)

# Restricción de nombres: esta CA SOLO puede firmar certificados para localhost
# y direcciones de redes privadas. Aunque alguien robara su clave, no podría
# usarla para hacerse pasar por un sitio real (un banco, Google, etc.).
RESTRICCION_NOMBRES="critical,permitted;DNS:localhost,permitted;IP:127.0.0.0/255.0.0.0,permitted;IP:10.0.0.0/255.0.0.0,permitted;IP:172.16.0.0/255.240.0.0,permitted;IP:192.168.0.0/255.255.0.0"

# --- Autoridad certificadora local (se crea una sola vez; si se rehace, hay que
#     reinstalarla en todos los celulares) ---
if [[ ! -f "$DIR/sigver-ca.key" ]]; then
    echo "Creando la CA local de SIGVER..."
    openssl req -x509 -new -nodes -newkey rsa:3072 -sha256 -days 825 \
        -keyout "$DIR/sigver-ca.key" -out "$DIR/sigver-ca.crt" \
        -subj "/O=SIGVER (desarrollo)/CN=SIGVER CA local" \
        -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "nameConstraints=$RESTRICCION_NOMBRES" 2>/dev/null
    chmod 600 "$DIR/sigver-ca.key"
else
    echo "Usando la CA existente ($DIR/sigver-ca.crt)."
fi

# --- Certificado del servidor: localhost + IP de esta PC en la red + extras ---
IP_LAN=$(hostname -I 2>/dev/null | awk '{print $1}')
SAN="DNS:localhost,IP:127.0.0.1"
[[ -n "$IP_LAN" ]] && SAN="$SAN,IP:$IP_LAN"
for extra in "$@"; do
    if [[ "$extra" =~ ^[0-9.]+$ ]]; then SAN="$SAN,IP:$extra"; else SAN="$SAN,DNS:$extra"; fi
done

EXT=$(mktemp)
trap 'rm -f "$EXT" "$DIR/servidor.csr"' EXIT
cat > "$EXT" <<EOF_EXT
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$SAN
EOF_EXT

openssl req -new -nodes -newkey rsa:2048 -sha256 \
    -keyout "$DIR/servidor.key" -out "$DIR/servidor.csr" \
    -subj "/O=SIGVER (desarrollo)/CN=${IP_LAN:-localhost}" 2>/dev/null
# 397 días: el máximo que aceptan iPhone y Chrome
openssl x509 -req -in "$DIR/servidor.csr" -CA "$DIR/sigver-ca.crt" -CAkey "$DIR/sigver-ca.key" \
    -CAcreateserial -out "$DIR/servidor.crt" -days 397 -sha256 -extfile "$EXT" 2>/dev/null
chmod 600 "$DIR/servidor.key"

echo "Certificado del servidor válido para: ${SAN//,/ }"
openssl x509 -in "$DIR/servidor.crt" -noout -enddate | sed 's/notAfter=/Vence: /'
echo
echo "Siguiente paso: docker compose restart nginx"
[[ -n "$IP_LAN" ]] && echo "CA para los celulares: http://$IP_LAN/sigver-ca.crt   ·   App: https://$IP_LAN/"
