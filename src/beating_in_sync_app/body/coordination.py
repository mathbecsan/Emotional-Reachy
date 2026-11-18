"""Head-body coordination: keep Reachy from jamming against itself.

The head pose is given in the world frame and the body turns underneath it. If the
body turns while the head keeps pointing the same way (or the head turns far while the
body stays), the gap between them grows until the Stewart platform runs out of travel
and Reachy gets stuck against its own body (the SDK's hard limit is 65 deg; observed in
practice: body-only turns of 150 deg jam unless the head turns with them).

Rules applied to every pose we send:
  * the head's yaw stays within MAX_RELATIVE_YAW of the body's yaw (the head follows the body);
  * the body stays within +-MAX_BODY_YAW;
  * during big body turns the head is kept nearly level (pitch/roll clamped), because a tilted
    head plus a large twist is where collisions happen;
  * big body turns are split into steps so head and body travel together.
"""
MAX_RELATIVE_YAW = 40.0     # deg between head and body (SDK limit 65: keep a margin)
MAX_BODY_YAW = 150.0        # deg (mechanical limit 160)
LEVEL_DURING_TURN = 10.0    # deg of pitch/roll allowed while the body turns a lot
TURN_STEP = 50.0            # deg of body travel per step for big turns


def coordinate(yaw: float, body: float, pitch: float = 0.0, roll: float = 0.0, body_delta: float = 0.0):
    """Return a safe (yaw, body, pitch, roll). `body_delta` = how far the body travels to get here."""
    body = max(-MAX_BODY_YAW, min(MAX_BODY_YAW, body))
    yaw = max(body - MAX_RELATIVE_YAW, min(body + MAX_RELATIVE_YAW, yaw))
    if abs(body_delta) > 45:
        pitch = max(-LEVEL_DURING_TURN, min(LEVEL_DURING_TURN, pitch))
        roll = max(-LEVEL_DURING_TURN, min(LEVEL_DURING_TURN, roll))
    return yaw, body, pitch, roll


def turn_steps(body_from: float, body_to: float, head_offset: float = 0.0) -> list[tuple[float, float]]:
    """Intermediate (yaw, body) waypoints for a big body turn, head travelling with the body."""
    span = body_to - body_from
    n = max(1, int(abs(span) // TURN_STEP) + (1 if abs(span) % TURN_STEP else 0))
    out = []
    for i in range(1, n + 1):
        b = body_from + span * i / n
        out.append(coordinate(b + head_offset, b)[:2])
    return out
