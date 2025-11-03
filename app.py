# app.py – Flask web version (NO GUI, NO tkinter)
import os
import struct
import subprocess
import re
from flask import Flask, render_template, request, jsonify, send_file, abort
from werkzeug.utils import secure_filename
from pathlib import Path

# ------------------- CONFIG -------------------
UPLOAD_FOLDER = "uploads"
RESULT_FOLDER = "results"
FFMPEG_BIN = "./ffmpeg/bin"
FFPROBE_PATH = os.path.join(FFMPEG_BIN, "ffprobe")

# DEBUG – check ffprobe
print(f"FFPROBE_PATH: {FFPROBE_PATH}")
print(f"Exists: {os.path.exists(FFPROBE_PATH)}")
print(f"Executable: {os.access(FFPROBE_PATH, os.X_OK) if os.path.exists(FFPROBE_PATH) else False}")
# ---------------------------------------------

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["RESULT_FOLDER"] = RESULT_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

Path(UPLOAD_FOLDER).mkdir(exist_ok=True)
Path(RESULT_FOLDER).mkdir(exist_ok=True)


def allowed_file(filename: str) -> bool:
    return filename.lower().endswith('.mp4')


def detect_original_fps(filepath: str):
    try:
        result = subprocess.run(
            [FFPROBE_PATH, "-v", "0", "-of", "csv=p=0",
             "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", filepath],
            capture_output=True, text=True, check=True
        )
        fps_text = result.stdout.strip()
        if '/' in fps_text:
            n, d = fps_text.split('/')
            return float(n) / float(d)
        return float(fps_text)
    except Exception as e:
        print("ffprobe error:", e)
        return None


def patch_atom(data: bytearray, atom_name: bytes, scale_factor: float):
    count = start = 0
    while True:
        found = data.find(atom_name, start)
        if found == -1:
            break
        size_offset = found - 4
        if size_offset < 0:
            start = found + len(atom_name)
            continue
        ts_off = found + 12
        dur_off = found + 16
        if scale_factor:
            ts = struct.unpack(">I", data[ts_off:ts_off+4])[0]
            dur = struct.unpack(">I", data[dur_off:dur_off+4])[0]
            data[ts_off:ts_off+4] = struct.pack(">I", int(ts * scale_factor))
            data[dur_off:dur_off+4] = struct.pack(">I", int(dur * scale_factor))
        count += 1
        start = found + len(atom_name)
    return count


def patch_mp4(in_path: str, out_path: str, scale: float):
    with open(in_path, "rb") as f:
        data = bytearray(f.read())
    patch_atom(data, b"mvhd", scale)
    patch_atom(data, b"mdhd", scale)
    with open(out_path, "wb") as f:
        f.write(data)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify(error="No file"), 400
    file = request.files["file"]
    fps_str = request.form.get("fps", "").strip()
    if not fps_str or not file or not allowed_file(file.filename):
        return jsonify(error="Invalid input"), 400

    try:
        desired_fps = float(re.sub(r"[^0-9.]", "", fps_str))
        if desired_fps <= 0:
            raise ValueError
    except Exception:
        return jsonify(error="Invalid FPS"), 400

    safe_name = secure_filename(file.filename)
    in_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    out_path = os.path.join(app.config["RESULT_FOLDER"], "patched_" + safe_name)
    file.save(in_path)

    orig_fps = detect_original_fps(in_path)
    if orig_fps is None:
        os.remove(in_path)
        return jsonify(error="Could not detect original FPS"), 500

    scale = orig_fps / desired_fps
    patch_mp4(in_path, out_path, scale)
    os.remove(in_path)

    return jsonify(
        success=True,
        download_url=f"/download/{os.path.basename(out_path)}",
        info=f"Original FPS: {orig_fps:.3f} to {desired_fps} FPS (scale {scale:.3f})"
    )


@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(app.config["RESULT_FOLDER"], filename)
    if not os.path.exists(path):
        abort(404)
    resp = send_file(path, as_attachment=True)
    @resp.call_on_close
    def cleanup():
        try:
            os.remove(path)
        except Exception:
            pass
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
