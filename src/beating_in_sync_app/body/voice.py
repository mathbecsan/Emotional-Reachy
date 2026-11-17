"""Speech output and music.

SimVoice prints the line (and waits roughly as long as speaking would take).
MacVoice uses macOS `say` with a voice per language -- good enough for
rehearsals; swap in a better multilingual TTS for the exhibition.
"""
import glob
import logging
import os
import shutil
import subprocess


logger = logging.getLogger(__name__)

MAC_VOICES = {"en": "Samantha", "es": "Paulina", "fr": "Thomas", "it": "Alice", "de": "Anna", "pt": "Luciana",
              "zh": "Tingting", "ja": "Kyoko", "ko": "Yuna", "hi": "Lekha", "ar": "Maged", "ru": "Milena",
              "tr": "Yelda", "vi": "Linh"}


class SimVoice:
    def __init__(self, clock):
        self.clock = clock

    def say(self, text, lang="en", rate=1.0, mode=""):
        logger.info("REACHY (%s, %s)> %s", mode, lang, text)
        self.clock.sleep(len(text.split()) * 0.33 / rate)

    def play_music(self, path, seconds):
        logger.info("music: %s for %.0fs", path or "(no file for this language)", seconds)
        return None

    def stop_music(self, handle):
        pass


class MacVoice(SimVoice):
    def say(self, text, lang="en", rate=1.0, mode=""):
        logger.info("REACHY (%s, %s)> %s", mode, lang, text)
        voice = MAC_VOICES.get(lang)
        cmd = ["say", "-r", str(int(185 * rate))] + (["-v", voice] if voice else []) + [text]
        subprocess.run(cmd, check=False)

    def play_music(self, path, seconds):
        if path and shutil.which("afplay"):
            return subprocess.Popen(["afplay", "-t", str(seconds), path])
        return super().play_music(path, seconds)

    def stop_music(self, handle):
        if handle:
            handle.terminate()


def music_for(lang, music_dir):
    """assets/music/<lang>.(mp3|wav|m4a), else assets/music/default.*"""
    for stem in (lang, "default"):
        hits = glob.glob(os.path.join(music_dir, f"{stem}.*"))
        if hits:
            return hits[0]
    return None
