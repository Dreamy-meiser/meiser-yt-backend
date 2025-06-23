import os
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from yt_dlp import YoutubeDL
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

DOWNLOADS_DIR = "temp_downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

def is_valid_youtube_url(url):
    domains = ['youtube.com', 'youtu.be']
    try:
        parsed = urlparse(url)
        return any(domain in parsed.netloc for domain in domains)
    except:
        return False

def cleanup_file(filename):
    try:
        if os.path.exists(filename):
            os.remove(filename)
            logger.info(f"Deleted: {filename}")
    except Exception as e:
        logger.error(f"Failed to delete {filename}: {e}")

@app.route('/search', methods=['POST'])
def search_video():
    data = request.json
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "No search query provided"}), 400

    try:
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'default_search': 'ytsearch20',
            'noplaylist': True
        }

        with YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(f"ytsearch20:{query}", download=False)
            videos = result.get('entries', [])

        formatted_videos = []
        for video in videos:
            if not video:
                continue
            formatted_videos.append({
                'id': video.get('id'),
                'title': video.get('title'),
                'url': f"https://youtu.be/{video.get('id')}",
                'duration': video.get('duration'),
                'thumbnail': video.get('thumbnails', [{}])[-1].get('url', ''),
                'channel': video.get('channel') or video.get('uploader', 'Unknown')
            })

        return jsonify(formatted_videos)

    except Exception as e:
        logger.error(f"Search failed: {str(e)}", exc_info=True)
        return jsonify({"error": "Search failed", "details": str(e)}), 500

@app.route('/info', methods=['POST'])
def get_video_info():
    data = request.json
    url = data.get("url", "").strip()
    if not url or not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL"}), 400

    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'noplaylist': True
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        for f in info.get('formats', []):
            if f.get('url') and f.get('vcodec') != 'none':
                formats.append({
                    'itag': f.get('format_id'),
                    'ext': f.get('ext'),
                    'resolution': f.get('resolution') or f.get('height', 'audio'),
                    'filesize': f.get('filesize') or 0,
                    'format_note': f.get('format_note', ''),
                    'url': f.get('url')
                })

        return jsonify({
            'id': info.get('id'),
            'title': info.get('title'),
            'url': info.get('webpage_url'),
            'duration': info.get('duration'),
            'thumbnail': info.get('thumbnail'),
            'channel': info.get('channel') or info.get('uploader', ''),
            'formats': formats
        })

    except Exception as e:
        logger.error(f"Info fetch failed: {str(e)}", exc_info=True)
        return jsonify({"error": "Could not fetch video info"}), 500

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get("url", "").strip()
    format_type = data.get("format", "mp4")
    itag = data.get("itag", None)

    if not url or not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL"}), 400

    cookies_path = os.getenv("COOKIES_FILE")

    if cookies_path:
        logger.info(f"Environment variable COOKIES_FILE is set to: {cookies_path}")
    else:
        logger.warning("Environment variable COOKIES_FILE not set.")

    if cookies_path and not os.path.exists(cookies_path):
        logger.warning(f"Cookie file not found at {cookies_path}. YouTube may require login.")

    try:
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOADS_DIR, '%(id)s.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
        }

        if cookies_path and os.path.exists(cookies_path):
            logger.info(f"Using cookies from: {cookies_path}")
            ydl_opts['cookiefile'] = cookies_path
        else:
            logger.warning("No valid cookies file found. Some downloads may fail due to bot detection.")

        if format_type == "mp3":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            })
        elif itag:
            ydl_opts['format'] = itag
        else:
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if format_type == "mp3":
                filename = os.path.splitext(filename)[0] + '.mp3'

        response = send_file(
            filename,
            as_attachment=True,
            mimetype='audio/mp3' if format_type == "mp3" else 'video/mp4',
            download_name=f"{info['title'][:50]}.{format_type}"
        )

        @response.call_on_close
        def cleanup():
            cleanup_file(filename)

        return response

    except Exception as e:
        logger.error(f"Download failed: {str(e)}", exc_info=True)
        return jsonify({"error": "Download failed", "details": str(e)}), 500

@app.route('/')
def home():
    return 'Meiser’s YT Backend Running ✅'

if __name__ == '__main__':
    for filename in os.listdir(DOWNLOADS_DIR):
        cleanup_file(os.path.join(DOWNLOADS_DIR, filename))
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
