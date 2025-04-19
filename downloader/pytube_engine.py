from pytube import YouTube
import logging
import os
import subprocess

# Set up logging
log_file_path = 'app.log'
if not os.path.exists(log_file_path):
    with open(log_file_path, 'w'): pass  # Create an empty log file if it doesn't exist.

logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,  # Set to DEBUG for detailed logs or INFO for less verbosity
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def download_video_pytube(url):
    logging.info(f"Received download request for URL: {url}")

    try:
        # Initiate download process
        yt = YouTube(url)
        logging.info(f"Video title: {yt.title}")
        
        # Get the highest resolution stream
        stream = yt.streams.get_highest_resolution()

        # Ensure the videos directory exists
        video_dir = './saved/videos'
        if not os.path.exists(video_dir):
            os.makedirs(video_dir)
            logging.info(f"Created video directory: {video_dir}")
        
        # Download the video to the specified path in its original format
        temp_file_path = stream.download(output_path=video_dir)
        logging.info(f"Download successful: {yt.title}")
        
        # Define the final MP4 file path
        final_file_path = os.path.join(video_dir, f"{yt.title}.mp4")
        
        # Convert the video to MP4 using FFmpeg (if it's not already in MP4)
        if not temp_file_path.endswith('.mp4'):
            logging.info(f"Converting video to MP4 format: {yt.title}")
            convert_video_to_mp4(temp_file_path, final_file_path)
        
        logging.info(f"Conversion successful: {final_file_path}")
        
        # Remove the original file if it's not MP4
        if temp_file_path != final_file_path:
            os.remove(temp_file_path)
            logging.info(f"Removed temporary non-MP4 file: {temp_file_path}")
        
        # Return video information
        return {
            'title': yt.title,
            'url': yt.watch_url,
            'file_size': os.path.getsize(final_file_path),  # File size in bytes
            'filename': final_file_path  # Full file path of the MP4
        }
    except Exception as e:
        # Log error if something goes wrong
        logging.error(f"Error downloading video with Pytube: {str(e)}")
        raise Exception(f"Error downloading video: {str(e)}")

def convert_video_to_mp4(input_file, output_file):
    """ Convert video to MP4 format using FFmpeg """
    try:
        command = [
            'ffmpeg', 
            '-i', input_file,   # Input file
            '-c:v', 'libx264',  # Video codec (H.264 for MP4)
            '-c:a', 'aac',      # Audio codec (AAC for MP4)
            '-strict', 'experimental',  # FFmpeg flag to allow experimental features
            output_file         # Output file
        ]
        
        subprocess.run(command, check=True)  # Run the FFmpeg conversion
        logging.info(f"Video conversion to MP4 completed successfully: {output_file}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error during video conversion: {str(e)}")
        raise Exception(f"Error during video conversion: {str(e)}")
