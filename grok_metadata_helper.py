import json
from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TXXX

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "itunes_library"
TRACKS_FILE = BASE_DIR / "tracks.json"

def embed_metadata():
    print("Loading track data from tracks.json...")
    
    if not TRACKS_FILE.exists():
        print("❌ tracks.json not found. Please run the main downloader first.")
        return

    with open(TRACKS_FILE, "r", encoding="utf-8") as f:
        tracks = json.load(f)

    print(f"Found {len(tracks)} tracks. Starting metadata embedding...\n")

    success = 0
    skipped = 0
    failed = 0

    for track in tracks:
        artist = track["artist"]
        title = track["title"]
        album = track.get("album", "Unknown Album")

        # Clean names to match downloader
        clean_artist = "".join(c for c in artist if c not in '<>:"/\\|?*').strip()
        clean_title = "".join(c for c in title if c not in '<>:"/\\|?*').strip()
        clean_album = "".join(c for c in album if c not in '<>:"/\\|?*').strip()

        mp3_path = OUTPUT_DIR / clean_artist / clean_album / f"{clean_artist} - {clean_title}.mp3"

        if mp3_path.exists():
            try:
                audio = MP3(mp3_path, ID3=ID3)
                if audio.tags is None:
                    audio.add_tags()

                audio.tags.add(TIT2(encoding=3, text=title))      # Song Title
                audio.tags.add(TPE1(encoding=3, text=artist))     # Artist
                audio.tags.add(TALB(encoding=3, text=album))      # Album

                # Extra info
                audio.tags.add(TXXX(encoding=3, desc="Spotify Album", text=album))

                audio.save()
                print(f"✓ {artist} - {title}")
                success += 1
            except Exception as e:
                print(f"✗ Failed: {artist} - {title} | Error: {e}")
                failed += 1
        else:
            print(f"⚠ Skipped (file not found): {artist} - {title}")
            skipped += 1

    print("\n=== Metadata Embedding Complete ===")
    print(f"Successfully updated : {success}")
    print(f"Skipped (not found)  : {skipped}")
    print(f"Failed               : {failed}")

if __name__ == "__main__":
    embed_metadata()