import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_apscheduler import APScheduler
import yt_dlp as youtube_dl
import uuid
import re
from datetime import datetime, timedelta
from pathlib import Path
import logging
from dotenv import load_dotenv
from urllib.parse import unquote, quote

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_folder='../frontend/build', static_url_path='/')

# Configure CORS
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://pracky.vercel.app",
            "http://localhost:3000"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"],
        "supports_credentials": True
    }
})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', 'https://pracky.vercel.app')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# Configuration
DOWNLOAD_FOLDER = Path(os.getenv('DOWNLOAD_FOLDER', 'downloads'))
DOWNLOAD_FOLDER.mkdir(exist_ok=True)
MAX_FILENAME_LENGTH = 100
CLEANUP_OLDER_THAN = timedelta(hours=24)  # 24 hours

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PrackyDownloader")

# Initialize scheduler
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Helper functions
def sanitize_filename(filename):
    """Sanitize filename to remove invalid characters but keep spaces"""
    filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
    if len(filename) > MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(filename)
        filename = name[:MAX_FILENAME_LENGTH-len(ext)] + ext
    return filename

def get_video_info(url):
    """Get video info without downloading with platform-specific handling"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'extract_flat': False,
        'ignoreerrors': True,
        'extractor_args': {
            'youtube': {'skip': ['dash', 'hls']},
            'instagram': {'extract_flat': True},
            'facebook': {'extract_flat': True}
        }
    }
    
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Handle cases where info might be None
            if not info:
                raise Exception("No video information could be extracted")
                
            # Default values for Instagram/Facebook
            if 'extractor' in info and info['extractor'] in ['instagram', 'facebook']:
                return {
                    'title': info.get('title', 'Instagram Video') if 'instagram' in info['extractor'] else 'Facebook Video',
                    'thumbnail': info.get('thumbnail'),
                    'duration': info.get('duration', 0),
                    'formats': [{
                        'format_id': 'best',
                        'ext': 'mp4',
                        'height': 1080,
                        'format_note': 'MP4'
                    }],
                    'extractor': info.get('extractor'),
                    'webpage_url': info.get('webpage_url', url)
                }
            
            return {
                'title': info.get('title', 'Untitled'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'formats': info.get('formats', []),
                'extractor': info.get('extractor'),
                'webpage_url': info.get('webpage_url'),
            }
    except Exception as e:
        logger.error(f"Error getting video info: {str(e)}")
        raise

def cleanup_old_files():
    """Clean up files older than CLEANUP_OLDER_THAN"""
    now = datetime.now()
    for file in DOWNLOAD_FOLDER.iterdir():
        file_time = datetime.fromtimestamp(file.stat().st_mtime)
        if (now - file_time) > CLEANUP_OLDER_THAN:
            try:
                file.unlink()
                logger.info(f"Deleted old file: {file.name}")
            except Exception as e:
                logger.error(f"Error deleting {file.name}: {str(e)}")

@app.before_first_request
def startup():
    """Initial checks when server starts"""
    logger.info(f"Download folder: {DOWNLOAD_FOLDER.absolute()}")
    logger.info(f"Download folder exists: {DOWNLOAD_FOLDER.exists()}")
    logger.info(f"Download folder writable: {os.access(DOWNLOAD_FOLDER, os.W_OK)}")
    logger.info(f"Files in download folder: {list(DOWNLOAD_FOLDER.iterdir())}")

# Routes
@app.route('/api/info', methods=['GET'])
def video_info():
    url = request.args.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'URL is required'}), 400
    
    try:
        info = get_video_info(url)
        return jsonify({'success': True, 'data': info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    format_id = data.get('format_id', 'best')
    
    if not url:
        return jsonify({'success': False, 'error': 'URL is required'}), 400
    
    try:
        # Get video info first
        info = get_video_info(url)
        safe_title = sanitize_filename(info['title'])
        filename = f"{safe_title}_{str(uuid.uuid4())[:8]}.mp4"  # Force .mp4 extension
        filepath = DOWNLOAD_FOLDER / filename
        
        ydl_opts = {
            'format': format_id,
            'outtmpl': str(filepath.with_suffix('')),  # Remove extension as yt-dlp will add it
            'quiet': False,
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'ignoreerrors': True,
            'extractor_args': {
                'youtube': {'skip': ['dash', 'hls']},
                'instagram': {'extract_flat': True},
                'facebook': {'extract_flat': True}
            }
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Verify the file exists with our exact filename
        if not filepath.exists():
            # Fallback: find any file with our base name
            downloaded_files = list(DOWNLOAD_FOLDER.glob(f"{filepath.stem}*"))
            if downloaded_files:
                filepath = downloaded_files[0]
                # Rename to ensure .mp4 extension
                if filepath.suffix.lower() != '.mp4':
                    new_path = filepath.with_suffix('.mp4')
                    filepath.rename(new_path)
                    filepath = new_path
                filename = filepath.name
            else:
                raise FileNotFoundError("Downloaded file not found")
        
        logger.info(f"Successfully downloaded: {filename}")
            
        return jsonify({
            'success': True,
            'message': 'Download complete',
            'filename': filename,
            'download_url': f'/api/downloads/{quote(filename)}',
        })
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/downloads/<path:filename>', methods=['GET'])
def download_file(filename):
    try:
        # Decode the URL-encoded filename
        decoded_filename = unquote(filename)
        
        # Security check
        if not re.match(r'^[\w\s\-\.#]+$', decoded_filename):
            logger.error(f"Invalid filename pattern: {decoded_filename}")
            return jsonify({'success': False, 'error': 'Invalid filename'}), 400
            
        file_path = DOWNLOAD_FOLDER / decoded_filename
        
        # Additional security check
        try:
            file_path.resolve().relative_to(DOWNLOAD_FOLDER.resolve())
        except ValueError:
            logger.error(f"Path traversal attempt: {decoded_filename}")
            return jsonify({'success': False, 'error': 'Invalid filename'}), 400
        
        if not file_path.exists():
            logger.error(f"File not found: {decoded_filename}")
            return jsonify({'success': False, 'error': 'File not found'}), 404
            
        if file_path.stat().st_size == 0:
            logger.error(f"Empty file: {decoded_filename}")
            return jsonify({'success': False, 'error': 'File is empty'}), 500
            
        return send_file(
            file_path,
            as_attachment=True,
            download_name=decoded_filename,
            mimetype='video/mp4'
        )
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/whatsapp', methods=['GET'])
def whatsapp_links():
    return jsonify({
        'success': True,
        'channel': os.getenv('WHATSAPP_CHANNEL', 'https://whatsapp.com/channel/0029VayK4ty7DAWr0jeCZx0i'),
        'group': os.getenv('WHATSAPP_GROUP', 'https://chat.whatsapp.com/FAJjIZY3a09Ck73ydqMs4E')
    })

# Serve React frontend
@app.route('/')
def serve_frontend():
    return app.send_static_file('index.html')

@app.errorhandler(404)
def not_found(e):
    return app.send_static_file('index.html')

# Scheduled tasks
@scheduler.task('interval', id='cleanup_job', hours=1)
def cleanup_job():
    cleanup_old_files()

if __name__ == '__main__':
    # Use this for production
    from waitress import serve
    logger.info("Starting server...")
    serve(app, host="0.0.0.0", port=5000)