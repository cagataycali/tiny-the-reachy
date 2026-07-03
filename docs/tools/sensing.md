# sensing

<span class="read-badge">⏱ 45s</span>

TINY sees through the **head camera** and can inject what it sees straight into
the conversation. All sensing is read-only.

## `reachy_camera` — grab a frame

```python
reachy_camera(save_path="", timeout=10.0)   # → saves a JPEG, returns the path
```

Captures a single frame from the head camera via the daemon. With no
`save_path`, it uses `TINY_CAMERA_SNAPSHOT` (default `/tmp/tiny_view.jpg`).

## `reachy_look_at` — visual servoing

```python
reachy_look_at(u, v, duration=1.0)   # pixel coords in the camera frame
```

Points the head so pixel `(u,v)` moves toward center. Chain it after a
detection to track a face or object.

## `take_photo` — bidi vision (the good one)

```python
take_photo(question="who's there?")
```

Grabs a frame **and** injects it into the model's context with your question —
so TINY actually *reasons about what it sees* and replies aloud. This is the
tool to use for "look at me", "what do you see?", "who's there?".

```
"look at me"        → take_photo(question="who is in front of me?")
"what's this?"      → take_photo(question="what object am I looking at?")
"read this to me"   → take_photo(question="transcribe any text you see")
```

!!! note "Media backend"
    The daemon owns the camera. If frame grabs fight the daemon, set
    `REACHY_MEDIA_BACKEND=no_media` and let `reachy_camera` grab transiently, or
    `REACHY_CAMERA_BACKEND=local`. See [env vars](../reference/env.md).
