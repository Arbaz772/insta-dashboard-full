#!/usr/bin/env python3
"""
instagram_hourly_jokes.py

Now includes a safety/alert system:
 - Detects Instagram "feedback_required" / challenge responses and stops the bot immediately.
 - Writes a debug file to outputs/instagram_block_debug.txt.
 - Optional SMTP email alerts (configure via env vars) using TLS.
 - All previous functionality retained (image/video rendering, ffmpeg transcode, audio attach, ffprobe diagnostics).

Set env to enable email alerts:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_EMAIL_FROM, ALERT_EMAIL_TO

The script will call handle_block_and_notify() on block detection which will save debug info and optionally email you, then exit.
"""

import os
import time
import json
import logging
import hashlib
import math
import random
import subprocess
import shutil
import tempfile
import smtplib
from email.message import EmailMessage
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    import moviepy.editor as mpy
    from moviepy.editor import ImageSequenceClip, AudioFileClip, concatenate_audioclips
    import numpy as np
    MOVIEPY_AVAILABLE = True
except Exception:
    MOVIEPY_AVAILABLE = False

from instagrapi import Client
from dotenv import load_dotenv

load_dotenv()

# ---- Config ----
IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
POST_INTERVAL = int(os.getenv("POST_INTERVAL_SECONDS", "3600"))
IMAGE_WIDTH, IMAGE_HEIGHT = 1080, 1080
FONT_PATH = os.getenv("FONT_PATH", "") or None
FONT_SIZE, MIN_FONT_SIZE = 44, 18
BACKGROUND_COLOR = (10, 12, 18)
TEXT_COLOR = (165, 255, 170)
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")
POST_VIDEO = os.getenv("POST_VIDEO", "false").lower() in ("1", "true", "yes")
AUDIO_FILE = os.getenv("AUDIO_FILE", "assets/futuristic.wav")

# SMTP alerting configuration (optional)
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO")

