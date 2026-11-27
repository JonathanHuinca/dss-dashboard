#!/bin/sh
set -e

mkdir -p /etc/nginx/certs
if [ ! -f /etc/nginx/certs/cert.crt ] || [ ! -f /etc/nginx/certs/cert.key ]; then
    echo "[nginx] Generando certificado TLS provisional de contingencia..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/certs/cert.key \
        -out /etc/nginx/certs/cert.crt \
        -subj "/C=CL/ST=Araucania/L=Temuco/O=UCT/OU=DSS/CN=localhost" 2>/dev/null || true
fi

API_TARGET="api:8000"
DIAG_INFO="init"

for CAND in api indicadoreshikcentral-api-dev uct-dss-api-1 127.0.0.1; do
    IP_CAND=$(getent hosts "$CAND" 2>/dev/null | awk '{print $1}' | head -n 1)
    if [ -n "$IP_CAND" ]; then
        if wget -q -T 3 -O /dev/null "http://${CAND}:8000/health" 2>/dev/null; then
            API_TARGET="${CAND}:8000"
            DIAG_INFO="ok:${CAND}(${IP_CAND})"
            break
        else
            DIAG_INFO="${DIAG_INFO}_fail:${CAND}(${IP_CAND})"
        fi
    else
        DIAG_INFO="${DIAG_INFO}_nohost:${CAND}"
    fi
done

if echo "$DIAG_INFO" | grep -qv "^ok:"; then
    MY_IPS=$(hostname -i 2>/dev/null || true)
    DIAG_INFO="${DIAG_INFO}_myips:$(echo $MY_IPS | tr ' ' ',')"
    for MY_IP in $MY_IPS; do
        PREFIX=$(echo "$MY_IP" | awk -F. '{print $1"."$2"."$3}')
        if [ -n "$PREFIX" ]; then
            for i in 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
                TEST_IP="${PREFIX}.${i}"
                if [ "$TEST_IP" != "$MY_IP" ]; then
                    if wget -q -T 1 -O - "http://${TEST_IP}:8000/health" 2>/dev/null | grep -q '"status":"ok"'; then
                        API_TARGET="${TEST_IP}:8000"
                        DIAG_INFO="ok_ip:${TEST_IP}_${DIAG_INFO}"
                        break 2
                    fi
                fi
            done
        fi
    done
fi

echo "[nginx] Upstream API detectado: http://${API_TARGET} (${DIAG_INFO})"
sed -i "s|__API_UPSTREAM__|http://${API_TARGET}|g" /etc/nginx/conf.d/default.conf
sed -i "s|__DIAG_INFO__|${DIAG_INFO}|g" /etc/nginx/conf.d/default.conf

exec "$@"
