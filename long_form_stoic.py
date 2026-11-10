import asyncio
import base64
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import edge_tts
import imageio_ffmpeg
import numpy as np
import requests
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from PIL import Image, ImageDraw, ImageFont

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output_long"
TEMP_DIR = BASE_DIR / "temp_long"
LONG_HISTORY_FILE = BASE_DIR / "long_history.json"
USED_CLIPS_FILE = BASE_DIR / "used_clips.json"

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

FORBIDDEN_TAGS = {
    "dog", "cat", "pet", "puppy", "kitten", "animal", "insect", "bee",
    "stickman", "cartoon", "baby", "kid", "child", "massage", "spa", "flower",
    "yoga", "fitness", "horror", "creepy", "blood", "zombie", "cute", "funny",
    "green screen", "greenscreen", "chroma", "chromakey", "template",
    "subscribe", "button", "animation", "3d", "vfx", "isolated", "emoji"
}

STOIC_VIDEO_QUERIES = [
    "ancient roman marble statue dark",
    "stormy ocean waves dark moody",
    "burning candle dark shadow",
    "foggy mountain cliff solitude",
    "ancient stone temple ruins",
    "rain falling dark window",
    "fire embers night dark",
    "dramatic storm clouds sky",
]

STOIC_PHOTO_QUERIES = [
    "greek marble statue sculpture",
    "ancient roman colosseum ruins dusk",
    "burning candle dark desk",
    "misty pine forest dark mountains",
    "old leather book library candle",
    "stormy dark sea cliff",
]

CURATED_LONG_TOPICS = [
    "How To Become Mentally Untouchable Using Marcus Aurelius' 5 Rules",
    "The Stoic Art of Letting Go: Lessons for Deep Inner Peace",
    "Why You Care Too Much: Epictetus' Cure for Overthinking",
    "Seneca on Mastering Time: Stop Wasting Your One Short Life",
    "How to Stay Unshakeable When Everyone Around You Panics",
    "The Hidden Stoic Routine to Conquer Anxiety and Anger Forever",
]


def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def load_json_list(path: Path) -> list:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_json_list(path: Path, data: list):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_used_clips() -> set:
    return set(str(x) for x in load_json_list(USED_CLIPS_FILE))


def mark_clip_used(clip_id: str):
    used = get_used_clips()
    used.add(str(clip_id))
    save_json_list(USED_CLIPS_FILE, sorted(list(used)))


def call_gemini_text(prompt: str, timeout: int = 45) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""
    for model in ["gemini-2.5-flash", "gemini-flash-latest", "gemini-flash-lite-latest"]:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=timeout,
            )
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"[WARN] Gemini {model} returned {r.status_code}")
        except Exception as e:
            print(f"[WARN] Gemini {model} error: {e}")
    return ""


