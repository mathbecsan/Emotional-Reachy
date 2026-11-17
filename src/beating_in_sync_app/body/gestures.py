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
