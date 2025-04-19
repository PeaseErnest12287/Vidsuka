import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import re

# --------------------- Setup ---------------------
app = Flask(__name__)
CORS(app)

log_file_path = 'app.log'
logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

VIDEO_DIR = './saved/videos'
os.makedirs(VIDEO_DIR, exist_ok=True)

download_progress = {}

# --------------------- Helper Functions ---------------------

def clean_filename(title):
    cleaned_title = re.sub(r'[^a-zA-Z0-9\s]', '', title)
    cleaned_title = cleaned_title.replace(' ', '_').replace('🔥', '').replace('🤯', '').replace('❗️', '')
    return cleaned_title[:100] if len(cleaned_title) > 100 else cleaned_title

def progress_hook(d):
    global download_progress
    if d['status'] == 'downloading':
        try:
            percent = (d['downloaded_bytes'] / d['total_bytes']) * 100 if d.get('total_bytes') else 0
        except ZeroDivisionError:
            percent = 0
        download_progress = {
            'status': 'downloading',
            'downloaded': d.get('downloaded_bytes', 0),
            'total': d.get('total_bytes', 0),
            'percent': percent
        }

def download_video_yt_dlp(url, format_choice=None):
    global download_progress
    logging.info(f"Request received for URL: {url}")

    # Temporary output filename pattern
    temp_outtmpl = f'{VIDEO_DIR}/%(title)s.%(ext)s'

    ydl_opts = {
        'format': format_choice if format_choice else 'bestvideo+bestaudio/best',
        'outtmpl': temp_outtmpl,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'noplaylist': True,
        'progress_hooks': [progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Untitled')
            ext = 'mp4'
            cleaned = clean_filename(title)
            real_filename = os.path.join(VIDEO_DIR, f"{cleaned}.{ext}")

            # Sometimes yt-dlp returns final filename
            downloaded_file = ydl.prepare_filename(info)
            if not downloaded_file.endswith('.mp4'):
                downloaded_file = downloaded_file.rsplit('.', 1)[0] + '.mp4'

            # Rename if needed
            if os.path.exists(downloaded_file) and downloaded_file != real_filename:
                os.rename(downloaded_file, real_filename)
                logging.info(f"Renamed file to {real_filename}")

            logging.info(f"Final file path: {real_filename}")
            return real_filename

    except Exception as e:
        logging.error(f"Download error: {str(e)}")
        raise Exception(f"Download failed: {str(e)}")

# --------------------- Routes ---------------------

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    format_choice = data.get('format')

    if not url:
        logging.warning("No URL provided")
        return jsonify({"error": "No URL provided"}), 400

    try:
        logging.info(f"Starting download for: {url}")
        filename = download_video_yt_dlp(url, format_choice)

        if not os.path.exists(filename):
            logging.error(f"File not found: {filename}")
            return jsonify({"error": "Download complete, but file not found"}), 500

        logging.info(f"Sending file: {filename}")
        return send_file(filename, as_attachment=True)

    except Exception as e:
        logging.error(f"Exception during /download: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/download-progress', methods=['GET'])
def get_download_progress():
    return jsonify(download_progress)

# --------------------- Run ---------------------

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
