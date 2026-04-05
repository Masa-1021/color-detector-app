#!/bin/bash
# timesyncd-watcher: シグナルファイルを監視して systemd-timesyncd を制御する
SIGNAL_FILE="/run/circle-detector/ntp-active"
PREV_STATE=""

while true; do
    if [ -f "$SIGNAL_FILE" ]; then
        CURR_STATE="active"
    else
        CURR_STATE="inactive"
    fi

    if [ "$CURR_STATE" != "$PREV_STATE" ]; then
        if [ "$CURR_STATE" = "active" ]; then
            systemctl stop systemd-timesyncd
            echo "[timesyncd-watcher] Stopped systemd-timesyncd (app NTP active)"
        else
            systemctl start systemd-timesyncd
            echo "[timesyncd-watcher] Started systemd-timesyncd (app NTP inactive)"
        fi
        PREV_STATE="$CURR_STATE"
    fi

    sleep 2
done
