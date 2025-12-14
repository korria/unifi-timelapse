# UniFi Protect Timelapse Generator

A Docker service that auto-discovers your UniFi Protect cameras, snaps photos at intervals, and stitches them into daily timelapse videos using FFmpeg.

## Features
* **Multi-Camera Support:** Supports one, multiple, or all cameras automatically.
* **Resolution Control:** Toggle `FORCE_HIGH_QUALITY` to switch between full sensor resolution (4K) or the lighter proxy stream (720p).
* **Video Quality Control:** Configurable CRF and Presets for FFmpeg.
* **Smart Retention:** Auto-deletes old images and videos to save space.
* **Resilient:** Uses connection pooling and retry logic.

## Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `UNIFI_HOST` | - | Local IP of your UDM/UNVR. |
| `UNIFI_API_KEY` | - | Local user password. |
| `CAMERA_NAMES` | (All) | Comma-separated list (e.g., `Front Porch,Garage`). Empty = All cameras. |
| `SNAPSHOT_INTERVAL` | `60` | Seconds between photos. |
| `FORCE_HIGH_QUALITY`| `true` | `true` = Full Res (4K/2K). `false` = Proxy (720p). |
| `VIDEO_CRF` | `23` | Quality (0-51). Lower is better. |
| `VIDEO_PRESET` | `medium` | `medium`, `slow`, `fast`, etc. |
| `RETENTION_DAYS_IMAGES` | `3` | Days to keep JPEGs. |
| `RETENTION_DAYS_VIDEOS` | `30` | Days to keep MP4s. |

## Quick Start

1. Create a **Local User** in UniFi OS (Admin -> Restricted to Local Access Only) with **View Only** permissions for Protect.
2. Update your `docker-compose.yaml`.
3. Run:
   ```bash
   docker-compose up -d --build
