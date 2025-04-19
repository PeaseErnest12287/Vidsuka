import os
import time

VIDEO_DIR = './saved/videos'
MAX_AGE = 2 * 60 * 60  # 24 hours in seconds

def clean_old_videos():
    current_time = time.time()
    for filename in os.listdir(VIDEO_DIR):
        file_path = os.path.join(VIDEO_DIR, filename)
        if os.path.isfile(file_path):
            file_age = current_time - os.path.getctime(file_path)
            if file_age > MAX_AGE:
                os.remove(file_path)
                print(f"Deleted old video: {filename}")

