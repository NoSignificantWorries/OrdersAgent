#!/bin/bash

while true; do
    cd ~/OrdersAgent || exit

    DOWN=$(docker compose ps --services --filter "status=exited" --filter "status=restarting" 2>/dev/null)

    if [ ! -z "$DOWN" ]; then
        TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
        LOG_DIR="./logs/crash-logs/$TIMESTAMP"
        mkdir -p "$LOG_DIR"

        echo "[$TIMESTAMP] ALERT: Services down: $DOWN"
        docker compose logs --no-color > "$LOG_DIR/all-services.log"

        for service in $DOWN; do
            docker compose logs --no-color $service > "$LOG_DIR/$service.log"
        done
    fi

    sleep 30
done
