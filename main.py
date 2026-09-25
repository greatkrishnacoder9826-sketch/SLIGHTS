"""
Cinematic Pixel-by-Pixel Photo Reveal Animation
=================================================

Reconstructs a photograph from thousands of tiny pixel-blocks in a
premium, cinematic animation, then displays it in full quality with
an emotional caption underneath.

Usage:
    pip install -r requirements.txt
    python main.py

Controls (while the window is focused):
    ESC   -> Exit
    SPACE -> Restart the animation
    S     -> Save a screenshot of the current frame
    F     -> Toggle fullscreen
    V     -> Export the animation to output/sister_reveal.mp4
"""

import os
import sys
import math
import random
import time

import numpy as np
import pygame
from PIL import Image

# ----------------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------------

# Path to the source photograph. Replace this file with your own photo.
IMAGE_PATH = "assets/sister.jpg"

# How long (in seconds) the pixel-reveal stage takes, before the
# final high-quality image snaps into place.
REVEAL_DURATION = 12

# Size (in screen pixels) of each reveal "block". Smaller = more
# blocks = finer, slower-feeling reveal but higher fidelity motion.
# This only affects the *reveal animation*; the final image is always
# shown at full source resolution.
PIXEL_SIZE = 4

# Target frame rate for the live animation.
FPS = 60

# Brightness (0-255) of the background canvas during Stage 1/2.
BACKGROUND_BRIGHTNESS = 5

# Toggle optional visual effects.
SHOW_PARTICLES = True
SHOW_GLOW = True

# Caption shown beneath the completed photograph.
FINAL_TEXT = "My Sister, My Love"

# Number of ambient background particles (Stage 1 atmosphere).
PARTICLE_COUNT = 500

# How long (seconds) the completed photo + text stay on screen
# before the loop simply holds (user can still restart with SPACE).
HOLD_DURATION = 6

# Seconds spent fading the caption in after the photo completes.
TEXT_FADE_DURATION = 2.5

# Output video path if the user exports the animation.
EXPORT_PATH = "output/sister_reveal.mp4"
EXPORT_FPS = 60


# ----------------------------------------------------------------------
# IMAGE LOADING
# ----------------------------------------------------------------------

def load_image(path):
    """Load the source photograph at full quality, preserving color and
    aspect ratio. Returns an RGB numpy array (H, W, 3) uint8."""
    if not os.path.exists(path):
        print("Image not found.")
        print("Please place your photograph inside:")
        print("    assets/sister.jpg")
        sys.exit(1)

    try:
        img = Image.open(path)
        img = img.convert("RGB")  # drop alpha / palette, preserve color
    except Exception as exc:
        print(f"Could not open the image file: {exc}")
        sys.exit(1)

    return np.array(img)  # (H, W, 3) uint8, full original resolution


def compute_display_size(img_w, img_h):
    """Pick the best display resolution (capped at the desktop size)
    while preserving the photo's aspect ratio, then compute the
    letterboxed target rect within that window."""
    info = pygame.display.Info()
    desktop_w, desktop_h = info.current_w, info.current_h

    # Prefer common resolutions, capped to what the desktop can show.
    candidates = [(3840, 2160), (2560, 1440), (1920, 1080)]
    win_w, win_h = 1920, 1080
    for cw, ch in candidates:
        if cw <= desktop_w and ch <= desktop_h:
            win_w, win_h = cw, ch
            break
    else:
        win_w, win_h = min(1920, desktop_w), min(1080, desktop_h)

    # Fit the image into the window without stretching (letterbox/pillarbox).
    scale = min(win_w / img_w, win_h / img_h)
    fit_w, fit_h = int(img_w * scale), int(img_h * scale)
    off_x, off_y = (win_w - fit_w) // 2, (win_h - fit_h) // 2

    return win_w, win_h, fit_w, fit_h, off_x, off_y


# ----------------------------------------------------------------------
# PIXEL BLOCK PREPARATION
# ----------------------------------------------------------------------

class PixelBlock:
    """A single reveal unit: a rectangular block of the down-scaled
    preview image, with its own reveal time and fade-in progress."""
    __slots__ = ("x", "y", "w", "h", "color", "reveal_t", "alpha", "dist")

    def __init__(self, x, y, w, h, color, dist):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.color = color
        self.dist = dist       # normalized distance used for ordering
        self.reveal_t = 0.0    # progress fraction [0,1] at which this block starts revealing
        self.alpha = 0         # current opacity 0-255


