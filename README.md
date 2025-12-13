# UniFi Protect Timelapse Creator

A Dockerized Python service that automatically interacts with the local UniFi Protect API to capture snapshots, maintain a "latest" image reference, generate daily timelapse videos using FFmpeg, and manage file retention.

## Features

* **Auto-Discovery:** Automatically finds all cameras connected to your UniFi Protect console.
* **Snapshots:** Captures high-res snapshots at a configurable interval (default: 60s).
* **Latest Image:** Maintains a `latest.jpg` in the camera root folder (useful for custom dashboards or Home Assistant).
* **Hourly Compiles:** Generates an MP4 timelapse of the *current* day every hour (overwrites the file so it grows throughout the day).
* **Auto-Cleanup:** Automatically deletes raw images and video files older than your configured retention period to save disk space.
* **Local API:** Uses the local UniFi Integration API (no cloud dependency required).

## Prerequisites

* **Docker** & **Docker Compose** installed on your host machine.
* A **UniFi Console** (UDM Pro, UNVR, Cloud Key Gen2+) running the Protect application.
* Local Administrator access to the UniFi Console to generate an API Key.

## Installation & Setup

### 1. Get your UniFi API Key
1.  Log in to your UniFi Site manager `unifi.ui.com`.
2.  Navigate to **Settings** (System Settings, not the Network app).
3.  Go to **Admins & Users** or **Control Plane** $\rightarrow$ **Integrations**.
4.  Create a new **API Key** for UniFi Protect.
5.  **Copy the API Key immediately.** You won't be able to see it again.

### 2. Project Structure
Create a directory on your server (e.g., `unifi-timelapse`) and place the three required files (`Dockerfile`, `docker-compose.yml`, `main.py`) inside it.

```text
unifi-timelapse/
├── Dockerfile
├── docker-compose.yml
├── main.py
└── data/              <-- (Created automatically by Docker)
    ├── images/
    ├── videos/
    └── logs/
```

### 3. Configure docker-compose.yml
Open `docker-compose.yml` and update the environment variables:
```text
version: '3.8'

services:
  unifi-timelapse:
    build: .
    container_name: unifi-timelapse
    restart: unless-stopped
    environment:
      - UNIFI_HOST=192.168.1.1        # Your Console IP
      - UNIFI_API_KEY=YOUR_KEY_HERE   # The key you copied in Step 1
      - SNAPSHOT_INTERVAL=60          # Seconds between snapshots
      - RETENTION_DAYS_IMAGES=3       # How long to keep raw JPEGs
      - RETENTION_DAYS_VIDEOS=30      # How long to keep MP4s
      - TZ=America/New_York           # Your Timezone
    volumes:
      - ./data:/data                  # Local storage mapping
```

### 4. Build and Run

Execute the following command in the project directory:
`docker-compose up -d --build`