def generate_long_script(topic: str, target_minutes: int = 11) -> dict:
    """
    Generates a coherent 5-chapter Stoic documentary script (~1,500-1,800 words for ~10-13 min)
    with explicit visual_type ('video' or 'photo') and cohesive atmospheric search queries.
    """
    outline_prompt = f"""
You are an elite YouTube documentary writer for a top Stoic Philosophy channel ("The Mind and Stoicism"), whose audience watches AND listens with headphones while working, driving, or winding down.

Topic: "{topic}"

Create a 5-Chapter outline for an engaging, deeply reflective {target_minutes}-minute video essay (~1,500 to 1,800 words total).
Return ONLY valid JSON:
{{
  "title": "Compelling, high-CTR Stoic documentary title under 75 chars (DO NOT include #shorts)",
  "thumbnail_text": "3-4 BOLD WORDS for thumbnail",
  "description_summary": "2-sentence compelling hook summarizing what listeners will master.",
  "chapters": [
    {{
      "chapter_num": 1,
      "chapter_title": "Introduction: The Quiet War Within",
      "theme_mood": "dark rain, ancient stone, solitude",
      "key_points": "Hook the listener immediately with a relatable modern pain point and introduce the ancient Stoic antidote."
    }}
  ]
}}
"""
    raw_outline = call_gemini_text(outline_prompt, timeout=35)
    m = re.search(r"\{.*\}", raw_outline, re.DOTALL)
    if not m:
        raise RuntimeError("Failed to generate long-form outline from Gemini.")
    outline = json.loads(m.group(0))

    full_chapters = []
    for ch in outline["chapters"]:
        c_num = ch["chapter_num"]
        c_title = ch["chapter_title"]
        c_mood = ch.get("theme_mood", "ancient marble statue, dark atmosphere")
        c_points = ch.get("key_points", "")

        ch_prompt = f"""
Write Chapter {c_num} ("{c_title}") of our Stoic audio-visual documentary on: "{topic}".
Mood/Visual theme for this chapter: {c_mood}
Core message to cover: {c_points}

CRITICAL VOICE & LISTENER RULES:
1. Write 300 to 360 spoken words divided into 6 cohesive micro-scenes (50-60 words per scene).
2. Because listeners also consume this audio-only, use DELIBERATE punctuation:
   - Commas (,) for natural breathing pauses.
   - Em-dashes (—) for dramatic shifts.
   - Ellipses (...) for reflective hesitation.
   - Rhetorical questions (?) that invite the listener to reflect.
3. No stage directions, no markdown asterisks, no emojis, no chapter header spoken aloud unless natural.
4. For each scene, choose either "video" (70% of scenes) or "photo" (30% of scenes — ideal for dramatic marble busts, ancient ruins, moody close-ups), and give a simple 2-3 word English stock search query matching the chapter's mood.

Return ONLY valid JSON:
{{
  "scenes": [
    {{
      "narration": "Spoken sentences for this scene with rich punctuation...",
      "visual_type": "video",
      "search_query": "ancient marble statue"
    }}
  ]
}}
"""
        raw_ch = call_gemini_text(ch_prompt, timeout=45)
        cm = re.search(r"\{.*\}", raw_ch, re.DOTALL)
        if not cm:
            raise RuntimeError(f"Failed to generate script for Chapter {c_num}")
        ch_data = json.loads(cm.group(0))
        full_chapters.append({
            "chapter_num": c_num,
            "chapter_title": c_title,
            "scenes": ch_data["scenes"],
        })
        print(f"[SCRIPT] Generated Chapter {c_num}: {c_title} ({len(ch_data['scenes'])} scenes)")
        time.sleep(1.5)

    return {
        "title": outline["title"].replace("#shorts", "").replace("#Shorts", "").strip(),
        "thumbnail_text": outline.get("thumbnail_text", "MASTER YOUR MIND"),
        "description_summary": outline.get("description_summary", topic),
        "chapters": full_chapters,
    }


