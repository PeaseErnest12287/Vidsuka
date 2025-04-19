from flask import Flask, request, jsonify
from flask_cors import CORS
from downloader.yt_dlp_engine import download_video_yt_dlp
from downloader.pytube_engine import download_video_pytube
from saved.cleanup import clean_old_videos
import os
import logging

# --------------------- Setup ---------------------
app = Flask(__name__)
CORS(app)  # Allow all origins by default (adjust for production)

# Logging setup
log_file_path = 'app.log'
logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create video directory if it doesn't exist
VIDEO_DIR = './saved/videos'
os.makedirs(VIDEO_DIR, exist_ok=True)

# Clean old videos on startup
clean_old_videos()

# --------------------- Routes ---------------------

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    platform = data.get('platform', 'yt_dlp')

    if not url:
        logging.warning("No URL provided in the download request")
        return jsonify({"error": "No URL provided"}), 400

    try:
        logging.info(f"Received download request for URL: {url} on platform: {platform}")
        
        # Download using chosen engine
        if platform == 'yt_dlp':
            video_info = download_video_yt_dlp(url)
        else:
            video_info = download_video_pytube(url)

        logging.info(f"Video download completed for: {video_info.get('title', 'Unknown Title')}")
        return jsonify(video_info), 200

    except Exception as e:
        logging.error(f"Error during video download: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        with open(log_file_path, 'r') as log_file:
            logs = log_file.readlines()
        return jsonify({'logs': logs[-10:]})
    except Exception as e:
        logging.error(f"Error reading logs: {str(e)}")
        return jsonify({'error': 'Unable to retrieve logs'}), 500

# --------------------- Run ---------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
