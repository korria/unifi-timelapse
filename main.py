import os
import time
import requests
import logging
import subprocess
import schedule
from datetime import datetime
from pathlib import Path
import urllib3

# --- Configuration ---
API_HOST = os.getenv('UNIFI_HOST')
API_KEY = os.getenv('UNIFI_API_KEY')
SNAPSHOT_INTERVAL = int(os.getenv('SNAPSHOT_INTERVAL', 60))
RETENTION_IMAGES = int(os.getenv('RETENTION_DAYS_IMAGES', 3))
RETENTION_VIDEOS = int(os.getenv('RETENTION_DAYS_VIDEOS', 30))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# --- Setup Paths ---
BASE_DIR = Path("/data")
IMG_DIR = BASE_DIR / "images"
VIDEO_DIR = BASE_DIR / "videos"
LOG_DIR = BASE_DIR / "logs"

for d in [IMG_DIR, VIDEO_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- Logging ---
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# --- Unifi API Functions ---
def get_cameras():
    url = f"https://{API_HOST}/proxy/protect/integration/v1/cameras"
    headers = {
        "X-API-KEY": API_KEY,
        "Accept": "application/json"
    }
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch cameras: {e}")
        return []

def take_snapshots():
    cameras = get_cameras()
    if not cameras:
        return

    timestamp = datetime.now()
    date_str = timestamp.strftime('%Y-%m-%d')
    time_str = timestamp.strftime('%H-%M-%S')

    for cam in cameras:
        cam_id = cam.get('id')
        cam_name = cam.get('name', cam_id).replace(" ", "_")
        
        # Define paths
        cam_root = IMG_DIR / cam_name
        daily_folder = cam_root / date_str
        
        # Ensure daily folder exists
        daily_folder.mkdir(parents=True, exist_ok=True)

        url = f"https://{API_HOST}/proxy/protect/integration/v1/cameras/{cam_id}/snapshot"
        headers = {"X-API-KEY": API_KEY}

        try:
            resp = requests.get(url, headers=headers, verify=False, timeout=10)
            if resp.status_code == 200:
                # 1. Save Timestamped Image (History)
                file_path = daily_folder / f"{time_str}.jpg"
                with open(file_path, 'wb') as f:
                    f.write(resp.content)
                
                # 2. Save Latest Image (Overwrite)
                latest_path = cam_root / "latest.jpg"
                with open(latest_path, 'wb') as f:
                    f.write(resp.content)
                    
                logger.debug(f"Snapshot saved for {cam_name}")
            else:
                logger.warning(f"Failed snapshot for {cam_name}: {resp.status_code}")
        except Exception as e:
            logger.error(f"Error snapshotting {cam_name}: {e}")

# --- FFmpeg Functions ---
def generate_hourly_timelapse():
    logger.info("Starting hourly timelapse generation...")
    
    camera_dirs = [x for x in IMG_DIR.iterdir() if x.is_dir()]
    today_str = datetime.now().strftime('%Y-%m-%d')

    for cam_dir in camera_dirs:
        today_images_path = cam_dir / today_str
        
        if not today_images_path.exists():
            continue

        output_folder = VIDEO_DIR / cam_dir.name
        output_folder.mkdir(parents=True, exist_ok=True)
        output_file = output_folder / f"timelapse_{today_str}.mp4"

        # FFmpeg command
        cmd = [
            'ffmpeg',
            '-y', 
            '-framerate', '30',
            '-pattern_type', 'glob',
            '-i', str(today_images_path / '*.jpg'),
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            str(output_file)
        ]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Generated timelapse: {output_file}")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed for {cam_dir.name}: {e}")

# --- Cleanup Function ---
def cleanup_old_files():
    logger.info("Running cleanup...")
    now = datetime.now()

    # 1. Clean Images
    for cam_dir in IMG_DIR.iterdir():
        if not cam_dir.is_dir(): continue
        for date_dir in cam_dir.iterdir():
            if not date_dir.is_dir(): continue # Skip latest.jpg
            try:
                dir_date = datetime.strptime(date_dir.name, '%Y-%m-%d')
                if (now - dir_date).days > RETENTION_IMAGES:
                    import shutil
                    shutil.rmtree(date_dir)
                    logger.info(f"Deleted old images: {date_dir}")
            except ValueError:
                continue 

    # 2. Clean Videos
    for cam_dir in VIDEO_DIR.iterdir():
        if not cam_dir.is_dir(): continue
        for video_file in cam_dir.glob("*.mp4"):
            try:
                date_part = video_file.stem.replace("timelapse_", "")
                vid_date = datetime.strptime(date_part, '%Y-%m-%d')
                if (now - vid_date).days > RETENTION_VIDEOS:
                    video_file.unlink()
                    logger.info(f"Deleted old video: {video_file}")
            except ValueError:
                continue
    
    # 3. Clean Logs
    for log_file in LOG_DIR.glob("*.log"):
         if (now - datetime.fromtimestamp(log_file.stat().st_mtime)).days > RETENTION_IMAGES:
             with open(log_file, 'w'): pass 

# --- Main Scheduler ---
if __name__ == "__main__":
    urllib3.disable_warnings()

    logger.info("Starting UniFi Timelapse Service...")
    
    schedule.every(SNAPSHOT_INTERVAL).seconds.do(take_snapshots)
    schedule.every().hour.at(":00").do(generate_hourly_timelapse)
    schedule.every().day.at("01:00").do(cleanup_old_files)

    take_snapshots()
    
    while True:
        schedule.run_pending()
        time.sleep(1)
