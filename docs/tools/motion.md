# motion

<span class="read-badge">⏱ 60s</span>

TINY's body is a **6-DOF head** (Stewart platform), a **rotating body**, and
**two antennas**. That's the whole motion vocabulary — and it's plenty
expressive. All angles are **degrees**, all translations **millimeters**, and
everything is clamped (see [safety](../guide/safety.md)).

## `reachy_look` — the primary gesture

Move the head to a pose with smooth interpolation.

```python
reachy_look(x=0, y=0, z=0,          # head translation, mm
            roll=0, pitch=0, yaw=0, # head orientation, deg
            antennas=None,          # optional [right, left] deg
            duration=1.0)
```

| param | range | note |
|---|---|---|
| `pitch` / `roll` | [-40, +40]° | up/down · tilt |
| `yaw` | [-180, +180]° | but head−body delta capped at 65° |
| `x,y,z` | small mm offsets | subtle lean / bob |

**Gestures fall right out of it:**

- nod → `reachy_look(pitch=15)` then `reachy_look(pitch=-10)`
- tilt (curious) → `reachy_look(roll=15)`
- lean in → `reachy_look(x=20, pitch=10)`

## `reachy_antennas` — emotion in a flick

```python
reachy_antennas(right=0.0, left=0.0, duration=0.5)   # degrees
```

- happy / alert → `reachy_antennas(45, 45)`
- excited → `reachy_antennas(60, 60)`
- sad / droop → `reachy_antennas(-40, -40)`

## `reachy_body_turn` — orient toward a speaker

```python
reachy_body_turn(yaw=0.0, duration=1.0)   # deg, clamped [-160, 160]
```

Turn toward whoever's talking: `reachy_body_turn(30)`. Keep the head−body yaw
delta under 65° — the wrapper clamps it for you.

## `reachy_home` & `reachy_wake`

```python
reachy_home(duration=1.0)          # neutral pose — head centered, antennas rest
reachy_wake(sleep=False)           # wake: init + wake emote + sound
reachy_wake(sleep=True)            # sleep: settle + goto_sleep
```

!!! tip "Small moves look best"
    Reachy Mini is a desktop companion. Gentle, small, frequent motion reads as
    "alive". Big fast moves read as "malfunctioning". The SDK clamps hard limits;
    good taste clamps the rest.
