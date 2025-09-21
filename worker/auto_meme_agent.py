# auto_meme_agent.py
import os
import time
import requests
import uuid
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
import openai

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
BACKEND_BASE = os.getenv("BACKEND_BASE", "http://localhost:3000")
SUBREDDITS = os.getenv("SUBREDDITS", "memes,dankmemes,ProgrammerHumor").split(",")
FETCH_LIMIT = int(os.getenv("FETCH_LIMIT", "25"))
MIN_UPVOTES = int(os.getenv("MIN_UPVOTES", "100"))

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

HEADERS = {"User-Agent": "InstaMemeAgent/1.0 (by your-app)"}
MAX_IMAGE_SIZE = (1080, 1080)

def fetch_reddit_images(subreddit, limit=20):
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    items = []
    data = res.json()
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        if post.get("over_18"):
            continue
        url_img = post.get("url_overridden_by_dest") or post.get("url")
        if not url_img:
            continue
        if any(url_img.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"]):
            items.append({
                "id": post.get("id"),
                "title": post.get("title"),
                "upvotes": post.get("ups", 0),
                "image_url": url_img,
                "permalink": "https://reddit.com" + post.get("permalink", ""),
                "author": post.get("author"),
            })
        else:
            preview = post.get("preview")
            if preview and preview.get("images"):
                src = preview["images"][0]["source"].get("url")
                if src:
                    src = src.replace("&amp;", "&")
                    items.append({
                        "id": post.get("id"),
                        "title": post.get("title"),
                        "upvotes": post.get("ups", 0),
                        "image_url": src,
                        "permalink": "https://reddit.com" + post.get("permalink", ""),
                        "author": post.get("author"),
                    })
    return items

def filter_candidates(items):
    seen = set()
    out = []
    for it in items:
        if it['id'] in seen: continue
        seen.add(it['id'])
        if it['upvotes'] < MIN_UPVOTES: continue
        out.append(it)
    return out

def download_image(url):
    resp = requests.get(url, headers=HEADERS, stream=True, timeout=20)
    resp.raise_for_status()
    img = Image.open(BytesIO(resp.content)).convert('RGB')
    return img

def generate_programming_caption(original_title):
    if not OPENAI_API_KEY:
        return original_title + " #programming"
    prompt = ("You are a witty social media copywriter. Rewrite this meme title so it becomes a short (<=140 chars), "
              "funny programming-related caption with 3-5 hashtags. Return only the caption.\n\n"
              f"Original title: {original_title}")
    resp = openai.Completion.create(model='gpt-4o-mini', prompt=prompt, max_tokens=150, temperature=0.8)
    return resp.choices[0].text.strip()

def overlay_text_on_image(img: Image.Image, caption_text: str):
    img = img.copy()
    w, h = img.size
    side = min(w,h)
    left = (w-side)//2
    top = (h-side)//2
    img = img.crop((left, top, left+side, top+side))
    img.thumbnail(MAX_IMAGE_SIZE)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=36)
    except Exception:
        font = ImageFont.load_default()
    margin = 12
    max_width = img.width - margin*2
    words = caption_text.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textsize(test, font=font)[0] <= max_width:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    line_h = draw.textsize("A", font=font)[1]
    total_h = line_h*len(lines) + margin*2
    rect_y0 = img.height - total_h - 10
    overlay_box = Image.new("RGBA", (img.width, total_h), (0,0,0,160))
    img.paste(overlay_box, (0, rect_y0), overlay_box)
    y = rect_y0 + margin
    for line in lines:
        draw.text((margin, y), line, font=font, fill=(255,255,255))
        y += line_h
    return img

def upload_to_backend(img: Image.Image):
    buf = BytesIO()
    img.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    files = {'file': ('meme.jpg', buf, 'image/jpeg')}
    r = requests.post(f"{BACKEND_BASE}/api/upload", files=files, timeout=60)
    r.raise_for_status()
    return r.json().get('imageUrl')

def schedule_post(image_url, caption):
    schedule_time = time.time() + 3600
    schedule_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(schedule_time))
    resp = requests.post(f"{BACKEND_BASE}/api/schedule", json={'imageUrl': image_url, 'caption': caption, 'scheduleTime': schedule_iso}, timeout=30)
    resp.raise_for_status()
    return resp.json()

def process_one(candidate):
    try:
        img = download_image(candidate['image_url'])
        caption = generate_programming_caption(candidate['title'])
        meme = overlay_text_on_image(img, caption)
        image_url = upload_to_backend(meme)
        result = schedule_post(image_url, caption)
        print("Scheduled:", result)
        return True
    except Exception as e:
        print("Error:", e)
        return False

def run_once():
    all_cands = []
    for sr in SUBREDDITS:
        try:
            items = fetch_reddit_images(sr, limit=FETCH_LIMIT)
            all_cands.extend(items)
        except Exception as e:
            print("Fetch error", sr, e)
    unique = {c['id']: c for c in all_cands}.values()
    filtered = filter_candidates(unique)
    processed = 0
    for c in filtered:
        if processed >= 3: break
        if process_one(c):
            processed += 1

if __name__ == '__main__':
    sched = BlockingScheduler()
    sched.add_job(run_once, 'interval', minutes=60)
    print("Auto-meme agent started.")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("Stopping.")
