"""
Strinova Discord Rich Presence
Captures game screenshots, reads weapon name via OCR, maps to character,
and displays character info + match timer on Discord.
"""

import json
import time
import sys
import os
import re
import logging
from datetime import datetime, timezone
from difflib import get_close_matches

import mss
import mss.tools
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract
from pypresence import Presence, exceptions as rpc_exceptions

# ─── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("strinova-rpc")


# ─── Config Loader ──────────────────────────────────────────────────────────────

def load_json(path: str) -> dict:
    """Load a JSON file relative to the script or executable directory."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller exe
        base = os.path.dirname(sys.executable)
    else:
        # Running as script
        base = os.path.dirname(os.path.abspath(__file__))
    
    full = os.path.join(base, path)
    with open(full, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── Screen Capture ─────────────────────────────────────────────────────────────

class ScreenCapture:
    """Captures regions of the primary monitor (full-screen game)."""

    def __init__(self, config: dict):
        self.interval = config["screenshot"]["interval_seconds"]
        self.window_title = config["screenshot"]["window_title"]
        self.regions_cfg = config["regions"]
        self.sct = mss.mss()

    def _monitor(self) -> dict:
        """Return the primary monitor geometry."""
        return self.sct.monitors[1]  # primary monitor (index 0 = all monitors)

    def grab_region(self, region_key: str) -> Image.Image:
        """
        Grab a sub-region of the screen.
        Region is defined as fractional coordinates in config.json.
        """
        mon = self._monitor()
        w, h = mon["width"], mon["height"]
        region = self.regions_cfg[region_key]

        left = int(region["left"] * w) + mon["left"]
        top = int(region["top"] * h) + mon["top"]
        right = int(region["right"] * w) + mon["left"]
        bottom = int(region["bottom"] * h) + mon["top"]

        bbox = {"left": left, "top": top, "width": right - left, "height": bottom - top}
        raw = self.sct.grab(bbox)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


# ─── OCR Reader ─────────────────────────────────────────────────────────────────

class OCRReader:
    """Reads text from cropped game screenshot regions using Tesseract OCR."""

    def __init__(self, config: dict, weapon_names: list[str]):
        ocr_cfg = config["ocr"]
        self.confidence = ocr_cfg["confidence_threshold"]
        pytesseract.pytesseract.tesseract_cmd = ocr_cfg["tesseract_path"]
        self.weapon_names = weapon_names

    @staticmethod
    def _preprocess(image: Image.Image, upscale: int = 3) -> Image.Image:
        """Enhance a cropped screenshot for better OCR accuracy."""
        # Upscale
        w, h = image.size
        image = image.resize((w * upscale, h * upscale), Image.LANCZOS)
        # Grayscale
        image = image.convert("L")
        # Increase contrast
        image = ImageEnhance.Contrast(image).enhance(2.5)
        # Sharpen
        image = image.filter(ImageFilter.SHARPEN)
        return image

    def read_text(self, image: Image.Image) -> str:
        """Run OCR on an image region and return the cleaned text."""
        processed = self._preprocess(image)
        raw = pytesseract.image_to_string(
            processed,
            config="--psm 7 --oem 3",  # single line mode
        )
        return raw.strip()

    def read_weapon_name(self, image: Image.Image) -> str | None:
        """
        Read weapon name from the bottom-right region of the screen.
        Uses fuzzy matching against known weapon names for robustness.
        """
        raw_text = self.read_text(image)
        if not raw_text:
            return None

        log.debug(f"OCR weapon raw: '{raw_text}'")

        # Exact match first
        for name in self.weapon_names:
            if name.lower() == raw_text.lower():
                return name

        # Fuzzy match
        matches = get_close_matches(raw_text, self.weapon_names, n=1, cutoff=self.confidence)
        if matches:
            log.debug(f"Fuzzy matched '{raw_text}' → '{matches[0]}'")
            return matches[0]

        log.debug(f"No weapon match for OCR text: '{raw_text}'")
        return None

    def read_match_info(self, image: Image.Image) -> dict:
        """
        Read match info from the top-center region.
        Looks for 'Objective' text and timer (MM:SS format).
        Returns dict with keys: 'has_objective', 'timer_text'
        """
        processed = self._preprocess(image, upscale=2)
        raw = pytesseract.image_to_string(
            processed,
            config="--psm 6 --oem 3",
        )
        text = raw.strip()
        log.debug(f"OCR match info raw: '{text}'")

        result = {
            "has_objective": False,
            "timer_text": None,
        }

        # Detect "Objective" keyword (case-insensitive, fuzzy)
        text_lower = text.lower()
        if "objective" in text_lower or "objectiv" in text_lower:
            result["has_objective"] = True

        # Extract timer in MM:SS or M:SS format
        timer_match = re.search(r"(\d{1,2}:\d{2})", text)
        if timer_match:
            result["timer_text"] = timer_match.group(1)

        return result


# ─── Match Tracker ──────────────────────────────────────────────────────────────

class MatchTracker:
    """Tracks match state: whether in a match, elapsed time, countdown."""

    def __init__(self, config: dict):
        match_cfg = config.get("match", {})
        self.round_duration = match_cfg.get("round_duration_seconds", 120)
        self.max_rounds = match_cfg.get("max_rounds", 13)
        self._streak_threshold = match_cfg.get("objective_verification_count", 3)

        self.in_match = False
        self.match_start_time: float | None = None
        self._no_objective_streak = 0

    def update(self, match_info: dict) -> None:
        """Update match state based on OCR match info."""
        has_objective = match_info.get("has_objective", False)

        if has_objective and not self.in_match:
            # Match just started
            self.in_match = True
            self.match_start_time = time.time()
            self._no_objective_streak = 0
            log.info("🎮 Match detected — starting timer")

        elif has_objective and self.in_match:
            # Still in a match
            self._no_objective_streak = 0

        elif not has_objective and self.in_match:
            # Objective disappeared — could be between rounds or match ended
            self._no_objective_streak += 1
            if self._no_objective_streak >= self._streak_threshold:
                self.in_match = False
                self.match_start_time = None
                self._no_objective_streak = 0
                log.info("🏁 Match ended — resetting timer")

    @property
    def elapsed_seconds(self) -> int | None:
        """Seconds since match started, or None if not in a match."""
        if self.match_start_time is None:
            return None
        return int(time.time() - self.match_start_time)

    @property
    def start_timestamp(self) -> float | None:
        """Unix timestamp of when the match started (for Discord elapsed)."""
        return self.match_start_time


# ─── Discord RPC ────────────────────────────────────────────────────────────────

class DiscordRPC:
    """Manages Discord Rich Presence connection and updates."""

    def __init__(self, config: dict, character_icons: dict):
        self.client_id = config["discord"]["client_id"]
        self.small_image = config["discord"].get("small_image", "strinova_logo")
        self.large_text = config["discord"].get("large_text", "Strinova")
        self.display = config["display_options"]
        self.character_icons = character_icons

        self.rpc: Presence | None = None
        self.connected = False

    def connect(self) -> bool:
        """Connect to Discord RPC. Returns True on success."""
        try:
            self.rpc = Presence(self.client_id)
            self.rpc.connect()
            self.connected = True
            log.info("✅ Connected to Discord RPC")
            return True
        except Exception as e:
            log.error(f"❌ Failed to connect to Discord: {e}")
            self.connected = False
            return False

    def update(
        self,
        character_name: str | None = None,
        match_start_ts: float | None = None,
    ) -> None:
        """Push an update to Discord Rich Presence."""
        if not self.connected or self.rpc is None:
            return

        kwargs: dict = {}

        # Character info — character icon as large (main) image, Strinova logo as small overlay
        if character_name and self.display.get("show_character", True):
            icon_key = self.character_icons.get(character_name)
            if icon_key:
                kwargs["large_image"] = icon_key
                kwargs["large_text"] = character_name
            else:
                kwargs["large_image"] = self.small_image
                kwargs["large_text"] = self.large_text
            # Strinova logo as small overlay
            kwargs["small_image"] = self.small_image
            kwargs["small_text"] = self.large_text
            kwargs["details"] = f"Playing as {character_name}"
        else:
            kwargs["large_image"] = self.small_image
            kwargs["large_text"] = self.large_text
            kwargs["details"] = "In Game"

        # Match timer (elapsed from start)
        if match_start_ts and self.display.get("show_timer", True):
            # pypresence uses epoch timestamps for elapsed display
            kwargs["start"] = int(match_start_ts)
            kwargs["state"] = "In Match"
        else:
            kwargs["state"] = "In Menu"

        try:
            self.rpc.update(**kwargs)
        except rpc_exceptions.InvalidID:
            log.warning("Discord RPC update failed — invalid ID, reconnecting...")
            self.connected = False
        except Exception as e:
            log.warning(f"Discord RPC update failed: {e}")

    def disconnect(self) -> None:
        """Close the RPC connection."""
        if self.rpc:
            try:
                self.rpc.clear()
            except Exception:
                pass

            try:
                self.rpc.close()
            except Exception:
                pass
            self.connected = False
            log.info("Disconnected from Discord RPC")


# ─── Main ───────────────────────────────────────────────────────────────────────

def main():
    log.info("╔══════════════════════════════════════╗")
    log.info("║   Strinova Discord Rich Presence     ║")
    log.info("╚══════════════════════════════════════╝")

    # Load configs
    config = load_json("config.json")
    weapon_map = load_json("character_weapon_map.json")
    character_icons = load_json("character_icons.json")
    weapon_names = list(weapon_map.keys())

    log.info(f"Loaded {len(weapon_map)} weapon→character mappings")

    # Initialize components
    capture = ScreenCapture(config)
    ocr = OCRReader(config, weapon_names)
    tracker = MatchTracker(config)
    discord = DiscordRPC(config, character_icons)

    # Connect to Discord (retry loop)
    while not discord.connect():
        log.info("Retrying Discord connection in 10 seconds...")
        time.sleep(10)

    # State
    current_character: str | None = None
    interval = config["screenshot"]["interval_seconds"]

    log.info(f"Monitoring every {interval}s — press Ctrl+C to stop")

    try:
        while True:
            try:
                # 1. Capture weapon name region → OCR → lookup character
                weapon_img = capture.grab_region("weapon_name")
                weapon_name = ocr.read_weapon_name(weapon_img)

                if weapon_name:
                    char = weapon_map.get(weapon_name)
                    if char and char != current_character:
                        current_character = char
                        log.info(f"🔫 Weapon: {weapon_name} → Character: {current_character}")

                # 2. Capture match info region → OCR → detect objective + timer
                match_img = capture.grab_region("match_info")
                match_info = ocr.read_match_info(match_img)
                tracker.update(match_info)

                # Reset character if match has ended (e.g. back in menu)
                if not tracker.in_match:
                    current_character = None

                # 4. Update Discord presence
                discord.update(
                    character_name=current_character,
                    match_start_ts=tracker.start_timestamp,
                )

                # 5. Reconnect if needed
                if not discord.connected:
                    log.info("Attempting to reconnect to Discord...")
                    discord.connect()

            except Exception as e:
                log.error(f"Error in main loop: {e}")

            time.sleep(interval)

    except KeyboardInterrupt:
        log.info("\n👋 Shutting down...")
    finally:
        discord.disconnect()


if __name__ == "__main__":
    main()
