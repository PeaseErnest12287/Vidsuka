import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import re
import threading
import time

# --------------------- Setup ---------------------
app = Flask(__name__)
CORS(app)

log_file_path = 'app.log'
logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

VIDEO_DIR = os.path.join('.', 'saved', 'videos')
os.makedirs(VIDEO_DIR, exist_ok=True)

download_progress = {}

# --------------------- Helper Functions ---------------------

def clean_filename(title):
    cleaned_title = re.sub(r'[^a-zA-Z0-9\s]', '', title)
    cleaned_title = cleaned_title.replace(' ', '_')
    cleaned_title = cleaned_title.replace('🔥', '').replace('🤯', '').replace('❗️', '')
    return cleaned_title[:100]  # Limit to 100 characters

def progress_hook(d):
    global download_progress
    try:
        if d.get('status') == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
            percent = (downloaded / total) * 100 if total > 0 else 0
            download_progress = {
                'status': 'downloading',
                'downloaded': downloaded,
                'total': total,
                'percent': percent,
            }
            logging.debug(f"Progress: {downloaded}/{total} bytes ({percent:.2f}%)")
    except Exception as e:
        logging.error(f"Error in progress_hook: {str(e)}")

def download_video_yt_dlp(url, format_choice=None):
    global download_progress
    logging.info(f"Initiating download for URL: {url}")

    ydl_opts = {
        'format': format_choice if format_choice else 'bestvideo+bestaudio/best',
        'outtmpl': os.path.join(VIDEO_DIR, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'noplaylist': True,
        'progress_hooks': [progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            original_title = info_dict.get('title', 'Untitled')
            cleaned_filename = clean_filename(original_title)
            final_path = os.path.join(VIDEO_DIR, f"{cleaned_filename}.mp4")

            logging.info(f"Download completed. Final file path: {final_path}")
            return final_path
    except Exception as e:
        logging.error(f"Download error: {str(e)}")
        raise Exception(f"Download error: {str(e)}")

# --------------------- Routes ---------------------

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    format_choice = data.get('format')

    if not url:
        logging.warning("Download request missing 'url'")
        return jsonify({"error": "No URL provided"}), 400

    try:
        logging.info(f"POST /download received with URL: {url}")
        filename = download_video_yt_dlp(url, format_choice)

        if not os.path.exists(filename):
            logging.error(f"File does not exist after download: {filename}")
            return jsonify({"error": "File not found after download"}), 500

        logging.info(f"Preparing to send file: {filename}")
        return send_file(filename, as_attachment=True)

    except Exception as e:
        logging.error(f"Unhandled error in /download: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/download-progress', methods=['GET'])
def get_download_progress():
    return jsonify(download_progress)

# --------------------- Run ---------------------

if __name__ == '__main__':
    logging.info("Starting Flask server on port 5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
