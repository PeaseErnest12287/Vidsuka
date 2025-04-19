from flask import Flask, request, jsonify
from downloader.yt_dlp_engine import download_video_yt_dlp
from downloader.pytube_engine import download_video_pytube
from saved.cleanup import clean_old_videos
import os
import logging

# Set up logging
log_file_path = 'app.log'
logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

# Ensure the video directory exists
VIDEO_DIR = './saved/videos'
if not os.path.exists(VIDEO_DIR):
    os.makedirs(VIDEO_DIR)

# Clean up old videos periodically (you can schedule this job if needed)
clean_old_videos()

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    platform = data.get('platform', 'yt_dlp')  # Default to yt_dlp

    if not url:
        logging.warning("No URL provided in the download request")
        return jsonify({"error": "No URL provided"}), 400

    try:
        logging.info(f"Received download request for URL: {url} on platform: {platform}")
        # Call appropriate download function based on platform
        if platform == 'yt_dlp':
            video_info = download_video_yt_dlp(url)
        else:
            video_info = download_video_pytube(url)
        
        logging.info(f"Video download completed for: {video_info['title']}")
        return jsonify(video_info), 200
    except Exception as e:
        logging.error(f"Error during video download: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    # Start the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        with open(log_file_path, 'r') as log_file:
            logs = log_file.readlines()
        return jsonify({'logs': logs[-10:]})
    except Exception as e:
        logging.error(f"Error reading logs: {str(e)}")
        return jsonify({'error': 'Unable to retrieve logs'}), 500
