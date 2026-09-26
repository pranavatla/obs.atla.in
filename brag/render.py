"""Render scene.html into an 11-second 1080p MP4, one deterministic frame at a time.

    pip install playwright imageio-ffmpeg
    python brag/render.py [--chromium /path/to/chrome]
"""
import argparse, pathlib, subprocess
import imageio_ffmpeg
from playwright.sync_api import sync_playwright

FPS, DUR = 30, 11
HERE = pathlib.Path(__file__).resolve().parent

ap = argparse.ArgumentParser()
ap.add_argument("--chromium", help="Chromium executable, if Playwright's bundled one is missing")
args = ap.parse_args()

out = HERE / "obs-atla-in-brag.mp4"
proc = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "image2pipe", "-framerate", str(FPS),
    "-c:v", "png", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
    "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.chromium)
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.goto((HERE / "scene.html").as_uri())
    for i in range(FPS * DUR):
        page.evaluate(f"render({i / FPS})")
        proc.stdin.write(page.screenshot(type="png"))
    browser.close()
proc.stdin.close()
proc.wait()
print(out)
