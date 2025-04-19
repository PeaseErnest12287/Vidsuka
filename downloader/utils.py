import os
import logging

# Set up logging
log_file_path = 'app.log'
logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_video_file_path(filename):
    # Return the file path for a given video filename
    file_path = os.path.join('./saved/videos', filename)
    logging.info(f"Checked file path for video: {file_path}")
    return file_path

def get_video_size(filename):
    # Return the size of the video file in MB
    file_path = get_video_file_path(filename)
    if os.path.exists(file_path):
        size = os.path.getsize(file_path) / (1024 * 1024)  # Size in MB
        logging.info(f"Video file {filename} exists, size: {size} MB")
        return size
    logging.warning(f"Video file {filename} does not exist")
    return 0
