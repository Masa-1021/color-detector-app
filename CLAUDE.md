# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Circle Detector** is a Raspberry Pi web application that detects colors in circular regions of camera footage to determine the state of signal lights (patlights), then transmits the results via MQTT to Oracle DB.

## Running the Application

```bash
# Desktop app mode (Chromium --app mode, recommended for Pi)
./launch-desktop.sh

# CLI mode with auto-restart loop
./run.sh

# Run Flask backend directly
python3 -m circle_detector.app
# → http://localhost:5000

# Run MQTT-Oracle bridge (parent device only)
python3 mqtt_oracle_bridge.py
```

## Installing Dependencies

```bash
pip3 install --break-system-packages flask opencv-python-headless paho-mqtt numpy ntplib oracledb
```

## System Architecture

### Data Flow

```
Camera (MJPEG) → Detection Engine (HSV) → Rule Engine → MQTT Sender → MQTT Broker → MQTT-Oracle Bridge → Oracle DB
```

### Device Modes

- **Parent**: Full stack (camera detection + MQTT broker + Oracle DB bridge). One per deployment.
- **Child**: Camera detection only; sends results to parent via MQTT. Multiple allowed.

Device mode is set via the Web UI wizard on first launch and stored in `config/settings.json`.

### Key Modules

| File | Responsibility |
|------|---------------|
| `circle_detector/app.py` | Flask app, API endpoints, MJPEG streaming, startup initialization |
| `circle_detector/config_manager.py` | JSON config management; dataclasses: `ColorRange`, `Circle`, `Group`, `Rule`, `RuleCondition`, `DetectionResult`, `SendData` |
| `circle_detector/detector.py` | HSV color detection + blink detection (`BlinkDetector`, `DetectionEngine`) |
| `circle_detector/camera.py` | OpenCV VideoCapture, background frame thread, MJPEG encode |
| `circle_detector/mqtt_sender.py` | MQTT publish with file queue fallback on connection failure |
| `circle_detector/rule_engine.py` | Priority-ordered rule evaluation (single/composite conditions) |
| `circle_detector/ntp_sync.py` | Background NTP sync; corrects clock via `sudo date` if offset > 0.5s |
| `mqtt_oracle_bridge.py` | MQTT subscriber → Oracle DB INSERT (parent only) |
| `message_queue.py` | JSONL file-based queue for fault-tolerant message delivery |
| `equipment_status.py` | Equipment status definitions |

### Frontend

`circle_detector/templates/index.html` + `static/js/main.js` + `static/css/style.css`

- Pure JavaScript (no React/npm build step)
- Global `state` object for state management
- Two modes: **Edit mode** (draw/resize circles, register colors, configure rules) and **Run mode** (live detection, MQTT send log)
- Serendie Design System CSS variables

## Configuration

`config/settings.json` — edited via Web UI, not manually:

- `device_mode`: `"parent"` | `"child"`
- `station.sta_no1` / `sta_no2`: factory/line codes
- `mqtt`: broker, port, topic
- `oracle`: DSN, credentials, table name
- `blink_detection`: window_ms, min_changes, min/max interval
- `regions`: array of circle detection regions with HSV color mappings

## HSV Color Detection

OpenCV uses H: 0–179, S: 0–255, V: 0–255. Hue matching uses circular arithmetic (e.g., near 0°/180° boundary). Color matching compares ROI average HSV against registered `ColorRange` entries.

## Fault Tolerance

Both MQTT sender and Oracle bridge use `message_queue.py` (`FileQueue`) to persist undelivered messages to `queue/` as JSONL. A background retry thread re-sends when connectivity is restored.

## Deployment (Raspberry Pi)

```bash
# Install desktop integration (app menu, taskbar, autostart)
./install.sh

# Or via systemd
sudo systemctl enable circle-detector
sudo systemctl start circle-detector
```

Service definitions in `systemd/`.
