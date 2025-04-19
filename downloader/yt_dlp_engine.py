import logging
from flask import Flask, jsonify, request
import yt_dlp
import os
import re
import threading

app = Flask(__name__)

# Set up logging
log_file_path = 'app.log'
if not os.path.exists(log_file_path):
    with open(log_file_path, 'w'): pass  # Create an empty log file if it doesn't exist.

logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,  # Set to DEBUG or INFO as needed
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Ensure the 'saved/videos/' directory exists
save_dir = './saved/videos/'
if not os.path.exists(save_dir):
    os.makedirs(save_dir)

def clean_filename(title):
    # Remove unwanted characters and replace spaces with underscores
    cleaned_title = re.sub(r'[^a-zA-Z0-9\s]', '', title)  # Remove special characters
    cleaned_title = cleaned_title.replace(' ', '_')  # Replace spaces with underscores
    cleaned_title = cleaned_title.replace('🔥', '').replace('🤯', '').replace('❗️', '')  # Remove emojis
    
    # Truncate filename if it's too long
    if len(cleaned_title) > 100:
        cleaned_title = cleaned_title[:100]  # Limit to 100 characters
    
    return cleaned_title

def download_video_yt_dlp(url):
    logging.info(f"Received download request for URL: {url}")
    
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',  # Download best video and audio
        'outtmpl': f'{save_dir}%(title)s.%(ext)s',  # Save location and filename template
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',  # Use FFmpeg for conversion
            'preferedformat': 'mp4',  # Ensure conversion to mp4
        }],
        'noplaylist': True,  # Don't download playlists
    }

    try:
        logging.info("Starting video download process...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            original_title = info_dict.get('title', 'Untitled')
            cleaned_filename = clean_filename(original_title)  # Clean up the filename
            filename = f'{save_dir}{cleaned_filename}.mp4'  # Save as .mp4 with cleaned-up name
            
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

def handle_download(url):
    download_video_yt_dlp(url)

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    
    if not url:
        logging.warning("No URL provided in the download request")
        return jsonify({"error": "No URL provided"}), 400

    try:
        logging.info(f"Received download request for URL: {url}")
        
        # Start the download in a separate thread
        download_thread = threading.Thread(target=handle_download, args=(url,))
        download_thread.start()

        return jsonify({"message": "Download started, check back later for completion."}), 200
    except Exception as e:
        logging.error(f"Error starting download: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        with open(log_file_path, 'r') as log_file:
            logs = log_file.readlines()
        return jsonify({'logs': logs[-10:]})  # Just send the last 10 log lines
    except Exception as e:
        logging.error(f"Error reading logs: {str(e)}")
        return jsonify({'error': 'Unable to retrieve logs'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
