"""All tunable numbers in one place.

The Personality doc calls the BPM threshold and the 3 s attention window
"starting values to tune in pilot sessions" -- tune them here.
"""
import os
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class Config:
    # --- Heart rate ---------------------------------------------------------
    baseline_window_s: float = 60.0      # stage 0: seconds of stable BPM needed
    wake_on_first_heartbeat: bool = True # wake the moment a heartbeat is felt; the baseline is learned after (False: snore through the baseline first)
    baseline_max_std: float = 9.0        # "stable" = std below this (real MAX30102 readings swing ~±7 BPM)
    bpm_jump_threshold: float = 15.0     # jump vs. baseline that Reachy comments on
    bpm_short_jump: float = 10.0         # jump vs. the last 30 s (catches fast spikes mid-session)
    bpm_jump_cooldown_s: float = 25.0    # don't comment on every beat
    bpm_flat_window_s: float = 45.0      # long flat stretch -> Teasing
    bpm_flat_max_std: float = 1.5
    bpm_stop_limit: float = 130.0        # safety: above this ...
    bpm_stop_duration_s: float = 30.0    # ... for this long -> stop + sincere goodbye

    pulse_mode: str = "one"              # one | wake | two (see perception/pulse_sensor.py)
    finger_min: int = 20000              # IR level that counts as a finger (pulse_triple --finger-min)
    finger_lost_s: float = 5.0           # finger off the sensors this long -> Reachy asks for it back
    # Session flow v2, Act 1: a fingertip makes Reachy stir at once; it wakes at the first heartbeat,
    # or after this much contact in total (lifts included) if the heartbeat is hard to read.
    contact_wake_s: float = 10.0
    finger_glance_s: float = 1.5         # finger off this long -> Reachy glances at the sensor (no words)
    finger_doze_s: float = 20.0          # finger off this long -> Reachy gets sleepy, but the session goes on

    # What the facilitator UI tells the participant (Arduino setup: two finger sensors).
    prompts: dict = field(default_factory=lambda: {
        "baseline": "Place a finger gently on a pulse sensor and breathe normally. Reachy will hear your heart.",
        "wake": "Place a finger on a pulse sensor to bring Reachy to life.",
    })

    # --- Attention / camera -------------------------------------------------
    look_away_s: float = 3.0             # looking away this long -> Scolding
    camera_index: int = 0
    fer_model_path: str = "models/fer2013_final_model.pth"     # from kudosscience/fer_and_ter_model
    ter_model_dir: str = "models/ter_distilbert_model"          # from kudosscience/fer_and_ter_model
    fusion_weights: dict = field(default_factory=lambda: {"facial": 0.6, "textual": 0.4})

    # --- Conversation -------------------------------------------------------
    listen_timeout_s: float = 9.0        # silence this long -> Reachy takes the initiative
    short_answer_words: int = 4          # answers this short count as "short" -> Teasing
    long_answer_words: int = 14          # answers this long count as "engaged"
    max_questions_in_row: int = 2        # then Reachy must tell / react / share instead of asking
    max_provocations_in_row: int = 2     # doc rule: then a warm mode
    discomfort_limit: int = 2            # doc rule: 2x discomfort -> no more provocation
    # The agreed stop word is "pause"; a few translations are accepted too.
    # Only matches short utterances ("pause", "pause please"), see brain/safety.py.
    stop_words: tuple = ("pause", "pausa", "stop")

    # --- Stage timings (seconds, from the Interaction Protocol) ---------------
    stage_time: dict = field(default_factory=lambda: {
        0: 120, 1: 60, 2: 120, 3: 180, 4: 180, 5: 120, 6: 60, 7: 120})
    min_conversation_turns: int = 2      # stage 3 advance rule
    provocation_moves: int = 3           # stage 4 advance rule

    # --- LLM ------------------------------------------------------------------
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "low"              # low latency matters more than depth for live speech
    llm_max_tokens: int = 2000

    # --- Music (stage 5): language code -> audio file the team provides -------
    music_dir: str = "assets/music"
    music_seconds: float = 25.0

    # --- Hardware / storage --------------------------------------------------
    heart_port: str | None = None        # e.g. /dev/tty.usbmodem1101 (BIS_HEART_PORT)
    use_emotion_library: bool = True     # recorded emotions from the Pollen HF dataset
    whisper_model: str = "small"
    sessions_dir: str = "sessions"

    # --- Simulation -----------------------------------------------------------
    time_scale: float = 1.0              # >1 runs the session clock faster (sim only)
    seed: int = 7


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PATH_FIELDS = ("fer_model_path", "ter_model_dir", "music_dir", "sessions_dir")


def config_from_env() -> Config:
    """Override any Config field with an env var named BIS_<FIELD> (see .env.example)."""
    cfg = Config()
    for f in fields(Config):
        raw = os.environ.get(f"BIS_{f.name.upper()}")
        if raw is None or isinstance(getattr(cfg, f.name), (dict, tuple)):
            continue
        cur = getattr(cfg, f.name)
        if isinstance(cur, bool):
            val = raw.lower() in ("1", "true", "yes", "on")
        elif isinstance(cur, int):
            val = int(raw)
        elif isinstance(cur, float):
            val = float(raw)
        else:
            val = raw
        setattr(cfg, f.name, val)
    # Relative paths are relative to the project, whatever directory the app was started from.
    for name in PATH_FIELDS:
        path = Path(getattr(cfg, name)).expanduser()
        setattr(cfg, name, str(path if path.is_absolute() else PROJECT_ROOT / path))
    return cfg
