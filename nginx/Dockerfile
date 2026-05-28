FROM nginx:1.27-alpine

# openssl ставится только для генерации self-signed серта при сборке.
# В финальном образе остаётся (мелкий — ~3MB), но сертификат уже сгенерирован.
RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/certs \
    && openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout /etc/nginx/certs/server.key \
        -out /etc/nginx/certs/server.crt \
        -days 365 \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

COPY default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80 443

# Образ запускает дефолтный nginx CMD из базового image.
