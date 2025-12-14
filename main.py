import os
import time
import requests
import logging
import subprocess
import schedule
import urllib3
from datetime import datetime
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Configuration ---
API_HOST = os.getenv('UNIFI_HOST')
API_KEY = os.getenv('UNIFI_API_KEY')
CAMERA_NAMES = [name.strip() for name in os.getenv('CAMERA_NAMES', '').split(',') if name.strip()]

# Snapshot Settings
SNAPSHOT_INTERVAL = int(os.getenv('SNAPSHOT_INTERVAL', 60))
FORCE_HIGH_QUALITY = os.getenv('FORCE_HIGH_QUALITY', 'true').lower() == 'true'

# Video Settings
VIDEO_CRF = os.getenv('VIDEO_CRF', '23')
VIDEO_PRESET = os.getenv('VIDEO_PRESET', 'medium')
VIDEO_FRAMERATE = os.getenv('VIDEO_FRAMERATE', '30')

# Retention
RETENTION_IMAGES = int(os.getenv('RETENTION_DAYS_IMAGES', 3))
RETENTION_VIDEOS = int(os.getenv('RETENTION_DAYS_VIDEOS', 30))

# System
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

# --- Networking Setup ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create a session to reuse TCP connections (Performance boost)
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))
# Headers common to all requests
session.headers.update({
    "X-API-KEY": API_KEY, # Used by some auth methods
    "Cookie": f"TOKEN={API_KEY}", # Fallback if using session token directly
    "Accept": "application/json"
})

# --- Unifi API Functions ---
def get_cameras():
    """Fetches and filters cameras."""
    # This endpoint returns camera metadata
    url = f"https://{API_HOST}/proxy/protect/integration/v1/cameras"
    
    try:
        resp = session.get(url, verify=False, timeout=10)
        resp.raise_for_status()
        all_cameras = resp.json()

        if CAMERA_NAMES:
            # Case-insensitive matching
            target_names = {name.lower() for name in CAMERA_NAMES}
            filtered = [c for c in all_cameras if c.get('name', '').lower() in target_names]
            
            if not filtered:
                available = [c.get('name') for c in all_cameras]
                logger.warning(f"No cameras found matching: {CAMERA_NAMES}. Available: {available}")
            return filtered
            
        return all_cameras

    except Exception as e:
        logger.error(f"Failed to fetch camera list: {e}")
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
        # Sanitize name for filesystem
        cam_name = cam.get('name', cam_id).strip().replace(" ", "_").replace("/", "-")

        cam_root = IMG_DIR / cam_name
        daily_folder = cam_root / date_str
        daily_folder.mkdir(parents=True, exist_ok=True)

        # Protect API specific: toggle HQ vs Proxy stream
        params = {
            "forceHighQuality": "true" if FORCE_HIGH_QUALITY else "false"
        }

        url = f"https://{API_HOST}/proxy/protect/integration/v1/cameras/{cam_id}/snapshot"

        try:
            resp = session.get(url, params=params, verify=False, timeout=15)
            
            if resp.status_code == 200:
                # Save History
                (daily_folder / f"{time_str}.jpg").write_bytes(resp.content)
                # Save Latest (useful for quick previews/HomeAssistant)
                (cam_root / "latest.jpg").write_bytes(resp.content)
                
                logger.debug(f"Snapshot saved: {cam_name}")
            else:
                logger.warning(f"Failed snapshot {cam_name}: {resp.status_code} - {resp.text}")

        except Exception as e:
            logger.error(f"Error snapshotting {cam_name}: {e}")

# --- FFmpeg Functions ---
def update_daily_timelapse():
    """Generates or updates the timelapse video for the current day."""
    logger.info("Updating daily timelapse videos...")
    
    camera_dirs = [x for x in IMG_DIR.iterdir() if x.is_dir()]
    today_str = datetime.now().strftime('%Y-%m-%d')

    for cam_dir in camera_dirs:
        today_images_path = cam_dir / today_str
        
        if not today_images_path.exists():
            continue
        
        # Check if we have enough images to make a video (at least 5 frames)
        image_count = len(list(today_images_path.glob("*.jpg")))
        if image_count < 5:
            continue

        output_folder = VIDEO_DIR / cam_dir.name
        output_folder.mkdir(parents=True, exist_ok=True)
        output_file = output_folder / f"timelapse_{today_str}.mp4"

        # FFmpeg command
        cmd = [
            'ffmpeg',
            '-y', 
            '-framerate', VIDEO_FRAMERATE,
            '-pattern_type', 'glob',
            '-i', str(today_images_path / '*.jpg'),
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-crf', VIDEO_CRF,
            '-preset', VIDEO_PRESET,
            str(output_file)
        ]

        try:
            # Run quietly unless there is an error
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            logger.info(f"Updated timelapse: {output_file} ({image_count} frames)")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed for {cam_dir.name}: {e.stderr.decode()}")

# --- Cleanup Function ---
def cleanup_old_files():
    logger.info("Running cleanup task...")
    now = datetime.now()
    import shutil

    # 1. Clean Images
    for cam_dir in IMG_DIR.iterdir():
        if not cam_dir.is_dir(): continue
        for date_dir in cam_dir.iterdir():
            if not date_dir.is_dir(): continue 
            try:
                dir_date = datetime.strptime(date_dir.name, '%Y-%m-%d')
                if (now - dir_date).days > RETENTION_IMAGES:
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
    log_file = LOG_DIR / "app.log"
    if log_file.exists():
        stat = log_file.stat()
        if (now - datetime.fromtimestamp(stat.st_mtime)).days > RETENTION_IMAGES or stat.st_size > 10 * 1024 * 1024:
             with open(log_file, 'w'): pass
             logger.info("Log file truncated.")

# --- Main Scheduler ---
if __name__ == "__main__":
    logger.info("Starting UniFi Timelapse Service...")
    logger.info(f"Targeting Cameras: {CAMERA_NAMES if CAMERA_NAMES else 'ALL'}")
    logger.info(f"Quality: {'Full Sensor' if FORCE_HIGH_QUALITY else 'Proxy Stream'}")

    schedule.every(SNAPSHOT_INTERVAL).seconds.do(take_snapshots)
    schedule.every().hour.at(":00").do(update_daily_timelapse)
    schedule.every().day.at("01:00").do(cleanup_old_files)

    take_snapshots()
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Scheduler loop crash: {e}")
            time.sleep(5)
