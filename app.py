import os, re, glob, shutil, tempfile
from flask import Flask, request, jsonify, send_file, send_from_directory
import yt_dlp

app = Flask(__name__, static_folder="static")
URL_RE = re.compile(r"^https?://", re.I)
MAX_SECONDS = 3600

def base_opts():
    return {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 20}

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

@app.post("/api/info")
def info():
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
    if not URL_RE.match(url):
        return jsonify(error="Please paste a valid link."), 400
    try:
        with yt_dlp.YoutubeDL(base_opts()) as y:
            d = y.extract_info(url, download=False)
        if d.get("entries"):
            d = list(d["entries"])[0]
    except Exception:
        return jsonify(error="Couldn't fetch this link. It may be private, removed or unsupported."), 422
    maxh = max([f.get("height") or 0 for f in d.get("formats", [])] or [0])
    quals = [h for h in (1080, 720, 480, 360, 240) if h <= maxh]
    if maxh and not quals:
        quals = [maxh]
    return jsonify(
        title=d.get("title") or "Video",
        thumbnail=d.get("thumbnail"),
        uploader=d.get("uploader") or "",
        duration=d.get("duration") or 0,
        has_video=bool(maxh),
        qualities=quals,
    )

@app.get("/api/download")
def download():
    url = request.args.get("url", "").strip()
    q = request.args.get("q", "best")
    if not URL_RE.match(url):
        return jsonify(error="Invalid link."), 400
    tmp = tempfile.mkdtemp(prefix="dl_")
    o = base_opts()
    o["outtmpl"] = os.path.join(tmp, "%(id).60s.%(ext)s")
    o["match_filter"] = yt_dlp.utils.match_filter_func("duration < %d" % MAX_SECONDS)
    if q == "mp3":
        o["format"] = "bestaudio/best"
        o["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        h = int(q) if q.isdigit() else 1080
        o["format"] = ("bestvideo[height<=%d]+bestaudio/best[height<=%d]/best" % (h, h))
        o["merge_output_format"] = "mp4"
    try:
        with yt_dlp.YoutubeDL(o) as y:
            d = y.extract_info(url, download=True)
            if d.get("entries"):
                d = list(d["entries"])[0]
        files = glob.glob(os.path.join(tmp, "*"))
        if not files:
            raise RuntimeError("no file")
        path = max(files, key=os.path.getsize)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return jsonify(error='Download failed: ' + str(e)[:180]), 422
    title = re.sub(r'[\\/*?:"<>|]', "", d.get("title") or "video")[:80].strip() or "video"
    ext = os.path.splitext(path)[1]
    resp = send_file(path, as_attachment=True, download_name=title + ext)
    resp.call_on_close(lambda: shutil.rmtree(tmp, ignore_errors=True))
    return resp

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
