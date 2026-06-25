# Этап 1: Сборка
FROM golang:1.26-alpine3.23 AS builder

# Устанавливаем необходимые инструменты
RUN apk add --no-cache git ca-certificates tzdata

# Устанавливаем рабочую директорию
WORKDIR /build

# Копируем go.mod и go.sum для кэширования зависимостей
COPY go.mod go.sum ./
COPY minio-go ./minio-go/
RUN go mod download

# Копируем остальной код
COPY . .

# Собираем бинарник
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags="-w -s" \
    -o /app/service \
    ./cmd/mail-agent

# Этап 2: Финальный образ
FROM alpine:3.23

# Устанавливаем CA сертификаты и timezone data
RUN apk --no-cache add ca-certificates tzdata

# Создаем непривилегированного пользователя
# RUN addgroup -g 1000 -S appgroup && \
#     adduser -u 1000 -S appuser -G appgroup

# Копируем бинарник из этапа сборки
COPY --from=builder /app/service /app/service

WORKDIR /app

COPY ./internal/config/config.json ./internal/config/config.json

# Копируем конфиги если нужны
# COPY --chown=appuser:appgroup ./configs /app/configs

# Переключаемся на непривилегированного пользователя
# USER appuser

# Рабочая директория

# Запускаем сервис
ENTRYPOINT ["./service"]