SEEN_CACHE_FILE = os.path.join(OUTPUT_DIR, "seen_jokes.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("insta-hourly-jokes")

FFMPEG_BIN = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "/usr/bin/ffprobe"

# ---- Utility helpers ----

def stable_key(text):
    return hashlib.sha256((text or "").strip().lower().encode()).hexdigest()


def load_seen():
    try:
        if os.path.exists(SEEN_CACHE_FILE):
            with open(SEEN_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception:
        logger.debug("Failed to load seen cache")
    return []


def save_seen(seen):
    try:
        tmp = SEEN_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(seen[-500:], f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, SEEN_CACHE_FILE)
    except Exception as e:
        logger.debug("Failed to save seen cache: %s", e)

# ---- Curated jokes ----
JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "Debugging: being the detective in a crime movie where you are also the murderer.",
    "There are only 10 types of people: those who understand binary and those who don’t.",
    "I would tell you a UDP joke, but you might not get it.",
    "Why do Java developers wear glasses? Because they don’t C#.",
    "A SQL query walks into a bar and sees two tables. He asks: Can I join you?",
    "To understand recursion, you must first understand recursion.",
    "If at first you don’t succeed, call it version 1.0.",
    "Why did the developer go broke? Because he used up all his cache.",
    "It works on my machine. Famous last words of engineers everywhere.",
]

# ---- Rendering helpers ----
def futuristic_background():
    base = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(base)
    for i in range(0, max(IMAGE_WIDTH, IMAGE_HEIGHT), 12):
        color = (int(6 + (i/100) % 200), int(12 + (i/60) % 180), int(30 + (i/30) % 220))
        draw.ellipse([IMAGE_WIDTH//2 - i, IMAGE_HEIGHT//2 - int(i*0.6), IMAGE_WIDTH//2 + i, IMAGE_HEIGHT//2 + int(i*0.6)], outline=color)
    return base.filter(ImageFilter.GaussianBlur(24))


def _text_bbox_size(draw, text, font):
    try:
        bbox = draw.textbbox((0,0), text, font=font)
        return bbox[2]-bbox[0], bbox[3]-bbox[1]
    except Exception:
        try:
            return draw.textsize(text, font=font)
        except Exception:
            return len(text)*7, FONT_SIZE


def wrap_text(draw, text, font, max_w):
    words = text.split()
    if not words:
        return [""]
    lines = []
    cur = words[0]
    for w in words[1:]:
        test = cur + " " + w
        tw, _ = _text_bbox_size(draw, test, font)
        if tw <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines

# ---- Image render ----
def render_image(text, out_path):
    img = futuristic_background()
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH or "DejaVuSansMono.ttf", FONT_SIZE)
    except Exception:
        font = ImageFont.load_default()

    pad_x, pad_y = 80, 120
    inner_w = IMAGE_WIDTH - pad_x*2
    cur_size = getattr(font, 'size', FONT_SIZE)
    while True:
        try:
            f = ImageFont.truetype(FONT_PATH or "DejaVuSansMono.ttf", cur_size)
        except Exception:
            f = ImageFont.load_default()
        lines = []
        for p in text.split('\n'):
            lines.extend(wrap_text(draw, p.strip(), f, inner_w - 40))
        _, line_h = _text_bbox_size(draw, 'Ay', f)
        if line_h * len(lines) <= (IMAGE_HEIGHT - pad_y*2) or cur_size <= MIN_FONT_SIZE:
            font = f
            break
        cur_size = max(MIN_FONT_SIZE, cur_size - 2)

    lines = []
    for p in text.split('\n'):
        lines.extend(wrap_text(draw, p.strip(), font, inner_w - 40))

    y = 140
    for i, line in enumerate(lines):
        draw.text((pad_x, y + i * (getattr(font, 'size', FONT_SIZE) + 6)), "$ " + line, font=font, fill=TEXT_COLOR)

    try:
        hfont = ImageFont.truetype("DejaVuSans.ttf", 16)
    except Exception:
        hfont = ImageFont.load_default()
    draw.text((pad_x, pad_y - 40), "404CodeChugger", font=hfont, fill=(180,200,220))

    img.save(out_path, quality=92)
    return out_path

# ---- Video render ----
def render_video(text, out_path_mp4, fps=24, max_duration=12):
    if not MOVIEPY_AVAILABLE:
        logger.warning("moviepy missing — falling back to image")
        return render_image(text, out_path_mp4.rsplit('.',1)[0] + '.jpg')

    base = futuristic_background()
    try:
        font = ImageFont.truetype(FONT_PATH or "DejaVuSansMono.ttf", 36)
    except Exception:
        font = ImageFont.load_default()

    draw_tmp = ImageDraw.Draw(base)
    lines = []
    for p in text.split('\n'):
        lines.extend(wrap_text(draw_tmp, p.strip(), font, IMAGE_WIDTH - 160))
    full_text = '\n'.join(lines)
    total_chars = max(1, len(full_text))

    duration = min(max(3, total_chars / 12.0), max_duration)
    total_frames = int(fps * duration)

    frames = []
    for i in range(total_frames):
        p = i / max(1, total_frames - 1)
        typed = int(total_chars * (p ** 1.05))
        visible = full_text[:typed]
        fr = base.copy()
        fd = ImageDraw.Draw(fr)
        vlines = visible.split('\n') if visible else ['']
        _, line_h = _text_bbox_size(fd, 'Ay', font)
        start_y = 140
        for li, ln in enumerate(vlines):
            prompt = "$ "
            fd.text((80, start_y + li*line_h), prompt, font=font, fill=(140,150,165))
            pw, _ = _text_bbox_size(fd, prompt, font)
            fd.text((80 + pw, start_y + li*line_h), ln, font=font, fill=TEXT_COLOR)
        blink_on = (i // max(1, (fps//2))) % 2 == 0
        if blink_on:
            last = vlines[-1]
            cw, ch = _text_bbox_size(fd, last, font)
            cx = 80 + pw + cw + 4
            cy = start_y + (len(vlines)-1)*line_h
            fd.rectangle([cx, cy + int(line_h*0.15), cx+8, cy + int(line_h*0.85)], fill=(200,230,200))
        frames.append(np.array(fr.convert('RGB'), dtype=np.uint8))

    clip = ImageSequenceClip(frames, fps=fps)

    if AUDIO_FILE and os.path.exists(AUDIO_FILE):
        try:
            audio = AudioFileClip(AUDIO_FILE)
            if audio.duration < clip.duration:
                n = math.ceil(clip.duration / audio.duration)
                audio = concatenate_audioclips([audio] * n)
            audio = audio.subclip(0, clip.duration).volumex(0.45)
            clip = clip.set_audio(audio)
            logger.info("Attached audio: %s", AUDIO_FILE)
        except Exception as e:
            logger.warning("Failed to attach audio: %s", e)

    tmp_out = out_path_mp4 + ".tmp.mp4"
    out_dir = os.path.dirname(out_path_mp4)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    clip.write_videofile(tmp_out, codec='libx264', audio_codec='aac', threads=0, verbose=False, logger=None)

    final = ensure_instagram_video_compatible_v2(tmp_out, out_path_mp4, target_width=IMAGE_WIDTH, target_height=IMAGE_HEIGHT, fps=30)
    try:
        if os.path.exists(tmp_out) and tmp_out != final:
            os.remove(tmp_out)
    except Exception:
        pass
    return final

# ---- ffprobe inspector ----
def ffprobe_inspect(path):
    if not os.path.exists(FFPROBE_BIN):
        logger.warning('ffprobe not found, skipping inspect')
        return None
    cmd = [FFPROBE_BIN, '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', path]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=20)
        info = json.loads(p.stdout.decode('utf-8', errors='ignore') or '{}')
        logger.info('ffprobe format for %s: %s', path, json.dumps(info.get('format', {}), indent=2)[:2000])
        for s in info.get('streams', []):
            logger.info('stream idx=%s codec=%s pix_fmt=%s width=%s height=%s r_frame_rate=%s', s.get('index'), s.get('codec_name'), s.get('pix_fmt'), s.get('width'), s.get('height'), s.get('r_frame_rate'))
        return info
    except Exception as e:
        logger.warning('ffprobe failed: %s', e)
        return None

# ---- improved transcoder (v2) ----
def ensure_instagram_video_compatible_v2(in_path, out_path=None, target_width=1080, target_height=1080, fps=30, crf=23, audio_bitrate='128k', try_strip_audio=False):
    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix='.mp4', dir=os.path.dirname(in_path) or '.')
        os.close(fd)
    if not os.path.exists(FFMPEG_BIN):
        logger.warning('ffmpeg not found, skipping transcode')
        return in_path

    vf = ("scale='if(gt(a,{w}/{h}),{w},-2)':'if(gt(a,{w}/{h}),-2,{h})',pad=ceil(iw/2)*2:ceil(ih/2)*2").format(w=target_width, h=target_height)
    cmd_base = [FFMPEG_BIN, '-y', '-i', in_path, '-c:v', 'libx264', '-preset', 'veryfast']
    cmd_base += ['-profile:v', 'baseline', '-level', '3.1', '-crf', str(crf), '-r', str(fps), '-vf', vf, '-pix_fmt', 'yuv420p']
    if try_strip_audio:
        cmd = cmd_base + ['-an', '-movflags', '+faststart', out_path]
    else:
        cmd = cmd_base + ['-c:a', 'aac', '-b:a', audio_bitrate, '-movflags', '+faststart', out_path]
    logger.info('Running ffmpeg transcode (compat v2): %s', ' '.join(cmd[:6]) + ' ...')
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=240)
        logger.debug('ffmpeg stderr: %s', p.stderr.decode(errors='ignore')[:2000])
        ffprobe_inspect(out_path)
        return out_path
    except subprocess.CalledProcessError as e:
        logger.warning('ffmpeg first-pass failed: rc=%s, stderr=%s', e.returncode, e.stderr.decode(errors='ignore')[:2000])
        if not try_strip_audio:
            logger.info('Retrying by stripping audio for compatibility')
            return ensure_instagram_video_compatible_v2(in_path, out_path, target_width, target_height, fps, crf, audio_bitrate, try_strip_audio=True)
        return in_path
    except subprocess.TimeoutExpired:
        logger.error('ffmpeg transcode timed out')
        return in_path

