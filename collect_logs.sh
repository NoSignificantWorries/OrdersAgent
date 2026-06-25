#!/bin/bash

DATE=$(date +%Y-%m-%d_%H-%M-%S)
LOG_DIR="./logs/$DATE"
mkdir -p $LOG_DIR

docker compose logs --no-color > "$LOG_DIR/all-services.log"

for service in $(docker compose config --services); do
    docker compose logs --no-color $service > "$LOG_DIR/$service.log"
done

echo "Logs saved to $LOG_DIR"
