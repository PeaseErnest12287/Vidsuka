import logging
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import os
import re
import threading
import time

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

# Global variable to store download progress
download_progress = {}

# --------------------- Helper Functions ---------------------

def clean_filename(title):
    # Remove unwanted characters and replace spaces with underscores
    cleaned_title = re.sub(r'[^a-zA-Z0-9\s]', '', title)  # Remove special characters
    cleaned_title = cleaned_title.replace(' ', '_')  # Replace spaces with underscores
    cleaned_title = cleaned_title.replace('🔥', '').replace('🤯', '').replace('❗️', '')  # Remove emojis
    
    # Truncate filename if it's too long
    if len(cleaned_title) > 100:
        cleaned_title = cleaned_title[:100]  # Limit to 100 characters
    
    return cleaned_title

def download_video_yt_dlp(url, format_choice=None):
    global download_progress
    logging.info(f"Received download request for URL: {url}")

    ydl_opts = {
        'format': format_choice if format_choice else 'bestvideo+bestaudio/best',  # Use provided format or best option
        'outtmpl': f'{VIDEO_DIR}%(title)s.%(ext)s',  # Save location and filename template
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',  # Use FFmpeg for conversion
            'preferedformat': 'mp4',  # Ensure conversion to mp4
        }],
        'noplaylist': True,  # Don't download playlists
        'progress_hooks': [lambda d: progress_hook(d)],  # Hook to track download progress
    }

    try:
        logging.info("Starting video download process...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            original_title = info_dict.get('title', 'Untitled')
            cleaned_filename = clean_filename(original_title)  # Clean up the filename
            filename = f'{VIDEO_DIR}{cleaned_filename}.mp4'  # Save as .mp4 with cleaned-up name
            
            logging.info(f"Download successful: {filename}")
            return {
                'title': original_title,
                'url': info_dict.get('url'),
                'file_size': info_dict.get('filesize'),
                'filename': filename
            }
    except Exception as e:
        logging.error(f"Error downloading video: {str(e)}")
        raise Exception(f"Error downloading video: {str(e)}")

def progress_hook(d):
    global download_progress
    if d['status'] == 'downloading':
        download_progress = {
            'status': 'downloading',
            'downloaded': d['downloaded_bytes'],
            'total': d['total_bytes'],
            'percent': (d['downloaded_bytes'] / d['total_bytes']) * 100,
        }

def get_video_formats(url):
    try:
        with yt_dlp.YoutubeDL({'noplaylist': True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)  # Do not download, just fetch formats
            formats = info_dict.get('formats', [])
            return formats
    except Exception as e:
        logging.error(f"Error retrieving formats: {str(e)}")
        raise Exception(f"Error retrieving formats: {str(e)}")

# --------------------- Routes ---------------------

@app.route('/formats', methods=['POST'])
def get_formats():
    data = request.json
    url = data.get('url')

    if not url:
        logging.warning("No URL provided in the request for formats")
        return jsonify({"error": "No URL provided"}), 400

    try:
        logging.info(f"Received format request for URL: {url}")
        formats = get_video_formats(url)
        return jsonify({'formats': formats}), 200
    except Exception as e:
        logging.error(f"Error retrieving formats: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    format_choice = data.get('format', None)  # Get the format choice, if provided

    if not url:
        logging.warning("No URL provided in the download request")
        return jsonify({"error": "No URL provided"}), 400

    try:
        logging.info(f"Received download request for URL: {url}")
        
        # Download using yt_dlp with the selected format
        video_info = download_video_yt_dlp(url, format_choice)

        logging.info(f"Video download completed for: {video_info.get('title', 'Unknown Title')}")
        return jsonify(video_info), 200

    except Exception as e:
        logging.error(f"Error during video download: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/download-progress', methods=['GET'])
def get_download_progress():
    return jsonify(download_progress)

@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        with open(log_file_path, 'r') as log_file:
            logs = log_file.readlines()
        return jsonify({'logs': logs[-10:]})  # Just send the last 10 log lines
    except Exception as e:
        logging.error(f"Error reading logs: {str(e)}")
        return jsonify({'error': 'Unable to retrieve logs'}), 500

# --------------------- Run ---------------------

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