def synthesize_gemini_tts(text: str, out_wav: Path, voice_name: str = "Charon") -> bool:
    """
    Synthesizes studio-grade, emotionally expressive WAV audio via Gemini 3.8 Flash TTS
    (with fallback to Gemini 2.5 Flash Preview TTS).
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False

    clean_text = re.sub(r"[\*\_#`]+", "", text).strip()
    for model in ["gemini-3.8-flash-tts", "gemini-2.5-flash-preview-tts"]:
        for attempt in range(2):
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                    json={
                        "contents": [{"parts": [{"text": clean_text}]}],
                        "generationConfig": {
                            "responseModalities": ["AUDIO"],
                            "speechConfig": {
                                "voiceConfig": {
                                    "prebuiltVoiceConfig": {"voiceName": voice_name}
                                }
                            },
                        },
                    },
                    timeout=60,
                )
                if r.status_code == 200:
                    part = r.json()["candidates"][0]["content"]["parts"][0]
                    inline = part.get("inlineData", {})
                    b64 = inline.get("data", "")
                    mime = inline.get("mimeType", "")
                    if not b64:
                        continue
                    raw_bytes = base64.b64decode(b64)
                    if "pcm" in mime.lower() or "l16" in mime.lower() or not raw_bytes.startswith(b"RIFF"):
                        with wave.open(str(out_wav), "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(24000)
                            wf.writeframes(raw_bytes)
                    else:
                        out_wav.write_bytes(raw_bytes)
                    return True
                elif r.status_code == 429:
                    print(f"[TTS] 429 rate limit on {model}, waiting 8s...")
                    time.sleep(8)
                else:
                    print(f"[TTS] {model} status {r.status_code}: {r.text[:180]}")
                    break
            except Exception as e:
                print(f"[TTS] {model} error: {e}")
                time.sleep(3)
    return False


def synthesize_edge_fallback(text: str, out_wav: Path, voice: str = "en-US-BrianNeural"):
    """Fallback synthesizer using Edge-TTS BrianNeural at natural audiobook pace."""
    clean_text = re.sub(r"[\*\_#`]+", "", text).strip()
    tmp_mp3 = out_wav.with_suffix(".mp3")

    async def _run():
        comm = edge_tts.Communicate(clean_text, voice, rate="+0%")
        await comm.save(str(tmp_mp3))

    asyncio.run(_run())
    subprocess.run(
        [FFMPEG_EXE, "-y", "-i", str(tmp_mp3), "-ar", "24000", "-ac", "1", str(out_wav)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    tmp_mp3.unlink(missing_ok=True)


def get_audio_duration(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def detect_silences(wav_path: Path) -> list[tuple[float, float]]:
    """Uses FFmpeg silencedetect to locate natural breathing pauses in the spoken chapter."""
    cmd = [
        FFMPEG_EXE, "-i", str(wav_path),
        "-af", "silencedetect=noise=-32dB:d=0.28",
        "-f", "null", "-"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    silences = []
    current_start = None
    for line in res.stderr.splitlines():
        ms = re.search(r"silence_start:\s*([\d\.]+)", line)
        if ms:
            current_start = float(ms.group(1))
        me = re.search(r"silence_end:\s*([\d\.]+)", line)
        if me and current_start is not None:
            silences.append((current_start, float(me.group(1))))
            current_start = None
    return silences


def compute_scene_durations(wav_path: Path, scenes: list[dict]) -> list[float]:
    """
    Maps each scene inside a chapter to exact speaker breath pauses so every visual cut
    falls cleanly between sentences.
    """
    total_dur = get_audio_duration(wav_path)
    n = len(scenes)
    if n <= 1:
        return [total_dur]

    silences = detect_silences(wav_path)
    pause_mids = [(s + e) / 2.0 for (s, e) in silences if 0.5 < (s + e) / 2.0 < total_dur - 0.5]

    word_counts = [max(1, len(sc["narration"].split())) for sc in scenes]
    total_words = sum(word_counts)

    cuts = [0.0]
    cum_words = 0
    for i in range(n - 1):
        cum_words += word_counts[i]
        ideal_t = (cum_words / total_words) * total_dur
        min_t = cuts[-1] + 2.5
        max_t = total_dur - (n - 1 - i) * 2.5
        # Find nearest natural pause near ideal_t
        candidates = [p for p in pause_mids if min_t <= p <= max_t]
        if candidates:
            best_p = min(candidates, key=lambda p: abs(p - ideal_t))
            cuts.append(best_p)
        else:
            cuts.append(max(min_t, min(max_t, ideal_t)))
    cuts.append(total_dur)

    durations = [max(2.0, cuts[i + 1] - cuts[i]) for i in range(n)]
    return durations


def fetch_landscape_media(query: str, visual_type: str, dest_path: Path) -> str:
    """
    Fetches horizontal 16:9 Pixabay video or photo avoiding duplicates and green screens.
    Returns 'video' or 'photo' depending on what was actually downloaded.
    """
    api_key = os.getenv("PIXABAY_API_KEY", "").strip()
    used = get_used_clips()
    clean_q = " ".join(re.sub(r"[^a-zA-Z0-9 ]+", " ", query).split()[:3])

    if visual_type == "video":
        queries = [clean_q] + random.sample(STOIC_VIDEO_QUERIES, 2)
        for q in queries:
            url = f"https://pixabay.com/api/videos/?key={api_key}&q={quote(q)}&video_type=film&per_page=25"
            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    hits = r.json().get("hits", [])
                    random.shuffle(hits)
                    for hit in hits:
                        raw_tags = hit.get("tags", "").lower()
                        if set(t.strip() for t in raw_tags.split(",")).intersection(FORBIDDEN_TAGS) or "green" in raw_tags:
                            continue
                        cid = f"px_{hit.get('id')}"
                        if cid in used:
                            continue
                        vids = hit.get("videos", {})
                        # Choose horizontal HD video (medium or large)
                        cand = vids.get("medium") or vids.get("large") or vids.get("small")
                        if cand and cand.get("url") and cand.get("width", 1920) >= cand.get("height", 1080):
                            vr = requests.get(cand["url"], stream=True, timeout=25)
                            if vr.status_code == 200:
                                vid_dest = dest_path.with_suffix(".mp4")
                                with open(vid_dest, "wb") as f:
                                    for chunk in vr.iter_content(65536):
                                        f.write(chunk)
                                if vid_dest.stat().st_size > 100_000:
                                    mark_clip_used(cid)
                                    return "video"
            except Exception:
                pass

    # Photo path (or video fallback to horizontal photo with Ken Burns motion)
    p_queries = [clean_q] + random.sample(STOIC_PHOTO_QUERIES, 2)
    for q in p_queries:
        url = f"https://pixabay.com/api/?key={api_key}&q={quote(q)}&image_type=photo&orientation=horizontal&per_page=25"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                hits = r.json().get("hits", [])
                random.shuffle(hits)
                for hit in hits:
                    raw_tags = hit.get("tags", "").lower()
                    if set(t.strip() for t in raw_tags.split(",")).intersection(FORBIDDEN_TAGS):
                        continue
                    cid = f"px_img_{hit.get('id')}"
                    if cid in used:
                        continue
                    img_url = hit.get("largeImageURL") or hit.get("webformatURL")
                    if img_url:
                        ir = requests.get(img_url, timeout=20)
                        if ir.status_code == 200 and len(ir.content) > 30_000:
                            img_dest = dest_path.with_suffix(".jpg")
                            img_dest.write_bytes(ir.content)
                            mark_clip_used(cid)
                            return "photo"
        except Exception:
            pass

    raise RuntimeError(f"Could not download visual media for query: {query}")


def create_chapter_overlay_png(chapter_num: int, chapter_title: str, out_png: Path):
    """Creates a transparent 1920x1080 PNG lower-third title card for chapter start."""
    img = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_path = None
    for cand in [
        "C:\\Windows\\Fonts\\georgiab.ttf",
        "C:\\Windows\\Fonts\\timesbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ]:
        if os.path.exists(cand):
            font_path = cand
            break

    f_small = ImageFont.truetype(font_path, 30) if font_path else ImageFont.load_default()
    f_big = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()

    # Subtle dark backdrop band at bottom-left
    draw.rectangle([(80, 860), (1250, 1000)], fill=(10, 10, 14, 180))
    draw.rectangle([(80, 860), (88, 1000)], fill=(212, 175, 55, 255))  # Gold Stoic accent bar

    draw.text((115, 875), f"CHAPTER {chapter_num}", font=f_small, fill=(212, 175, 55, 255))
    draw.text((115, 920), chapter_title.upper()[:52], font=f_big, fill=(245, 245, 245, 255))
    img.save(out_png)


def render_normalized_scene_clip(
    media_type: str,
    media_base: Path,
    duration: float,
    out_mp4: Path,
    overlay_png: Path = None,
):
    """
    Renders a single normalized 1920x1080 30fps silent clip locked to exact `duration`
    with unified dark Stoic color grading, Ken Burns zoom for photos, and optional chapter card.
    """
    frames = max(30, int(round(duration * FPS)))
    grade = "eq=contrast=1.08:brightness=-0.05:saturation=0.72,vignette=PI/4"

    if media_type == "video":
        in_file = media_base.with_suffix(".mp4")
        vfilter = (
            f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},fps={FPS},setpts=PTS-STARTPTS,{grade}"
        )
        cmd = [FFMPEG_EXE, "-y", "-stream_loop", "-1", "-i", str(in_file)]
    else:
        in_file = media_base.with_suffix(".jpg")
        # Gentle Ken Burns slow zoom (1.0 -> 1.12)
        vfilter = (
            f"[0:v]scale=3840:2160:force_original_aspect_ratio=increase,"
            f"crop=3840:2160,"
            f"zoompan=z='min(zoom+0.0005,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
            f"{grade}"
        )
        cmd = [FFMPEG_EXE, "-y", "-i", str(in_file)]

    if overlay_png and overlay_png.exists():
        cmd += ["-loop", "1", "-i", str(overlay_png)]
        vfilter += (
            f"[base];[1:v]fade=t=in:st=0.2:d=0.6:alpha=1,fade=t=out:st=4.0:d=0.8:alpha=1[ov];"
            f"[base][ov]overlay=0:0:enable='between(t,0,5.0)'[v]"
        )
    else:
        vfilter += "[v]"

    cmd += [
        "-filter_complex", vfilter,
        "-map", "[v]",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-video_track_timescale", "90000",
        "-pix_fmt", "yuv420p", "-an",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def create_long_ambient_pad(duration: float, out_wav: Path):
    """Creates a warm, soothing 432Hz/C2 Stoic ambient underscore (-27 dB)."""
    sr = 24000
    chunk_sec = 30.0
    t_chunk = np.linspace(0, chunk_sec, int(sr * chunk_sec), endpoint=False)
    pad = (
        0.50 * np.sin(2 * np.pi * 65.41 * t_chunk) +
        0.30 * np.sin(2 * np.pi * 98.00 * t_chunk + 0.5) +
        0.20 * np.sin(2 * np.pi * 130.81 * t_chunk + 1.1)
    )
    # Seamless loop modulation
    lfo = 0.78 + 0.22 * np.sin(2 * np.pi * (1.0 / 15.0) * t_chunk)
    pad = np.clip(pad * lfo * 0.044, -1.0, 1.0)  # ~ -27 dB
    pcm = (pad * 32767).astype(np.int16).tobytes()

    total_chunks = int(math.ceil(duration / chunk_sec))
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for _ in range(total_chunks):
            wf.writeframes(pcm)


def create_thumbnail(bg_img: Path, hook_text: str, out_thumb: Path):
    """Generates a dramatic 1280x720 YouTube thumbnail from the best Stoic image."""
    img = Image.open(bg_img).convert("RGB")
    img = img.resize((1280, 720), Image.Resampling.LANCZOS)
    # Darken gradient
    overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 135))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    font_path = None
    for cand in [
        "C:\\Windows\\Fonts\\georgiab.ttf",
        "C:\\Windows\\Fonts\\impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ]:
        if os.path.exists(cand):
            font_path = cand
            break
    font = ImageFont.truetype(font_path, 86) if font_path else ImageFont.load_default()

    words = hook_text.upper().split()
    lines = [" ".join(words[i:i+2]) for i in range(0, len(words), 2)]
    y = 220
    for idx, line in enumerate(lines[:3]):
        color = (255, 215, 0) if idx == 0 else (255, 255, 255)
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (1280 - tw) // 2
        draw.text((x + 4, y + 4), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=color)
        y += 105

    img.save(out_thumb, quality=92)


def upload_long_youtube(
    video_path: Path,
    thumb_path: Path,
    title: str,
    description: str,
    privacy_status: str = "public",
) -> str:
    from uploader import get_authenticated_service

    youtube = get_authenticated_service()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": ["stoicism", "marcus aurelius", "philosophy", "seneca", "epictetus", "self improvement", "stoic mindset", "sleep philosophy", "documentary"],
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": "private" if privacy_status == "scheduled" else privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    if privacy_status == "scheduled":
        pub = datetime.now(timezone.utc) + timedelta(hours=2)
        body["status"]["publishAt"] = pub.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=5 * 1024 * 1024)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    print(f"[YOUTUBE] Uploading long-form video '{title}'...")
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"[YOUTUBE] Progress: {int(status.progress() * 100)}%")

    vid_id = resp["id"]
    url = f"https://www.youtube.com/watch?v={vid_id}"
    print(f"[SUCCESS] Long-form video live at: {url}")

    if thumb_path.exists():
        try:
            youtube.thumbnails().set(
                videoId=vid_id,
                media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
            ).execute()
            print("[SUCCESS] Custom thumbnail uploaded!")
        except Exception as e:
            print(f"[WARN] Thumbnail upload skipped (may require intermediate verification): {e}")

    return url


def run_long_form_pipeline(topic: str = None, privacy_status: str = "public", upload: bool = True):
    ensure_dirs()
    history = load_json_list(LONG_HISTORY_FILE)
    past_topics = {h.get("topic", "").lower() for h in history}

    if not topic:
        available = [t for t in CURATED_LONG_TOPICS if t.lower() not in past_topics]
        if available:
            topic = random.choice(available)
        else:
            gen_t = call_gemini_text(
                f"Suggest ONE compelling, original 12-minute YouTube Stoic philosophy documentary title (not in: {list(past_topics)}). Return ONLY the title."
            )
            topic = gen_t.strip('"') if gen_t else random.choice(CURATED_LONG_TOPICS)

    print(f"\n{'='*65}\n  STOIC WISDOM LONG-FORM AUDIO-VISUAL DOCUMENTARY ENGINE\n{'='*65}")
    print(f"[TOPIC] {topic}\n")

    script_data = generate_long_script(topic)
    chapters = script_data["chapters"]

    chapter_wavs = []
    chapter_timestamps = []
    all_scene_clips = []
    cumulative_sec = 0.0
    first_photo_for_thumb = None

    for ch in chapters:
        c_num = ch["chapter_num"]
        c_title = ch["chapter_title"]
        scenes = ch["scenes"]

        # Record YouTube Chapter start timestamp (MM:SS)
        mins = int(cumulative_sec // 60)
        secs = int(cumulative_sec % 60)
        chapter_timestamps.append(f"{mins:02d}:{secs:02d} {c_title}")

        # 1. Synthesize full chapter speech continuously for natural podcast cadence
        chapter_text = " ... ".join(sc["narration"].strip() for sc in scenes)
        ch_wav = TEMP_DIR / f"chapter_{c_num}.wav"
        print(f"[AUDIO] Synthesizing Chapter {c_num} ({len(chapter_text.split())} words) via Gemini 3.8 Flash TTS (Charon)...")
        ok = synthesize_gemini_tts(chapter_text, ch_wav, voice_name="Charon")
        if not ok:
            print(f"[AUDIO] Falling back to Edge-TTS BrianNeural for Chapter {c_num}...")
            synthesize_edge_fallback(chapter_text, ch_wav)

        # 2. Align scene durations to exact breath pauses
        scene_durs = compute_scene_durations(ch_wav, scenes)
        chapter_dur = sum(scene_durs)
        cumulative_sec += chapter_dur
        chapter_wavs.append(ch_wav)

        # 3. Render chapter overlay PNG
        ov_png = TEMP_DIR / f"overlay_ch_{c_num}.png"
        create_chapter_overlay_png(c_num, c_title, ov_png)

        # 4. Fetch media & render normalized 1080p clips locked to breath pauses
        for s_idx, (sc, sdur) in enumerate(zip(scenes, scene_durs)):
            m_base = TEMP_DIR / f"media_c{c_num}_s{s_idx}"
            actual_type = fetch_landscape_media(sc.get("search_query", "marble statue"), sc.get("visual_type", "video"), m_base)
            if actual_type == "photo" and first_photo_for_thumb is None:
                first_photo_for_thumb = m_base.with_suffix(".jpg")

            clip_mp4 = TEMP_DIR / f"clip_c{c_num}_s{s_idx}.mp4"
            render_normalized_scene_clip(
                actual_type,
                m_base,
                sdur,
                clip_mp4,
                overlay_png=(ov_png if s_idx == 0 else None),
            )
            all_scene_clips.append(clip_mp4)
            print(f"  [CLIP] Ch{c_num}.S{s_idx+1}: {actual_type.upper()} ({sdur:.1f}s) rendered.")

        time.sleep(2.5)  # Polite API pacing between chapters

    # 5. Concatenate all chapter WAVs
    voice_list_txt = TEMP_DIR / "voice_list.txt"
    voice_list_txt.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in chapter_wavs), encoding="utf-8")
    full_voice_wav = TEMP_DIR / "full_voice.wav"
    subprocess.run(
        [FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", str(voice_list_txt), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(full_voice_wav)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    total_audio_dur = get_audio_duration(full_voice_wav)
    ambient_wav = TEMP_DIR / "ambient_pad.wav"
    create_long_ambient_pad(total_audio_dur + 2.0, ambient_wav)

    mixed_audio = TEMP_DIR / "mixed_audio.m4a"
    subprocess.run(
        [
            FFMPEG_EXE, "-y",
            "-i", str(full_voice_wav),
            "-i", str(ambient_wav),
            "-filter_complex", "[0:a]aresample=48000[v];[1:a]aresample=48000[a];[v][a]amix=inputs=2:duration=first:dropout_transition=2[out]",
            "-map", "[out]", "-c:a", "aac", "-b:a", "192k",
            str(mixed_audio),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # 6. Concatenate all visual clips and combine with mixed studio audio
    video_list_txt = TEMP_DIR / "video_list.txt"
    video_list_txt.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in all_scene_clips), encoding="utf-8")

    safe_slug = re.sub(r"[^a-zA-Z0-9]+", "_", script_data["title"])[:45].strip("_")
    final_mp4 = OUTPUT_DIR / f"Stoic_Long_{safe_slug}.mp4"

    subprocess.run(
        [
            FFMPEG_EXE, "-y",
            "-f", "concat", "-safe", "0", "-i", str(video_list_txt),
            "-i", str(mixed_audio),
            "-c:v", "copy", "-c:a", "copy", "-shortest",
            str(final_mp4),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print(f"\n[DONE] Full Long-Form Documentary Built: {final_mp4} ({total_audio_dur/60:.1f} min)")

    # 7. Generate Thumbnail
    thumb_path = OUTPUT_DIR / f"Stoic_Long_{safe_slug}_thumb.jpg"
    if first_photo_for_thumb is None:
        fetch_landscape_media("ancient marble bust dark", "photo", TEMP_DIR / "thumb_bg")
        first_photo_for_thumb = (TEMP_DIR / "thumb_bg").with_suffix(".jpg")
    create_thumbnail(first_photo_for_thumb, script_data["thumbnail_text"], thumb_path)

    # 8. Build rich Description with Chapters & Book Links
    chapters_block = "\n".join(chapter_timestamps)
    description = (
        f"{script_data['description_summary']}\n\n"
        f"Put on your headphones, breathe slowly, and immerse yourself in the timeless wisdom of Marcus Aurelius, Seneca, and Epictetus.\n\n"
        f"⏱️ CHAPTERS:\n{chapters_block}\n\n"
        f"📚 ESSENTIAL STOIC READING:\n"
        f"• Meditations by Marcus Aurelius\n"
        f"• Letters from a Stoic by Seneca\n"
        f"• Discourses by Epictetus\n\n"
        f"#Stoicism #MarcusAurelius #Philosophy #AudioEssay #MentalStrength #SleepPhilosophy"
    )

    if upload:
        priv = "scheduled" if "--scheduled" in sys.argv else privacy_status
        url = upload_long_youtube(final_mp4, thumb_path, script_data["title"], description, privacy_status=priv)
        history.append({
            "topic": topic,
            "title": script_data["title"],
            "url": url,
            "duration_min": round(total_audio_dur / 60, 2),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })
        save_json_list(LONG_HISTORY_FILE, history)
        return url
    return str(final_mp4)


if __name__ == "__main__":
    no_upload = "--dry-run" in sys.argv
    run_long_form_pipeline(upload=not no_upload)
