from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

SUPPORTED_DOMAINS = [
    "youtube.com", "youtu.be",
    "facebook.com", "fb.watch",
    "instagram.com",
    "tiktok.com",
    "twitter.com", "x.com",
    "vimeo.com",
    "dailymotion.com"
]

def is_valid_url(url):
    return any(domain in url for domain in SUPPORTED_DOMAINS)

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/")
def index():
    return jsonify({"status": "VidGrab API running"})

@app.route("/fetch", methods=["GET"])
def fetch_video():
    url = request.args.get("url", "").strip()

    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400

    if not is_valid_url(url):
        return jsonify({"success": False, "error": "Unsupported platform"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title", "Video")
        thumbnail = info.get("thumbnail", "")
        duration = info.get("duration", 0)
        uploader = info.get("uploader", "")

        formats = []
        seen = set()

        raw_formats = info.get("formats", [])

        for f in raw_formats:
            furl = f.get("url", "")
            ext = f.get("ext", "mp4")
            height = f.get("height")
            acodec = f.get("acodec", "none")
            vcodec = f.get("vcodec", "none")
            filesize = f.get("filesize") or f.get("filesize_approx")

            if not furl or furl in seen:
                continue

            if vcodec != "none" and height:
                quality = f"{height}p"
                label = f"{height}p"
                if height >= 1080:
                    label = f"{height}p HD"
                elif height >= 720:
                    label = f"{height}p HD"
            elif vcodec == "none" and acodec != "none":
                quality = "audio"
                label = "Audio only"
                ext = f.get("ext", "m4a")
            else:
                continue

            key = f"{quality}-{ext}"
            if key in seen:
                continue
            seen.add(key)
            seen.add(furl)

            size_str = ""
            if filesize:
                mb = filesize / (1024 * 1024)
                size_str = f"{mb:.1f} MB"

            formats.append({
                "quality": label,
                "ext": ext,
                "url": furl,
                "size": size_str,
                "height": height or 0
            })

        formats.sort(key=lambda x: x["height"], reverse=True)

        if not formats:
            return jsonify({"success": False, "error": "No downloadable formats found"}), 404

        mins = int(duration // 60) if duration else 0
        secs = int(duration % 60) if duration else 0
        duration_str = f"{mins}:{secs:02d}" if duration else ""

        return jsonify({
            "success": True,
            "title": title,
            "thumbnail": thumbnail,
            "uploader": uploader,
            "duration": duration_str,
            "formats": formats
        })

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "Private" in msg or "private" in msg:
            return jsonify({"success": False, "error": "This video is private"}), 403
        if "age" in msg.lower():
            return jsonify({"success": False, "error": "Age-restricted video"}), 403
        return jsonify({"success": False, "error": "Could not fetch video. It may be unavailable."}), 400
    except Exception as e:
        return jsonify({"success": False, "error": "Something went wrong. Try again."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