def prepare_pixels(display_rgb, fit_w, fit_h, block_size):
    """Down-sample the (already fit-sized) display image into a grid of
    PixelBlocks used purely for the reveal animation. The final image
    itself is drawn separately at full resolution."""
    small = Image.fromarray(display_rgb).resize(
        (max(1, fit_w // block_size), max(1, fit_h // block_size)),
        Image.LANCZOS,
    )
    small_arr = np.array(small)
    gh, gw = small_arr.shape[0], small_arr.shape[1]

    blocks = []
    cx, cy = gw / 2.0, gh / 2.0
    max_dist = math.hypot(cx, cy)

    for gy in range(gh):
        for gx in range(gw):
            color = tuple(int(c) for c in small_arr[gy, gx])
            px, py = gx * block_size, gy * block_size
            dist = math.hypot(gx - cx, gy - cy) / max_dist if max_dist > 0 else 0
            blocks.append(PixelBlock(px, py, block_size, block_size, color, dist))

    return blocks, gw, gh


def generate_reveal_order(blocks):
    """Assign each block a reveal_t in [0,1) using a sophisticated blend
    of center-outward, edge-to-center, scattered random and small
    clustered reveals, rather than a simple left-to-right sweep."""
    n = len(blocks)
    if n == 0:
        return

    # Split blocks into behavioural groups so several patterns overlap.
    indices = list(range(n))
    random.shuffle(indices)

    group_center_out = indices[: int(n * 0.35)]
    group_edge_in = indices[int(n * 0.35): int(n * 0.60)]
    group_clusters = indices[int(n * 0.60): int(n * 0.80)]
    group_random = indices[int(n * 0.80):]

    # Center-outward: blocks near the middle reveal earliest.
    for i in group_center_out:
        b = blocks[i]
        jitter = random.uniform(-0.03, 0.03)
        blocks[i].reveal_t = max(0.0, min(0.9, b.dist * 0.9 + jitter))

    # Edge-to-center: blocks near the edges reveal earliest.
    for i in group_edge_in:
        b = blocks[i]
        jitter = random.uniform(-0.03, 0.03)
        blocks[i].reveal_t = max(0.0, min(0.9, (1.0 - b.dist) * 0.9 + jitter))

    # Small clusters: group nearby blocks (by scanning order) so patches
    # of the image "pop in" together rather than pixel-by-pixel noise.
    cluster_size = 24
    for start in range(0, len(group_clusters), cluster_size):
        chunk = group_clusters[start:start + cluster_size]
        base_t = random.uniform(0.05, 0.85)
        for i in chunk:
            blocks[i].reveal_t = max(0.0, min(0.95, base_t + random.uniform(-0.02, 0.02)))

    # Pure scattered randomness for the remainder, for an organic feel.
    for i in group_random:
        blocks[i].reveal_t = random.uniform(0.0, 0.95)


# ----------------------------------------------------------------------
# PARTICLES
# ----------------------------------------------------------------------

class Particle:
    """A small ambient or burst particle used for atmosphere."""
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color")

    def __init__(self, x, y, vx, vy, life, size, color):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = life
        self.max_life = life
        self.size = size
        self.color = color

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0

    def alpha(self):
        return max(0, min(255, int(255 * (self.life / self.max_life))))


def make_ambient_particles(win_w, win_h, count):
    particles = []
    for _ in range(count):
        x, y = random.uniform(0, win_w), random.uniform(0, win_h)
        vx, vy = random.uniform(-4, 4), random.uniform(-6, -1)
        life = random.uniform(3, 8)
        size = random.uniform(1, 2.2)
        brightness = random.randint(60, 160)
        particles.append(Particle(x, y, vx, vy, life, size, (brightness,) * 3))
    return particles


def spawn_burst(x, y, count=4):
    burst = []
    for _ in range(count):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(10, 40)
        vx, vy = math.cos(angle) * speed, math.sin(angle) * speed
        life = random.uniform(0.25, 0.6)
        size = random.uniform(1, 2.5)
        burst.append(Particle(x, y, vx, vy, life, size, (255, 240, 210)))
    return burst


# ----------------------------------------------------------------------
# DRAWING
# ----------------------------------------------------------------------

def draw_particles(surface, particles):
    for p in particles:
        a = p.alpha()
        if a <= 0:
            continue
        r, g, b = p.color
        s = int(p.size)
        pygame.draw.circle(surface, (r, g, b), (int(p.x), int(p.y)), max(1, s))


def draw_pixels(surface, blocks, progress, off_x, off_y, glow_enabled):
    """Draw all pixel blocks whose reveal_t has been reached, fading
    each one in smoothly rather than snapping to full opacity."""
    fade_window = 0.06  # fraction of progress over which a block fades in
    glow_layer = None
    if glow_enabled:
        glow_layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

    for b in blocks:
        if progress < b.reveal_t:
            continue
        t = (progress - b.reveal_t) / fade_window
        alpha = 255 if t >= 1.0 else max(0, min(255, int(255 * t)))
        if alpha <= 0:
            continue

        rect = (off_x + b.x, off_y + b.y, b.w, b.h)
        color_surf = pygame.Surface((b.w, b.h))
        color_surf.fill(b.color)
        color_surf.set_alpha(alpha)
        surface.blit(color_surf, rect[:2])

        # Subtle glow for freshly appeared blocks only.
        if glow_layer is not None and t < 1.0:
            glow_alpha = int(90 * (1.0 - t))
            if glow_alpha > 0:
                glow_rect = pygame.Rect(rect[0] - 2, rect[1] - 2, b.w + 4, b.h + 4)
                pygame.draw.rect(glow_layer, (*b.color, glow_alpha), glow_rect)

    if glow_layer is not None:
        surface.blit(glow_layer, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)


def draw_final_image(surface, final_surf, off_x, off_y, brighten=0.0):
    """Blit the true, full-resolution source photograph. `brighten`
    (0-1) adds a subtle cinematic brightness lift on completion."""
    surface.blit(final_surf, (off_x, off_y))
    if brighten > 0:
        overlay = pygame.Surface(final_surf.get_size(), pygame.SRCALPHA)
        overlay.fill((255, 255, 255, int(40 * brighten)))
        surface.blit(overlay, (off_x, off_y), special_flags=pygame.BLEND_RGBA_ADD)


def draw_final_text(surface, font, text, win_w, text_y, fade_progress, spacing_extra=0):
    """Draw the caption with a fade-in and very subtle letter-spacing
    animation, plus a soft glow."""
    alpha = max(0, min(255, int(255 * fade_progress)))
    if alpha <= 0:
        return

    # Render each letter separately to allow subtle letter-spacing.
    letters = [font.render(ch, True, (255, 235, 225)) for ch in text]
    spacing = 2 + spacing_extra
    total_w = sum(l.get_width() for l in letters) + spacing * (len(letters) - 1)
    x = (win_w - total_w) // 2

    # Soft glow pass behind the text.
    glow_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    gx = x
    for letter in letters:
        glow_letter = pygame.transform.smoothscale(
            letter, (int(letter.get_width() * 1.15), int(letter.get_height() * 1.15))
        )
        glow_letter.set_alpha(int(alpha * 0.35))
        glow_surf.blit(glow_letter, (gx - 4, text_y - 4))
        gx += letter.get_width() + spacing
    surface.blit(glow_surf, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

    gx = x
    for letter in letters:
        letter.set_alpha(alpha)
        surface.blit(letter, (gx, text_y))
        gx += letter.get_width() + spacing


# ----------------------------------------------------------------------
# EASING
# ----------------------------------------------------------------------

def ease_out_cubic(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


# ----------------------------------------------------------------------
# VIDEO EXPORT
# ----------------------------------------------------------------------

def export_video(blocks, final_surf, win_w, win_h, off_x, off_y, font,
                  reveal_duration, fps, path):
    """Render the full animation offscreen and write it to an MP4 file
    using OpenCV, at the same resolution and quality as the live show."""
    try:
        import cv2
    except ImportError:
        print("OpenCV (opencv-python) is required for video export.")
        print("Install it with: pip install opencv-python")
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)
    writer = cv2.VideoWriter(
        path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (win_w, win_h)
    )

    surface = pygame.Surface((win_w, win_h))
    total_frames = int(reveal_duration * fps) + int((TEXT_FADE_DURATION + 2) * fps)
    text_y = off_y + final_surf.get_height() + 40

    print(f"Exporting {total_frames} frames to {path} ...")
    for frame_i in range(total_frames):
        t = frame_i / fps
        surface.fill((BACKGROUND_BRIGHTNESS,) * 3)

        reveal_progress = ease_out_cubic(min(1.0, t / reveal_duration))
        draw_pixels(surface, blocks, reveal_progress, off_x, off_y, SHOW_GLOW)

        if reveal_progress >= 1.0:
            brighten = min(1.0, (t - reveal_duration) / 1.0) if t > reveal_duration else 0
            draw_final_image(surface, final_surf, off_x, off_y, brighten)
            fade_t = max(0.0, min(1.0, (t - reveal_duration) / TEXT_FADE_DURATION))
            draw_final_text(surface, font, FINAL_TEXT, win_w, text_y, fade_t)

        frame_arr = pygame.surfarray.array3d(surface)
        frame_arr = np.transpose(frame_arr, (1, 0, 2))  # (H, W, 3)
        frame_bgr = frame_arr[:, :, ::-1]  # RGB -> BGR for OpenCV
        writer.write(frame_bgr.astype(np.uint8))

        if frame_i % fps == 0:
            print(f"  {frame_i // fps}s / {total_frames // fps}s rendered")

    writer.release()
    print(f"Export complete: {path}")
    print("Note: no audio track is included. To add background music,")
    print("merge the exported video with an audio file using ffmpeg, e.g.:")
    print(f'  ffmpeg -i "{path}" -i your_music.mp3 -c:v copy -shortest final.mp4')


# ----------------------------------------------------------------------
# MAIN APPLICATION
# ----------------------------------------------------------------------

def main():
    pygame.init()
    pygame.display.set_caption("A Memory, Rebuilt")

    print("Preparing your memory...")

    source_rgb = load_image(IMAGE_PATH)
    img_h, img_w = source_rgb.shape[0], source_rgb.shape[1]

    win_w, win_h, fit_w, fit_h, off_x, off_y = compute_display_size(img_w, img_h)
    screen = pygame.display.set_mode((win_w, win_h))

    # High-quality resize for the on-screen display copy (source data
    # itself is never modified or re-compressed).
    display_pil = Image.fromarray(source_rgb).resize((fit_w, fit_h), Image.LANCZOS)
    display_rgb = np.array(display_pil)
    final_surf = pygame.image.frombuffer(
        display_rgb.tobytes(), (fit_w, fit_h), "RGB"
    ).convert()

    blocks, gw, gh = prepare_pixels(display_rgb, fit_w, fit_h, PIXEL_SIZE)
    generate_reveal_order(blocks)
    print(f"Prepared {len(blocks)} reveal blocks ({gw}x{gh} grid).")

    font_path = pygame.font.match_font("georgia") or pygame.font.match_font("serif")
    font = pygame.font.Font(font_path, max(20, fit_h // 22))

    clock = pygame.time.Clock()
    ambient = make_ambient_particles(win_w, win_h, PARTICLE_COUNT) if SHOW_PARTICLES else []
    bursts = []

    start_time = time.time()
    fullscreen = False
    text_y = off_y + fit_h + 40
    running = True

    while running:
        dt = clock.tick(FPS) / 1000.0
        elapsed = time.time() - start_time
        raw_progress = min(1.0, elapsed / REVEAL_DURATION)
        progress = ease_out_cubic(raw_progress)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    start_time = time.time()
                    for b in blocks:
                        b.alpha = 0
                elif event.key == pygame.K_s:
                    os.makedirs("output", exist_ok=True)
                    shot_path = f"output/screenshot_{int(time.time())}.png"
                    pygame.image.save(screen, shot_path)
                    print(f"Saved screenshot: {shot_path}")
                elif event.key == pygame.K_f:
                    fullscreen = not fullscreen
                    flags = pygame.FULLSCREEN if fullscreen else 0
                    screen = pygame.display.set_mode((win_w, win_h), flags)
                elif event.key == pygame.K_v:
                    export_video(blocks, final_surf, win_w, win_h, off_x, off_y,
                                 font, REVEAL_DURATION, EXPORT_FPS, EXPORT_PATH)

        screen.fill((BACKGROUND_BRIGHTNESS,) * 3)

        if SHOW_PARTICLES:
            ambient = [p for p in ambient if p.update(dt)]
            while len(ambient) < PARTICLE_COUNT:
                ambient.extend(make_ambient_particles(win_w, win_h, 1))
            draw_particles(screen, ambient)

            # Occasionally spawn a small burst near a freshly revealed area.
            if raw_progress < 1.0 and random.random() < 0.4:
                bx = off_x + random.uniform(0, fit_w)
                by = off_y + random.uniform(0, fit_h)
                bursts.extend(spawn_burst(bx, by, count=3))
            bursts = [p for p in bursts if p.update(dt)]
            draw_particles(screen, bursts)

        if raw_progress < 1.0:
            draw_pixels(screen, blocks, progress, off_x, off_y, SHOW_GLOW)
            fade_progress = 0.0
        else:
            hold_elapsed = elapsed - REVEAL_DURATION
            brighten = min(1.0, hold_elapsed / 1.0)
            draw_final_image(screen, final_surf, off_x, off_y, brighten)
            fade_progress = max(0.0, min(1.0, hold_elapsed / TEXT_FADE_DURATION))

        draw_final_text(screen, font, FINAL_TEXT, win_w, text_y, fade_progress)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
