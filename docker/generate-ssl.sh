#!/bin/sh

CERT_FILE="/etc/nginx/certs/cert.pem"
KEY_FILE="/etc/nginx/certs/key.pem"

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "Info: SSL certificates not found at /etc/nginx/certs/"
    echo "Info: Generating a temporary self-signed certificate..."
    
    # 如果当前容器环境内没有 openssl，则尝试静默安装
    if ! command -v openssl >/dev/null 2>&1; then
        if command -v apk >/dev/null 2>&1; then
            apk add --no-cache openssl
        elif command -v apt-get >/dev/null 2>&1; then
            apt-get update && apt-get install -y openssl
        fi
    fi

    mkdir -p /etc/nginx/certs
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$KEY_FILE" -out "$CERT_FILE" \
        -subj "/C=CN/ST=State/L=City/O=Vibe/CN=localhost"
        
    echo "Info: Self-signed certificate generated successfully."
else
    echo "Info: Custom SSL certificates found, skipping generation."
fi
