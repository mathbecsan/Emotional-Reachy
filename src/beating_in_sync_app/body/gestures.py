"""Body language for each mode, as keyframes for Reachy Mini.

Pose = head (x/y/z mm, roll/pitch/yaw deg), antennas (left, right deg;
0 = upright, + = forward/down), body_yaw deg, duration s.
Pitch > 0 looks down, < 0 looks up ("nose up"); z > 0 lifts / leans the head.
Values are starting points -- tune them on the robot.
"""
from dataclasses import dataclass


@dataclass
class Pose:
    roll: float = 0; pitch: float = 0; yaw: float = 0
    z: float = 0; x: float = 0
    ant: tuple = (0, 0)
    body_yaw: float = 0
    dur: float = 0.6


NEUTRAL = Pose(dur=0.8)

GESTURES = {
    # Head down, slow sway, antennas drooped
    "sleepy": [Pose(pitch=28, z=-12, ant=(70, 70), roll=-4, dur=2.0), Pose(pitch=30, z=-14, ant=(75, 72), roll=5, dur=2.5)],
    # Snoring: slow inhale / exhale around the sleep pose, antennas twitch on the exhale
    "snore": [Pose(pitch=24, z=-9, ant=(66, 70), dur=1.6), Pose(pitch=30, z=-15, ant=(78, 74), dur=2.0),
              Pose(pitch=30, z=-15, ant=(72, 80), dur=0.3)],
    # Wake-up: head lifts slowly, antennas twitch, stretch
    "wake": [Pose(pitch=25, z=-10, ant=(60, 60), dur=1.5), Pose(pitch=0, z=6, ant=(20, 20), dur=2.0),
             Pose(pitch=-12, z=12, ant=(-25, -25), roll=6, dur=1.0), Pose(ant=(5, -10), dur=0.3), Pose(ant=(-10, 5), dur=0.3), NEUTRAL],
    # Head tilts side to side, antennas perk up
    "curious": [Pose(roll=14, ant=(-20, -20), dur=0.6), Pose(roll=-12, ant=(-15, -25), dur=0.7), Pose(roll=8, ant=(-20, -20), dur=0.6)],
    "excited": [Pose(z=10, pitch=-8, ant=(-35, -35), dur=0.3), Pose(z=4, ant=(-10, -40), dur=0.25), Pose(z=10, ant=(-40, -10), dur=0.25), Pose(z=6, ant=(-30, -30), dur=0.3)],
    # Slow lean in, head tilt, antennas wiggle softly
    "flirty": [Pose(x=12, z=4, roll=12, pitch=6, ant=(-5, -5), dur=1.6), Pose(x=14, roll=14, ant=(-15, 0), dur=0.5), Pose(x=14, roll=14, ant=(0, -15), dur=0.5), Pose(x=12, roll=10, ant=(-8, -8), dur=0.6)],
    # Head pulls back, quick antenna flick
    "teasing": [Pose(x=-10, pitch=-6, roll=-6, dur=0.35), Pose(x=-10, ant=(-40, -40), dur=0.15), Pose(x=-8, ant=(10, 10), dur=0.2), Pose(x=-4, yaw=8, dur=0.5)],
    # Sharp turn away, nose up, antennas flat
    "offended": [Pose(yaw=-35, body_yaw=-25, pitch=-15, ant=(85, 85), dur=0.35), Pose(yaw=-38, body_yaw=-28, pitch=-18, ant=(88, 88), dur=1.8)],
    # Fast snap back to face user, antennas stiff, small forward jolt
    "scolding": [Pose(yaw=0, body_yaw=0, ant=(-45, -45), dur=0.2), Pose(x=15, z=3, ant=(-45, -45), dur=0.15), Pose(x=6, ant=(-40, -40), dur=0.4)],
    # Very slow, soft motion, head bows, antennas lower gently
    "sincere": [Pose(pitch=12, z=-2, ant=(30, 30), dur=2.5), Pose(pitch=8, roll=4, ant=(25, 25), dur=2.0)],
    # Listening backchannel: small nod
    "listen": [Pose(pitch=6, roll=3, dur=0.4), Pose(pitch=-2, roll=3, dur=0.4)],
    "think": [Pose(roll=-8, pitch=-10, yaw=10, ant=(-5, 15), dur=0.7)],
    # Look back at the participant
    "attend": [Pose(yaw=0, body_yaw=0, dur=0.5)],
    "to_sleep": [Pose(pitch=10, ant=(30, 30), dur=1.5), Pose(pitch=28, z=-12, ant=(70, 70), dur=2.5)],
}