# ---- alerting helpers ----
def send_email_alert(subject, body):
    """Send a short email alert using configured SMTP (optional)."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS or not ALERT_EMAIL_TO or not ALERT_EMAIL_FROM:
        logger.debug('SMTP not configured; skipping email alert')
        return False
    try:
        msg = EmailMessage()
        msg['From'] = ALERT_EMAIL_FROM
        msg['To'] = ALERT_EMAIL_TO
        msg['Subject'] = subject
        msg.set_content(body)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        logger.info('Sent alert email to %s', ALERT_EMAIL_TO)
        return True
    except Exception as e:
        logger.warning('Failed to send alert email: %s', e)
        return False


def handle_block_and_notify(exc):
    """Write debug info and optionally email, then stop the process."""
    now = datetime.utcnow().isoformat()
    debug_path = os.path.join(OUTPUT_DIR, 'instagram_block_debug.txt')
    try:
        with open(debug_path, 'a', encoding='utf-8') as f:
            f.write(f"[{now}] BLOCK DETECTED: {repr(exc)}\n")
    except Exception:
        logger.exception('Failed to write debug file')

    # attempt to send email
    subject = f"Instagram bot blocked for account {IG_USERNAME}"
    body = f"Block detected at {now}. Exception: {repr(exc)}\n\nCheck outputs/instagram_block_debug.txt for details."
    send_email_alert(subject, body)

    logger.error('Detected Instagram block; stopping bot. See %s', debug_path)
    raise SystemExit('Instagram restricted posting - manual intervention required')

# ---- safe upload wrapper ----
def safe_video_upload(client, path, caption):
    try:
        return client.video_upload(path, caption)
    except Exception as e:
        # better attempt to find response
        resp = None
        try:
            if hasattr(e, 'response') and e.response is not None:
                resp = e.response
            elif hasattr(e, 'args') and len(e.args) > 0:
                arg0 = e.args[0]
                resp = getattr(arg0, 'response', None) if hasattr(arg0, 'response') else None
            if resp is not None:
                body = getattr(resp, 'text', None)
                logger.error('Instagram response status=%s body=%s', getattr(resp, 'status_code', None), body[:4000] if body else body)
                if body and ('feedback_required' in body or 'challenge_required' in body or 'restricted' in body or 'Please wait' in body):
                    handle_block_and_notify(body)
        except Exception:
            logger.exception('Error extracting response from exception')
        raise

# ---- post with retries (invokes block handler when detected) ----

def post_with_retries(client, path, caption, max_attempts=4):
    attempt = 1
    last_exc = None
    while attempt <= max_attempts:
        try:
            ext = os.path.splitext(path)[1].lower()
            upload_path = path
            if ext in ('.mp4', '.mov', '.m4v', '.avi', '.webm'):
                target = os.path.splitext(path)[0] + '.ig.mp4'
                upload_path = ensure_instagram_video_compatible_v2(path, target, target_width=IMAGE_WIDTH, target_height=IMAGE_HEIGHT, fps=30)

            logger.info('Uploading %s (attempt %s)', upload_path, attempt)
            if upload_path.lower().endswith(('.mp4', '.mov', '.m4v')):
                safe_video_upload(client, upload_path, caption)
            else:
                client.photo_upload(upload_path, caption)

            logger.info('Upload succeeded')
            try:
                if upload_path.endswith('.ig.mp4') and os.path.exists(upload_path):
                    os.remove(upload_path)
            except Exception:
                pass
            return True
        except Exception as e:
            last_exc = e
            # check raw message for block indicators
            txt = str(e).lower()
            if 'feedback_required' in txt or 'challenge_required' in txt or 'restricted' in txt or 'please wait' in txt:
                handle_block_and_notify(e)
            logger.warning('Upload attempt %s failed: %s', attempt, e)
            attempt += 1
            wait = min(300, 5 * (2 ** (attempt - 1)))
            logger.info('Backing off %s seconds', wait)
            time.sleep(wait)
    logger.error('All upload attempts failed: %s', last_exc)
    return False

# ---- Instagram login ----
def instagram_client_login(username, password):
    client = Client()
    client.login(username, password)
    return client

# ---- main loop ----
def main():
    if not IG_USERNAME or not IG_PASSWORD:
        logger.error('Missing IG credentials')
        return

    client = None
    for i in range(3):
        try:
            client = instagram_client_login(IG_USERNAME, IG_PASSWORD)
            break
        except Exception as e:
            logger.warning('Login failed: %s', e)
            time.sleep(5 * (2 ** i))
    if not client:
        logger.error('Could not login')
        return

    seen = load_seen()

    while True:
        try:
            joke = random.choice(JOKES)
            key = stable_key(joke)
            if key in seen:
                logger.info('Already posted, skipping')
                time.sleep(2)
                continue

            ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            if POST_VIDEO:
                out = os.path.join(OUTPUT_DIR, f'joke_{ts}.mp4')
                produced = render_video(joke, out)
            else:
                out = os.path.join(OUTPUT_DIR, f'joke_{ts}.jpg')
                produced = render_image(joke, out)

            caption = f"{joke}\n\n#programming #devhumor #coding"
            success = post_with_retries(client, produced, caption)
            if success:
                seen.append(key)
                save_seen(seen)
        except SystemExit:
            logger.error('Bot stopped due to Instagram block — exit')
            break
        except Exception as e:
            logger.exception('Main loop error: %s', e)

        logger.info('Sleeping %s seconds', POST_INTERVAL)
        time.sleep(POST_INTERVAL)

if __name__ == '__main__':
    logger.info('POST_VIDEO=%s MOVIEPY=%s FFMPEG=%s FFPROBE=%s SMTP=%s', POST_VIDEO, MOVIEPY_AVAILABLE, bool(os.path.exists(FFMPEG_BIN)), bool(os.path.exists(FFPROBE_BIN)), bool(SMTP_HOST))
    main()