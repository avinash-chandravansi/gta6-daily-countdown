# GTA VI daily countdown

Generates a vertical (1080×1920, 9:16) 8-second countdown reel for Instagram Reels / TikTok / YouTube Shorts,
counting down to **GTA VI on November 19, 2026**.

Synthwave look: sunset sun, scrolling neon grid and palm silhouettes. The day count rolls up and lands on the beat,
with a synthesized soundtrack (pad, riser, kick and bass).

## Usage

Requires Python 3.9+, `ffmpeg` and the Inter font (falls back to DejaVu).

```bash
pip install -r requirements.txt
python3 make_reel.py                    # today (US Eastern) -> out/gta6-countdown-YYYY-MM-DD.mp4
python3 make_reel.py --date 2026-11-18  # any specific day ("TOMORROW · 1 DAY TO GO")
python3 make_reel.py --no-audio         # silent, if you'd rather add a trending sound in-app
```

On launch day the reel switches to "IT'S LAUNCH DAY".

## Daily automation

`.github/workflows/daily-reel.yml` renders the day's reel every morning and attaches it to the workflow run
as an artifact (Actions → Daily countdown reel → latest run). It can also be triggered manually.
