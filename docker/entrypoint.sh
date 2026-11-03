#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
    set -- chat
fi

case "$1" in
    chat|evaluate)
        if [ ! -s /app/runtime/store.sqlite3 ] || [ ! -s /app/runtime/policies.txt ]; then
            emporio setup >&2
        fi
        ;;
esac

exec emporio "$@"
