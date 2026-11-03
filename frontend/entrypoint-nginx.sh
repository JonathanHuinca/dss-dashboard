#!/bin/sh
set -e

mkdir -p /etc/nginx/certs
if [ ! -f /etc/nginx/certs/cert.crt ] || [ ! -f /etc/nginx/certs/cert.key ]; then
    echo "[nginx] Generando certificado TLS provisional de contingencia para evitar caídas..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/certs/cert.key \
        -out /etc/nginx/certs/cert.crt \
        -subj "/C=CL/ST=Araucania/L=Temuco/O=UCT/OU=DSS/CN=localhost" 2>/dev/null || true
fi

exec "$@"