def dance_moves(bpm: float = 100, seconds: float = 8):
    """Head bob on the beat, antennas alternate, body sways every bar."""
    beat = 60.0 / bpm
    seq, t, i = [], 0.0, 0
    while t < seconds:
        up = i % 2 == 0
        seq.append(Pose(z=8 if up else -2, roll=10 if (i // 2) % 2 else -10,
                        ant=(-40, 10) if up else (10, -40), body_yaw=15 if (i // 4) % 2 else -15, dur=beat))
        t += beat
        i += 1
    return seq + [NEUTRAL]


# ---------------------------------------------------------------- Off-Brand Reachy gestures
# From "Off-Brand Reachy: Persona Script & App Spec" (express.py). Keyframes there are
# (seconds, x, z, roll, pitch, yaw, antenna_right, antenna_left, body_yaw) with positive
# antennas = raised; ours use positive = drooped, so the sign flips. Head yaw stays within
# 60 deg of the body (SDK limit 65), body yaw within +-160.
_R = (0.6, 0, 0, 0, 0, 0, 0, 0, 0)
_EXPRESS = {
    "nod_yes": [(0.25, 0, 0, 0, 15, 0, 10, 10, 0), (0.25, 0, 0, 0, -5, 0, 10, 10, 0), (0.25, 0, 0, 0, 12, 0, 10, 10, 0), _R],
    "shake_no": [(0.25, 0, 0, 0, 0, 25, 0, 0, 0), (0.3, 0, 0, 0, 0, -25, 0, 0, 0), (0.3, 0, 0, 0, 0, 20, 0, 0, 0), _R],
    "curious_tilt": [(0.5, 5, 0, 20, -5, 0, 30, 0, 0), (1.0, 5, 0, 20, -5, 0, 30, 0, 0), _R],
    "perk_up": [(0.3, 0, 12, 0, -12, 0, 45, 45, 0), (0.8, 0, 12, 0, -12, 0, 45, 45, 0), _R],
    "antenna_wave": [(0.2, 0, 0, 0, 0, 0, 50, -20, 0), (0.2, 0, 0, 0, 0, 0, -20, 50, 0), (0.2, 0, 0, 0, 0, 0, 50, -20, 0), (0.2, 0, 0, 0, 0, 0, -20, 50, 0), _R],
    "double_take": [(0.3, 0, 0, 0, 0, 35, 0, 0, 0), (0.15, 0, 0, 0, 0, 0, 0, 0, 0), (0.15, 0, 0, 0, 0, 35, 0, 0, 0), (0.2, 8, 8, 0, -10, 0, 40, 40, 0), _R],
    "lean_in": [(0.6, 15, -5, 0, 10, 0, 25, 25, 0), (1.2, 15, -5, 0, 10, 0, 25, 25, 0), _R],
    "back_off": [(0.3, -15, 5, 0, -10, 0, -20, -20, 0), (0.8, -15, 5, 0, -10, 0, -20, -20, 0), _R],
    "eye_roll": [(0.4, 0, 0, 0, -20, 20, 20, -20, 0), (0.4, 0, 0, -15, -25, 0, 20, -20, 0), (0.4, 0, 0, 0, -20, -20, 20, -20, 0), _R],
    "look_past": [(0.5, 0, 0, 5, -5, 30, 15, -15, 0), (2.0, 0, 0, 5, -5, 30, 15, -15, 0), _R],
    "turn_away_bored": [(0.8, 0, -5, 0, 5, 50, -10, -10, 50), (2.0, 0, -5, 0, 5, 50, -10, -10, 50), _R],
    "slump": [(1.2, 0, -15, 0, 25, 0, -40, -40, 0), (2.0, 0, -15, 0, 25, 0, -40, -40, 0), (1.0, 0, 0, 0, 0, 0, -15, -15, 0)],
    "heavy_sigh": [(0.8, 0, 8, 0, -10, 0, 10, 10, 0), (1.4, 0, -15, 0, 25, 0, -40, -40, 0), (1.0, 0, -5, 0, 10, 0, -20, -20, 0)],
    "hat_brim": [(0.8, 0, -5, 0, 15, 0, 20, -35, 0), (2.0, 0, -5, 0, 15, 0, 20, -35, 0), _R],
    "over_shoulder": [(1.0, 0, 0, 0, 5, 90, 0, -20, 90), (0.8, 0, 0, 0, 5, 40, 0, -20, 90), (1.5, 0, 0, 0, 5, 40, 0, -20, 90), (1.0, 0, 0, 0, 0, 0, 0, 0, 0)],
    "slow_scan": [(1.5, 0, 0, 0, 10, 35, 0, -20, 0), (3.0, 0, 0, 0, 10, -35, 0, -20, 0), (1.5, 0, 0, 0, 0, 0, 0, 0, 0)],
    "hair_flip": [(0.25, 0, 5, 20, -10, 15, 40, 40, 0), (0.35, 0, 5, -10, -15, -5, 50, 50, 0), (1.0, 0, 5, -10, -15, -5, 50, 50, 0), _R],
    "pose_hold": [(0.4, 0, 10, 12, -15, 10, 55, 55, 0), (2.0, 0, 10, 12, -15, 10, 55, 55, 0), _R],
    "talk_to_the_hand": [(0.5, 0, 5, 0, -15, 60, 40, 40, 60), (1.5, 0, 5, 0, -15, 60, 40, 40, 60), (0.6, 0, 0, 0, 0, 0, 0, 0, 0)],
    "big_bounce": [(0.2, 0, 15, 0, -10, 0, 60, 60, 0), (0.2, 0, -10, 0, 10, 0, 0, 0, 0)] * 3 + [_R],
    "groove": [(0.3, 0, 5, 15, 0, 10, 50, 10, 15), (0.3, 0, -5, -15, 0, -10, 10, 50, -15)] * 3 + [_R],
    "twirl": [(1.0, 0, 10, 0, -5, 150, 60, 60, 150), (1.0, 0, 10, 0, -5, 0, 60, 60, 0), (1.0, 0, 10, 0, -5, -150, 60, 60, -150), (1.0, 0, 0, 0, 0, 0, 0, 0, 0)],
    "raise_the_roof": [(0.2, 0, 15, 0, -15, 0, 70, 70, 0), (0.2, 0, 5, 0, -5, 0, 20, 20, 0)] * 3 + [_R],
    "menacing_lean": [(1.5, 15, -10, 0, 15, 0, 30, 30, 0), (0.6, 15, -10, 0, 15, 0, 30, 30, 0), (0.2, -10, 10, 0, -15, 0, 60, 60, 0), _R],
    "dramatic_turn": [(1.4, 0, 5, 0, -10, 120, 40, 40, 120), (1.5, 0, 5, 0, -10, 120, 40, 40, 120), (0.35, 0, 5, 0, -10, 0, 60, 60, 0), _R],
    "villain_rise": [(2.0, 0, 20, 0, -15, 0, 70, 70, 0), (1.0, 0, 20, 0, -15, 0, 70, 70, 0), _R],
    "steeple": [(0.8, 0, 0, 0, 10, 0, -30, -30, 0), (1.5, 0, 0, 0, 10, 0, -30, -30, 0), _R],
    "whisper_glance": [(0.3, 0, 0, 0, 0, 35, 30, 30, 0), (0.4, 0, 0, 0, 0, -35, 30, 30, 0), (0.5, 15, -5, 15, 10, 0, 40, 40, 0), (1.2, 15, -5, 15, 10, 0, 40, 40, 0), _R],
    "scan_head_to_toe": [(0.8, 0, 5, 0, -25, 0, 40, 40, 0), (2.0, 0, -5, 0, 30, 0, 40, 40, 0), (0.8, 0, 0, 0, 0, 0, 30, 30, 0)],
    "nosy_lean": [(0.6, 15, 0, 12, 5, 0, 50, 50, 0), (1.5, 15, 0, 12, 5, 0, 50, 50, 0), _R],
    "flinch": [(0.12, -15, -10, 0, 12, 0, -30, -30, 0), (0.6, -15, -10, 0, 12, 0, -30, -30, 0), _R],
    "tremble": [(0.08, 0, 0, 3, 0, 0, 15, -5, 0), (0.08, 0, 0, -3, 0, 0, -5, 15, 0)] * 5 + [_R],
    "self_check": [(0.6, 0, -5, 0, 35, 25, 40, 0, 0), (0.8, 0, -5, 0, 35, -25, 0, 40, 0), (0.5, 0, 0, 0, 0, 0, 20, 20, 0), _R],
}
EXPRESS_GESTURES = list(_EXPRESS)


def _pose(k) -> Pose:
    sec, x, z, roll, pitch, yaw, ant_r, ant_l, body = k
    yaw = max(body - 60.0, min(body + 60.0, yaw))
    return Pose(roll=roll, pitch=pitch, yaw=yaw, z=z, x=x, ant=(-ant_r, -ant_l),
                body_yaw=max(-160.0, min(160.0, body)), dur=max(0.08, sec))


GESTURES.update({name: [_pose(k) for k in keys] for name, keys in _EXPRESS.items()})


def at_speed(name: str, speed: float = 1.0) -> list[Pose]:
    """A gesture played faster or slower (0.5-2.0), e.g. the burned-out employee at 0.6."""
    s = min(2.0, max(0.5, speed))
    return [Pose(p.roll, p.pitch, p.yaw, p.z, p.x, p.ant, p.body_yaw, max(0.08, p.dur / s)) for p in GESTURES[name]]
