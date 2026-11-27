import json
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
from main import build_shorts_video
from uploader import upload_shorts_video
from multi_platform_uploader import upload_to_facebook_reels, upload_to_tiktok

HISTORY_FILE = BASE_DIR / "history.json"
LONG_HISTORY_FILE = BASE_DIR / "long_history.json"


def pick_related_long_video(topic: str) -> dict | None:
    """Finds the best-matching (or latest) published long-form documentary for cross-linking."""
    if not LONG_HISTORY_FILE.exists():
        return None
    try:
        longs = json.loads(LONG_HISTORY_FILE.read_text(encoding="utf-8"))
        if not longs:
            return None
        keywords = [w for w in topic.lower().split() if len(w) >= 4]
        best_item = None
        best_score = 0
        for item in longs:
            hay = f"{item.get('topic', '')} {item.get('title', '')}".lower()
            score = sum(1 for kw in keywords if kw in hay)
            if score > best_score:
                best_score = score
                best_item = item
        return best_item if best_item else longs[-1]
    except Exception:
        return None


def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_to_history(topic: str, title: str, url: str, publish_at: str = None):
    history = load_history()
    entry = {
        "topic": topic,
        "title": title,
        "url": url,
        "timestamp": datetime.now().isoformat(timespec="seconds")
    }
    if publish_at:
        entry["publish_at"] = publish_at
    history.append(entry)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


VIRAL_STOIC_PROMPTS = [
    "Marcus Aurelius on how to handle toxic and ungrateful people",
    "Seneca's brutal reminder on why you have far less time than you think",
    "Epictetus rule: The psychological trick to becoming mentally untouchable",
    "The Stoic secret to never getting angry again in any argument",
    "Why seeking revenge destroys you while indifference makes you powerful",
    "Marcus Aurelius: 3 morning habits that will discipline your mind",
    "The brutal truth about death that will set your soul free (Memento Mori)",
    "How to stop caring what people think of you in under 30 seconds",
    "The Stoic art of silence: Why the smartest person in the room never speaks first",
    "Why suffering is a choice: Seneca's lesson on modern anxiety",
    "3 tests life throws at you to see if you have truly matured",
    "How to detach emotionally from anyone who disrespects you",
    "The mirror test: What Marcus Aurelius saw every morning before ruling Rome",
    "Why comfort is the silent killer of modern ambition",
    "How to master impulse control and conquer your own desires",
    "Amor Fati: Why loving your fate turns every disaster into fuel",
    "Why you should never complain, not even to yourself",
    "Epictetus on freedom: You only control your thoughts and actions",
    "How to remain calm when everyone around you is panicking",
    "The 3 things you must cut out of your life to find peace",
    "Why the opinion of 10,000 foolish people means nothing",
    "The Stoic cure for overthinking and racing thoughts",
    "How to turn pain into unshakeable mental armor",
    "Seneca on anger: Temporary madness that costs you everything",
    "Why true power is conquering yourself, not other people"
]


_STOIC_STOP_WORDS = {
    "that", "this", "with", "from", "your", "about", "never", "every", "people",
    "stoic", "stoicism", "philosophy", "mind", "life", "rule", "secret", "shorts",
    "what", "when", "where", "which", "while", "into", "their", "they", "them",
    "marcus", "aurelius", "seneca", "epictetus", "zeno", "cato", "master", "power",
}


def _norm_text(s: str) -> str:
    s = re.sub(r"#shorts", "", s or "", flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s.lower())).strip()


def _meaningful_tokens(s: str) -> set[str]:
    return {w for w in _norm_text(s).split() if len(w) >= 4 and w not in _STOIC_STOP_WORDS}


def _is_duplicate_stoic_item(candidate: str, history: list[dict]) -> bool:
    cand_norm = _norm_text(candidate)
    if not cand_norm:
        return True
    cand_tokens = _meaningful_tokens(cand_norm)
    for item in history:
        for field in ("topic", "title"):
            past_norm = _norm_text(item.get(field, ""))
            if past_norm and cand_norm == past_norm:
                return True
    for item in history[-80:]:
        for field in ("topic", "title"):
            past_tokens = _meaningful_tokens(item.get(field, ""))
            if not cand_tokens or not past_tokens:
                continue
            overlap = cand_tokens & past_tokens
            union = cand_tokens | past_tokens
            if len(overlap) >= 2 and (len(overlap) / len(union) >= 0.45 or len(overlap) >= 3):
                return True
    return False


def _ensure_unique_title(title: str, topic: str, history: list[dict]) -> str:
    cand_norm = _norm_text(title)
    past_titles = {_norm_text(item.get("title", "")) for item in history}
    if cand_norm and cand_norm not in past_titles:
        return title
    clean_topic = re.sub(r"#shorts", "", topic or "", flags=re.IGNORECASE).strip().rstrip("?.!:-")
    if len(clean_topic) > 50:
        clean_topic = clean_topic[:50].rsplit(" ", 1)[0].rstrip(".,:-")
    alt = f"{clean_topic} #shorts"
    if _norm_text(alt) not in past_titles:
        print(f"[DEDUP] Replaced duplicate title '{title}' -> '{alt}'")
        return alt
    return title


