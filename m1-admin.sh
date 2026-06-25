#!/bin/bash

CONTAINER_NAME="storage"
POSTGRES_DB="mails_data"
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="1234"

source ./.env

exec_sql() {
    docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -F $'\t' -c "$1"
}

list_users() {
    echo "==========================================================="
    printf "%-10s | %-30s | %-20s\n" "ID" "Email" "Role"
    echo "==========================================================="

    exec_sql "SELECT id, email, role FROM users ORDER BY id;" | while IFS=$'\t' read -r id email role; do
        printf "%-10s | %-30s | %-20s\n" "$id" "$email" "$role"
    done
    echo "==========================================================="
}

set_role() {
    local identifier="$1"
    local role="$2"
    local field=""

    valid_roles=("standart" "admin" "manager")
    local valid=0
    for valid_role in "${valid_roles[@]}"; do
        if [[ "$role" == "$valid_role" ]]; then
            valid=1
            break
        fi
    done

    if [[ $valid -eq 0 ]]; then
        echo "Ошибка: Неверная роль '$role'"
        echo "Доступные роли: ${valid_roles[*]}"
        exit 1
    fi

    if [[ "$identifier" =~ ^[0-9]+$ ]]; then
        field="id"
    else
        field="email"
    fi

    local user_exists=$(exec_sql "SELECT COUNT(*) FROM users WHERE $field = '$identifier';")
    user_exists=$(echo "$user_exists" | xargs)

    if [[ "$user_exists" -eq 0 ]]; then
        echo "Ошибка: Пользователь с $field '$identifier' не найден"
        exit 1
    fi

    # Обновляем роль
    exec_sql "UPDATE users SET role = '$role' WHERE $field = '$identifier';" > /dev/null 2>&1

    if [[ $? -eq 0 ]]; then
        echo "Роль успешно обновлена"
        echo ""
        echo "Новые данные пользователя:"
        exec_sql "SELECT id, email, role FROM users WHERE $field = '$identifier';" | while IFS=$'\t' read -r id email role; do
            printf "ID: %s\nEmail: %s\nРоль: %s\n" "$id" "$email" "$role"
        done
    else
        echo "Ошибка при обновлении роли"
        exit 1
    fi
}

# Функция показа помощи
show_help() {
    cat << EOF
Использование: ./m1-admin.sh <команда> [опции]

Команды:
  list                                Показать список всех пользователей
  set-role -e <email> <role>         Установить роль пользователю по email
  set-role -i <id> <role>            Установить роль пользователю по ID
  help                               Показать эту справку

Примеры:
  ./m1-admin.sh list
  ./m1-admin.sh set-role -e user@example.com admin
  ./m1-admin.sh set-role -i 42 standart

Доступные роли:
  standart, manager, admin
EOF
}

# ============================================
# MAIN
# ============================================

case "$1" in
    list)
        list_users
        ;;
    set-role)
        shift
        if [[ "$1" == "-e" ]]; then
            shift
            if [[ -z "$1" ]] || [[ -z "$2" ]]; then
                echo "Ошибка: Необходимо указать email и роль"
                echo "Пример: ./m1-admin.sh set-role -e user@example.com admin"
                exit 1
            fi
            set_role "$1" "$2"
        elif [[ "$1" == "-i" ]]; then
            shift
            if [[ -z "$1" ]] || [[ -z "$2" ]]; then
                echo "Ошибка: Необходимо указать ID и роль"
                echo "Пример: ./m1-admin.sh set-role -i 42 standart"
                exit 1
            fi
            set_role "$1" "$2"
        else
            echo "Ошибка: Используйте -e для email или -i для ID"
            show_help
            exit 1
        fi
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Ошибка: Неизвестная команда '$1'"
        echo ""
        show_help
        exit 1
        ;;
esac
