import os
from flask import Flask, request, jsonify, send_file, Response
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
from functools import lru_cache
import time
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from contextlib import contextmanager
import hashlib

# Load environment variables
load_dotenv()

# Initialize Flask app with optimized settings
app = Flask(__name__, static_folder='../frontend/build', static_url_path='/')
app.config.update({
    'MAX_CONTENT_LENGTH': 500 * 1024 * 1024,  # 500MB
    'SEND_FILE_MAX_AGE_DEFAULT': 3600,  # 1 hour cache
    'JSONIFY_PRETTYPRINT_REGULAR': False,
    'JSON_SORT_KEYS': False,
})

# Configure CORS with pre-compiled regex for faster matching
CORS(app, resources={
    r"/api/.*": {
        "origins": [
            "https://pracky.vercel.app",
            "http://localhost:3000"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"],
        "supports_credentials": True,
        "max_age": 600  # 10 minute preflight cache
    }
})

# Configuration
DOWNLOAD_FOLDER = Path(os.getenv('DOWNLOAD_FOLDER', 'downloads'))
DOWNLOAD_FOLDER.mkdir(exist_ok=True, parents=True)
MAX_FILENAME_LENGTH = 100
CLEANUP_OLDER_THAN = timedelta(hours=24)
MAX_CONCURRENT_DOWNLOADS = 4

# Thread pool for downloads
DOWNLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS)

# Database for tracking downloads
DB_PATH = Path('downloads.db')
init_db_called = False

# Setup optimized logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('server.log')
    ]
)
logger = logging.getLogger("PrackyDownloader")
logger.setLevel(logging.INFO)

# Pre-compile regex patterns for faster matching
FILENAME_SANITIZE_PATTERN = re.compile(r'[\\/*?:"<>|]')
FILENAME_VALIDATE_PATTERN = re.compile(r'^[\w\s\-\.#]+$')
URL_HASH_PATTERN = re.compile(r'^[a-f0-9]{32}$')

# Initialize scheduler
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Database functions
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    global init_db_called
    if not init_db_called:
        with get_db() as conn:
            conn.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id TEXT PRIMARY KEY,
                filename TEXT,
                url TEXT,
                url_hash TEXT,
                status TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                filesize INTEGER,
                ip_address TEXT
            )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_url_hash ON downloads(url_hash)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON downloads(status)')
            conn.commit()
        init_db_called = True

def record_download_start(download_id, filename, url, ip_address):
    url_hash = hashlib.md5(url.encode()).hexdigest()
    with get_db() as conn:
        conn.execute(
            'INSERT INTO downloads (id, filename, url, url_hash, status, ip_address) VALUES (?, ?, ?, ?, ?, ?)',
            (download_id, filename, url, url_hash, 'started', ip_address)
        )
        conn.commit()

def record_download_complete(download_id, filesize):
    with get_db() as conn:
        conn.execute(
            'UPDATE downloads SET status = ?, completed_at = CURRENT_TIMESTAMP, filesize = ? WHERE id = ?',
            ('completed', filesize, download_id)
        )
        conn.commit()

def check_existing_download(url):
    url_hash = hashlib.md5(url.encode()).hexdigest()
    with get_db() as conn:
        row = conn.execute(
            'SELECT filename FROM downloads WHERE url_hash = ? AND status = ? ORDER BY completed_at DESC LIMIT 1',
            (url_hash, 'completed')
        ).fetchone()
        return row['filename'] if row else None

# Optimized helper functions
def sanitize_filename(filename):
    """Ultra-fast filename sanitization"""
    if not filename:
        return "untitled"
    filename = FILENAME_SANITIZE_PATTERN.sub("_", filename)
    if len(filename) > MAX_FILENAME_LENGTH:
        return filename[:MAX_FILENAME_LENGTH]
    return filename