def pick_viral_topic() -> str:
    """
    Picks a fresh viral English topic using Gemini or the curated list,
    strictly avoiding any previously covered topics or titles.
    """
    history = load_history()
    past_entries = [
        f"{item.get('topic', '')} | Title: {item.get('title', '')}".strip()
        for item in history[-80:]
    ]

    recent_text = " ".join(
        f"{item.get('topic', '')} {item.get('title', '')}" for item in history[-2:]
    ).lower()
    avoid_philosophers = [
        p for p in ["seneca", "marcus aurelius", "epictetus"] if p in recent_text
    ]

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            import requests

            past_list_str = "\n- ".join(past_entries) if past_entries else "None"
            avoid_rule = (
                f"Do NOT focus on {', '.join(p.title() for p in avoid_philosophers)} this time—rotate to a different Stoic thinker or timeless Stoic principle.\n"
                if avoid_philosophers
                else ""
            )
            prompt = (
                "We have ALREADY published YouTube Shorts about these Stoic philosophy topics and titles:\n"
                f"- {past_list_str}\n\n"
                "CRITICAL RULE: Suggest ONE brand new, deeply impactful YouTube Shorts topic in English about "
                "Stoicism, Marcus Aurelius, Seneca, Epictetus, mental resilience, emotional mastery, or discipline.\n"
                f"{avoid_rule}"
                "Do NOT duplicate or closely paraphrase ANY topic or title above.\n"
                "Return ONLY the topic sentence, under 10 words, no quotes."
            )
            for _attempt in range(3):
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={api_key}",
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=12,
                )
                if r.status_code == 200:
                    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip().strip('"\'` ')
                    if txt and len(txt) > 5 and not _is_duplicate_stoic_item(txt, history):
                        if not any(p in txt.lower() for p in avoid_philosophers):
                            return txt
        except Exception:
            pass

    available = [t for t in VIRAL_STOIC_PROMPTS if not _is_duplicate_stoic_item(t, history)]
    rotated = [t for t in available if not any(p in t.lower() for p in avoid_philosophers)]
    if rotated:
        return random.choice(rotated)
    if not available:
        available = VIRAL_STOIC_PROMPTS
    return random.choice(available)


def run_autopilot(privacy_status: str = "scheduled"):
    print("=" * 60)
    print("      24/7 AUTONOMOUS STOIC WISDOM SHORTS ENGINE      ")
    print("=" * 60)

    # 1. Pick viral topic
    topic = pick_viral_topic()
    print(f"\n[TOPIC SELECTED] {topic}")

    # 2. Build complete Short video
    video_path = build_shorts_video(topic)

    # 3. Load generated metadata (supports both .json and _metadata.json)
    meta_path = video_path.with_suffix(".json")
    if not meta_path.exists():
        meta_path = video_path.with_name(video_path.stem + "_metadata.json")
    clean_topic = topic.strip().rstrip("?.!")
    fallback_title = clean_topic[:55].rsplit(" ", 1)[0].rstrip(".,:-") if len(clean_topic) > 55 else clean_topic
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        title = _ensure_unique_title(meta.get("title", f"{fallback_title} #shorts"), topic, load_history())
        description = meta.get("description", f"Timeless Stoic philosophy: {clean_topic}. #shorts #stoic #stoicism #marcusaurelius #philosophy #wisdom")
    else:
        title = _ensure_unique_title(f"{fallback_title} #shorts", topic, load_history())
        description = f"Timeless Stoic philosophy: {clean_topic}. Subscribe for daily mental mastery! #shorts #stoic #stoicism #marcusaurelius #philosophy #wisdom"

    tags = ["shorts", "stoicism", "stoic philosophy", "marcus aurelius", "philosophy", "wisdom", "mindset", "mentalstrength", "seneca", "epictetus"]

    related_long = pick_related_long_video(topic)
    if related_long and related_long.get("url"):
        description = (
            f"{description.rstrip()}\n\n"
            f"🎧 Watch the full Stoic deep dive:\n"
            f"{related_long.get('title', 'Full Stoic Documentary')} → {related_long['url']}"
        )

    # 4. Upload to YouTube
    print(f"\n[AUTOPILOT] Uploading to YouTube ({privacy_status})...")
    url = upload_shorts_video(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        privacy_status=privacy_status
    )

    # 5. Dual publishing to Facebook Reels & TikTok
    upload_to_facebook_reels(video_path=video_path, description=f"{title}\n\n{description}")
    upload_to_tiktok(video_path=video_path, title=title)

    # 6. Save to history
    import uploader as _uploader
    save_to_history(topic=topic, title=title, url=url, publish_at=getattr(_uploader, "LAST_SCHEDULED_PUBLISH_AT", None))
    print("\n" + "=" * 60)
    print(f"[SUCCESS] Stoic Short Live on YouTube: {url}")
    print("=" * 60)
    return url


if __name__ == "__main__":
    privacy = "scheduled"
    if "--public" in sys.argv:
        privacy = "public"
    elif "--unlisted" in sys.argv:
        privacy = "unlisted"
    elif "--private" in sys.argv:
        privacy = "private"
    run_autopilot(privacy_status=privacy)
