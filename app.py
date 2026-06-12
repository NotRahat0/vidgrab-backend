from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import os, tempfile, requests

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Public Invidious instances (fallback list)
INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://invidious.privacyredirect.com",
    "https://yt.drgnz.club",
]

SUPPORTED_DOMAINS = [
    "youtube.com", "youtu.be",
    "facebook.com", "fb.watch",
    "instagram.com",
    "tiktok.com",
    "twitter.com", "x.com",
    "vimeo.com",
    "dailymotion.com"
]

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

def is_valid_url(url):
    return any(domain in url for domain in SUPPORTED_DOMAINS)

def extract_yt_id(url):
    import re
    patterns = [
        r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:embed/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def fetch_youtube_invidious(video_id):
    """Fetch YouTube info via Invidious API — no bot detection"""
    for instance in INVIDIOUS_INSTANCES:
        try:
            r = requests.get(
                f"{instance}/api/v1/videos/{video_id}",
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if r.status_code != 200:
                continue
            data = r.json()

            title = data.get("title", "Video")
            uploader = data.get("author", "")
            duration_s = data.get("lengthSeconds", 0)
            thumbnail = ""
            thumbs = data.get("videoThumbnails", [])
            for t in thumbs:
                if t.get("quality") in ("maxres", "high", "medium"):
                    thumbnail = t.get("url", "")
                    break
            if not thumbnail and thumbs:
                thumbnail = thumbs[0].get("url", "")

            formats = []
            seen = set()

            # Video formats
            for f in data.get("adaptiveFormats", []) + data.get("formatStreams", []):
                furl = f.get("url", "")
                if not furl or furl in seen:
                    continue

                container = f.get("container", "mp4")
                resolution = f.get("resolution", "")
                quality_label = f.get("qualityLabel", "")
                mime = f.get("type", "")

                if "audio" in mime and "video" not in mime:
                    label = "Audio only"
                    ext = "m4a" if "mp4" in mime else "webm"
                    height = 0
                elif resolution:
                    height = int(resolution.replace("p", "").split("x")[-1]) if "p" in resolution else 0
                    label = f"{height}p HD" if height >= 720 else f"{height}p"
                    ext = container or "mp4"
                elif quality_label:
                    label = quality_label
                    height = int(''.join(filter(str.isdigit, quality_label)) or 0)
                    ext = container or "mp4"
                else:
                    continue

                key = f"{height}-{ext}"
                if key in seen:
                    continue
                seen.add(key)
                seen.add(furl)

                formats.append({
                    "quality": label,
                    "ext": ext,
                    "url": furl,
                    "size": "",
                    "height": height
                })

            formats.sort(key=lambda x: x["height"], reverse=True)

            mins = int(duration_s // 60) if duration_s else 0
            secs = int(duration_s % 60) if duration_s else 0

            return {
                "success": True,
                "title": title,
                "thumbnail": thumbnail,
                "uploader": uploader,
                "duration": f"{mins}:{secs:02d}" if duration_s else "",
                "formats": formats
            }
        except Exception:
            continue

    return None

def fetch_with_ytdlp(url):
    """Fallback: use yt-dlp for non-YouTube platforms"""
    cookies_content = os.environ.get("YT_COOKIES", "")
    cookies_file = None
    if cookies_content:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        tmp.write(cookies_content)
        tmp.close()
        cookies_file = tmp.name

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title", "Video")
        thumbnail = info.get("thumbnail", "")
        duration = info.get("duration", 0)
        uploader = info.get("uploader", "")
        formats = []
        seen = set()

        for f in info.get("formats", []):
            furl = f.get("url", "")
            ext = f.get("ext", "mp4")
            height = f.get("height")
            acodec = f.get("acodec", "none")
            vcodec = f.get("vcodec", "none")
            filesize = f.get("filesize") or f.get("filesize_approx")

            if not furl or furl in seen:
                continue
            if vcodec != "none" and height:
                label = f"{height}p HD" if height >= 720 else f"{height}p"
            elif vcodec == "none" and acodec != "none":
                label = "Audio only"
                ext = f.get("ext", "m4a")
                height = 0
            else:
                continue

            key = f"{height}-{ext}"
            if key in seen:
                continue
            seen.add(key)
            seen.add(furl)

            size_str = f"{filesize/(1024*1024):.1f} MB" if filesize else ""
            formats.append({"quality": label, "ext": ext, "url": furl, "size": size_str, "height": height or 0})

        formats.sort(key=lambda x: x["height"], reverse=True)
        mins = int(duration // 60) if duration else 0
        secs = int(duration % 60) if duration else 0

        return {
            "success": True,
            "title": title,
            "thumbnail": thumbnail,
            "uploader": uploader,
            "duration": f"{mins}:{secs:02d}" if duration else "",
            "formats": formats
        }
    finally:
        if cookies_file and os.path.exists(cookies_file):
            os.unlink(cookies_file)

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

    is_youtube = "youtube.com" in url or "youtu.be" in url

    try:
        if is_youtube:
            video_id = extract_yt_id(url)
            if not video_id:
                return jsonify({"success": False, "error": "Invalid YouTube URL"}), 400

            result = fetch_youtube_invidious(video_id)
            if result:
                return jsonify(result)
            else:
                return jsonify({"success": False, "error": "Could not fetch YouTube video. All servers busy, try again."}), 503
        else:
            result = fetch_with_ytdlp(url)
            if result and result.get("formats"):
                return jsonify(result)
            return jsonify({"success": False, "error": "No downloadable formats found"}), 404

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "private" in msg.lower():
            return jsonify({"success": False, "error": "This video is private"}), 403
        if "age" in msg.lower():
            return jsonify({"success": False, "error": "Age-restricted video"}), 403
        return jsonify({"success": False, "error": "Could not fetch video"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": "Something went wrong. Try again."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
