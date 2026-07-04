import os
import json
import re
import sys
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp  # Added for direct API usage

# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "itunes_library"
LOG_FILE = BASE_DIR / "pipeline.log"
TRACKS_FILE = BASE_DIR / "tracks.json"
FAILED_FILE = BASE_DIR / "failed_tracks.json"

OUTPUT_DIR.mkdir(exist_ok=True)

MAX_RETRIES = 3

load_dotenv()

# ============================================================
# LOGGING
# ============================================================

def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# ============================================================
# FILE CLEANING
# ============================================================

def clean(text):
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ============================================================
# SPOTIFY AUTH
# ============================================================

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET")
    )
)

# ============================================================
# ROBUST PLAYLIST ID PARSER
# ============================================================

def get_playlist_id(url):
    url = url.strip()
    match = re.search(r"playlist/([a-zA-Z0-9]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"spotify:playlist:([a-zA-Z0-9]+)", url)
    if match:
        return match.group(1)
    raise ValueError("Invalid Spotify playlist URL")

# ============================================================
# EXPORT PLAYLIST → JSON
# ============================================================

def export_playlist(playlist_url):
    playlist_id = get_playlist_id(playlist_url)
    log(f"\n[EXPORT] Playlist ID: {playlist_id}")

    results = sp.playlist_tracks(playlist_id)
    tracks = []
    seen = set()

    while results:
        for item in results["items"]:
            track = item["track"]
            if not track:
                continue

            artist = track["artists"][0]["name"]
            title = track["name"]
            album = track["album"]["name"]

            key = f"{artist}-{title}".lower()
            if key in seen:
                continue
            seen.add(key)

            tracks.append({
                "artist": artist,
                "title": title,
                "album": album
            })

        if results["next"]:
            results = sp.next(results)
        else:
            break

    TRACKS_FILE.write_text(json.dumps(tracks, indent=2), encoding="utf-8")
    log(f"[EXPORT] Saved {len(tracks)} tracks")
    return tracks

# ============================================================
# YOUTUBE SEARCH
# ============================================================

def get_candidates(query):
    cmd = [
        sys.executable,
        "-m", "yt_dlp",
        f"ytsearch5:{query}",
        "--print", "%(title)s|%(duration)s|%(webpage_url)s",
        "--no-warnings"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    candidates = []
    for line in result.stdout.splitlines():
        if "|" in line:
            parts = line.split("|")
            if len(parts) == 3:
                candidates.append(parts)
    return candidates

# ============================================================
# SMART MATCHING
# ============================================================

def pick_best(track, candidates):
    artist = track["artist"].lower()
    title = track["title"].lower()
    best_url = None
    best_score = -1

    for yt_title, _, url in candidates:
        yt = yt_title.lower()
        score = 0
        if title in yt:
            score += 60
        if artist in yt:
            score += 40

        bad = ["live", "cover", "karaoke", "instrumental", "remix", "version"]
        for b in bad:
            if b in yt:
                score -= 15

        if score > best_score:
            best_score = score
            best_url = url
    return best_url

# ============================================================
# DOWNLOAD TRACK (ENHANCED)
# ============================================================

def download_track(track):
    artist = clean(track["artist"])
    title = clean(track["title"])
    album = clean(track.get("album", "Unknown Album"))

    folder = OUTPUT_DIR / artist / album
    folder.mkdir(parents=True, exist_ok=True)

    final_file = folder / f"{artist} - {title}.mp3"

    if final_file.exists() and final_file.stat().st_size > 100_000:
        return f"SKIP: {artist} - {title}"

    query = f"{artist} {title} official audio"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            candidates = get_candidates(query)
            url = pick_best(track, candidates)

            if not url:
                log(f"[{attempt}] No good match found for {artist} - {title}")
                continue

            log(f"[{attempt}] Downloading: {artist} - {title}")

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(folder / f"{artist} - {title}.%(ext)s"),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': False,
                'extract_audio': True,
                'noplaylist': True,
                'ignoreerrors': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # Ensure final filename
                if final_file.exists() or Path(str(final_file).replace('.mp3', '.webm')).exists():
                    return f"OK: {artist} - {title}"

        except Exception as e:
            log(f"[{attempt}] Error for {artist} - {title}: {str(e)}")

    return f"FAIL: {artist} - {title}"

# ============================================================
# MAIN PIPELINE
# ============================================================

def main():
    playlist_url = input("Paste Spotify playlist URL: ").strip()
    tracks = export_playlist(playlist_url)

    failed = []
    log("\n--- STARTING DOWNLOADS ---\n")

    for i, track in enumerate(tracks, 1):
        result = download_track(track)
        log(f"[{i}/{len(tracks)}] {result}")
        if "FAIL" in result:
            failed.append(track)

    FAILED_FILE.write_text(json.dumps(failed, indent=2), encoding="utf-8")
    log("\nDONE\n")

if __name__ == "__main__":
    main()