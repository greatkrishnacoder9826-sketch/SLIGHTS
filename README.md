# My Sister, My Love — Cinematic Pixel Reveal

A cinematic, high-quality pixel-by-pixel photo reveal animation built with
Python, Pygame, NumPy and Pillow. The photo starts as a dark canvas of
scattered pixel-blocks and gradually reconstructs itself into the full,
original-resolution photograph, finishing with a soft cinematic glow and
an elegant fading caption: **"My Sister, My Love"**.

## Project structure

```
project/
├── main.py
├── requirements.txt
├── README.md
├── assets/
│   └── sister.jpg      <- put your photo here
└── output/              <- screenshots / exported video land here
```

## Setup

```bash
pip install -r requirements.txt
```

Replace `assets/sister.jpg` with your own photograph (any common format —
jpg, png, etc. — just keep the filename, or update `IMAGE_PATH` in
`main.py`). The image is never permanently down-scaled or recompressed:
it's loaded once at full resolution, and that same high-quality copy is
what's shown on screen and in any exported video.

## Run

```bash
python main.py
```

## Controls

| Key   | Action                                   |
|-------|-------------------------------------------|
| ESC   | Exit                                      |
| SPACE | Restart the animation                     |
| S     | Save a screenshot of the current frame    |
| F     | Toggle fullscreen                         |
| V     | Export the animation to `output/sister_reveal.mp4` |

## How the reveal works

The photo is divided into small blocks (`PIXEL_SIZE`, default 4px). Each
block is assigned a "reveal time" using a blend of four patterns so it
never looks like a simple left-to-right sweep:

- **Center-outward** — pixels near the middle of the photo appear first.
- **Edge-to-center** — pixels near the border appear first.
- **Clustered patches** — small groups of nearby blocks pop in together.
- **Scattered randomness** — the rest appear in organic random order.

Each block fades in smoothly (no hard on/off switch) and gets a subtle
glow while it's freshly appearing. Ambient particles drift in the
background throughout for atmosphere, with small particle bursts near
freshly-revealed areas.

Once 100% of the blocks are visible, the animation cross-fades into the
**true, full-resolution source photograph** (never the low-res preview
blocks), applies a gentle brightness lift and glow, and then fades in the
caption underneath, one letter at a time with slight letter-spacing.

## Configuration

All key settings are exposed at the top of `main.py`:

```python
IMAGE_PATH = "assets/sister.jpg"   # source photo
REVEAL_DURATION = 12               # seconds for the pixel reveal
PIXEL_SIZE = 4                     # reveal block size in pixels
FPS = 60                           # live animation frame rate
BACKGROUND_BRIGHTNESS = 5          # 0-255, canvas darkness
SHOW_PARTICLES = True
SHOW_GLOW = True
FINAL_TEXT = "My Sister, My Love"
PARTICLE_COUNT = 500
HOLD_DURATION = 6
TEXT_FADE_DURATION = 2.5
EXPORT_PATH = "output/sister_reveal.mp4"
EXPORT_FPS = 60
```

Feel free to adjust `REVEAL_DURATION`, `PIXEL_SIZE` and `PARTICLE_COUNT`
first — they have the biggest effect on look and feel.

## Exporting a video

Press **V** while the app is running, or call `export_video(...)` directly
from `main.py`. It renders the full animation offscreen frame-by-frame at
the same resolution as the live window and writes it with OpenCV to
`output/sister_reveal.mp4`. No audio is included — to add background
music afterward, merge the video and an audio track with ffmpeg:

```bash
ffmpeg -i output/sister_reveal.mp4 -i your_music.mp3 -c:v copy -shortest final_with_music.mp4
```

## Notes on quality

- The image is loaded once via Pillow at full resolution and kept as the
  single source of truth (`final_surf`) for the completed photo.
- The only down-sampled copy is a small in-memory grid used purely to
  decide the *color and position* of each reveal block — it is discarded
  once the reveal finishes, and the final frame always draws from the
  full-resolution image.
- Resizing uses Pillow's `LANCZOS` filter (high-quality anti-aliased
  resampling), and the image is never re-saved or JPEG-recompressed
  internally.
- The display window auto-selects the best supported resolution among
  3840×2160 / 2560×1440 / 1920×1080 and letterboxes/pillarboxes to keep
  the photo's original aspect ratio — it's never stretched.