@lru_cache(maxsize=512)
def get_video_info_cached(url, cache_key):
    """Highly optimized video info fetcher with aggressive caching"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'extract_flat': False,
        'ignoreerrors': True,
        'noplaylist': True,
        'socket_timeout': 8,
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls', 'translated_subs'],
                'player_skip': ['js'],
                'player_client': ['android']
            },
            'instagram': {'extract_flat': True},
            'facebook': {'extract_flat': True}
        },
        'force_ipv4': True,
        'geo_bypass': True,
        'geo_bypass_country': 'US'
    }
    
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise ValueError("No video information could be extracted")
                
            # Platform-specific optimizations
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
    """Fast cleanup with batch processing"""
    now = datetime.now()
    try:
        with get_db() as conn:
            # Get files to delete
            old_files = conn.execute('''
                SELECT filename FROM downloads 
                WHERE completed_at < ? 
                AND status = 'completed'
            ''', (now - CLEANUP_OLDER_THAN,)).fetchall()
            
            # Delete files in batch
            deleted = 0
            for file in old_files:
                try:
                    file_path = DOWNLOAD_FOLDER / file['filename']
                    if file_path.exists():
                        file_path.unlink()
                        deleted += 1
                except Exception as e:
                    logger.error(f"Error deleting {file['filename']}: {str(e)}")
            
            # Update database
            conn.execute('''
                DELETE FROM downloads 
                WHERE completed_at < ? 
                AND status = 'completed'
            ''', (now - CLEANUP_OLDER_THAN,))
            conn.commit()
            
            logger.info(f"Cleaned up {deleted} old files")
    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")

# Optimized routes
@app.route('/api/info', methods=['GET'])
def video_info():
    url = request.args.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'URL is required'}), 400
    
    try:
        # Check cache first
        cache_key = int(time.time() / 60)  # Cache for 1 minute
        info = get_video_info_cached(url, cache_key)
        
        # Check if we already have this file
        existing_file = check_existing_download(url)
        if existing_file:
            info['cached'] = True
            info['download_url'] = f'/api/downloads/{quote(existing_file)}'
        
        return jsonify({
            'success': True, 
            'data': info,
            'cached': existing_file is not None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    format_id = data.get('format_id', 'best')
    ip_address = request.remote_addr
    
    if not url:
        return jsonify({'success': False, 'error': 'URL is required'}), 400
    
    try:
        # Check if we already have this file
        existing_file = check_existing_download(url)
        if existing_file:
            return jsonify({
                'success': True,
                'message': 'File already exists',
                'filename': existing_file,
                'download_url': f'/api/downloads/{quote(existing_file)}',
                'cached': True
            })
        
        # Get video info
        cache_key = int(time.time() / 60)
        info = get_video_info_cached(url, cache_key)
        safe_title = sanitize_filename(info['title'])
        download_id = str(uuid.uuid4())
        filename = f"{safe_title}_{download_id[:8]}.mp4"
        filepath = DOWNLOAD_FOLDER / filename
        
        # Record download start
        record_download_start(download_id, filename, url, ip_address)
        
        # Submit download task
        DOWNLOAD_EXECUTOR.submit(
            download_task, 
            url, 
            format_id, 
            filepath, 
            download_id
        )
        
        return jsonify({
            'success': True,
            'message': 'Download started',
            'filename': filename,
            'download_url': f'/api/downloads/{quote(filename)}',
            'download_id': download_id
        })
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

def download_task(url, format_id, filepath, download_id):
    """Optimized download task with progress tracking"""
    try:
        ydl_opts = {
            'format': format_id,
            'outtmpl': str(filepath.with_suffix('')),
            'quiet': True,
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
            },
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': True,
            'http_chunk_size': 1048576,  # 1MB chunks for faster downloads
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Handle the downloaded file
        if not filepath.exists():
            downloaded_files = list(DOWNLOAD_FOLDER.glob(f"{filepath.stem}*"))
            if downloaded_files:
                filepath = downloaded_files[0]
                if filepath.suffix.lower() != '.mp4':
                    new_path = filepath.with_suffix('.mp4')
                    filepath.rename(new_path)
                    filepath = new_path
        
        # Record completion
        if filepath.exists():
            record_download_complete(download_id, filepath.stat().st_size)
            logger.info(f"Successfully downloaded: {filepath.name}")
        else:
            logger.error(f"Download failed - file not created: {filepath.name}")
    except Exception as e:
        logger.error(f"Download task failed: {str(e)}")

@app.route('/api/downloads/<path:filename>', methods=['GET'])
def download_file(filename):
    try:
        decoded_filename = unquote(filename)
        
        # Ultra-fast validation
        if not FILENAME_VALIDATE_PATTERN.match(decoded_filename):
            logger.error(f"Invalid filename: {decoded_filename}")
            return jsonify({'success': False, 'error': 'Invalid filename'}), 400
            
        file_path = DOWNLOAD_FOLDER / decoded_filename
        
        # Security check
        try:
            file_path.resolve().relative_to(DOWNLOAD_FOLDER.resolve())
        except ValueError:
            logger.error(f"Path traversal attempt: {decoded_filename}")
            return jsonify({'success': False, 'error': 'Invalid filename'}), 400
        
        if not file_path.exists():
            logger.error(f"File not found: {decoded_filename}")
            return jsonify({'success': False, 'error': 'File not found'}), 404
            
        filesize = file_path.stat().st_size
        if filesize == 0:
            logger.error(f"Empty file: {decoded_filename}")
            return jsonify({'success': False, 'error': 'File is empty'}), 500
            
        # Use efficient file serving
        response = Response()
        response.headers['Content-Type'] = 'video/mp4'
        response.headers['Content-Disposition'] = f'attachment; filename="{decoded_filename}"'
        response.headers['Content-Length'] = filesize
        
        if 'USE_X_SENDFILE' in os.environ:
            response.headers['X-Sendfile'] = str(file_path.absolute())
        else:
            response = send_file(
                file_path,
                as_attachment=True,
                download_name=decoded_filename,
                mimetype='video/mp4',
                conditional=True
            )
            
        return response
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/status/<download_id>', methods=['GET'])
def download_status(download_id):
    try:
        with get_db() as conn:
            download = conn.execute(
                'SELECT status, filename FROM downloads WHERE id = ?',
                (download_id,)
            ).fetchone()
            
            if not download:
                return jsonify({'success': False, 'error': 'Download not found'}), 404
                
            return jsonify({
                'success': True,
                'status': download['status'],
                'filename': download['filename'],
                'download_url': f"/api/downloads/{quote(download['filename'])}" if download['status'] == 'completed' else None
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Startup optimizations
# Replace the @app.before_first_request decorator with this:

@app.before_request
def startup():
    """Initial checks when server starts"""
    if not hasattr(app, 'has_run_startup'):
        logger.info(f"Download folder: {DOWNLOAD_FOLDER.absolute()}")
        logger.info(f"Download folder exists: {DOWNLOAD_FOLDER.exists()}")
        logger.info(f"Download folder writable: {os.access(DOWNLOAD_FOLDER, os.W_OK)}")
        logger.info(f"Files in download folder: {list(DOWNLOAD_FOLDER.iterdir())}")
        init_db()
        cleanup_old_files()
        app.has_run_startup = True

# Scheduled tasks
@scheduler.task('interval', id='cleanup_job', hours=1)
def cleanup_job():
    cleanup_old_files()

if __name__ == '__main__':
    # Production server with optimized settings
    from waitress import serve
    serve(
        app,
        host="0.0.0.0",
        port=5000,
        threads=8,  # Increased thread pool
        channel_timeout=60,
        connection_limit=1000
    )