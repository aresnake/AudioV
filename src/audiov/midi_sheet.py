from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import mido


@dataclass(frozen=True)
class NoteEvent:
    start_s: float
    end_s: float
    pitch: int
    velocity: int
    channel: int
    track: int


def _collect_tempo_map(mid: mido.MidiFile) -> List[Tuple[int, int]]:
    """Return list of (tick, tempo_us_per_beat). Defaults to 500000 at tick 0."""
    changes: List[Tuple[int, int]] = [(0, 500000)]
    for tr in mid.tracks:
        abs_tick = 0
        for msg in tr:
            abs_tick += msg.time
            if msg.type == "set_tempo":
                changes.append((abs_tick, int(msg.tempo)))

    changes.sort(key=lambda x: x[0])

    # Deduplicate same-tick tempo changes (keep last)
    dedup: Dict[int, int] = {}
    for tick, tempo in changes:
        dedup[int(tick)] = int(tempo)

    out = sorted(dedup.items(), key=lambda x: x[0])
    if not out or out[0][0] != 0:
        out.insert(0, (0, 500000))
    return out


def _tick_to_seconds(tick: int, tpq: int, tempo_map: List[Tuple[int, int]]) -> float:
    """Convert absolute tick -> seconds using piecewise tempo segments."""
    if tick <= 0:
        return 0.0

    total = 0.0
    prev_tick = tempo_map[0][0]
    prev_tempo = tempo_map[0][1]

    for change_tick, change_tempo in tempo_map[1:]:
        if change_tick >= tick:
            break
        dt = change_tick - prev_tick
        if dt > 0:
            total += mido.tick2second(dt, tpq, prev_tempo)
        prev_tick = change_tick
        prev_tempo = change_tempo

    remaining = tick - prev_tick
    if remaining > 0:
        total += mido.tick2second(remaining, tpq, prev_tempo)

    return float(total)


def parse_midi_notes(midi_path: str | Path) -> List[NoteEvent]:
    p = Path(midi_path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    mid = mido.MidiFile(str(p))
    tempo_map = _collect_tempo_map(mid)

    events: List[NoteEvent] = []

    for track_idx, track in enumerate(mid.tracks):
        abs_tick = 0
        active: Dict[Tuple[int, int], Tuple[int, int]] = {}  # (ch, pitch) -> (start_tick, vel)

        for msg in track:
            abs_tick += msg.time

            if msg.type == "note_on" and msg.velocity > 0:
                active[(msg.channel, msg.note)] = (abs_tick, msg.velocity)

            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                key = (msg.channel, msg.note)
                if key not in active:
                    continue

                start_tick, vel = active.pop(key)
                start_s = _tick_to_seconds(start_tick, mid.ticks_per_beat, tempo_map)
                end_s = _tick_to_seconds(abs_tick, mid.ticks_per_beat, tempo_map)
                if end_s <= start_s:
                    continue

                events.append(
                    NoteEvent(
                        start_s=start_s,
                        end_s=end_s,
                        pitch=int(msg.note),
                        velocity=int(vel),
                        channel=int(msg.channel),
                        track=int(track_idx),
                    )
                )

    events.sort(key=lambda e: (e.start_s, e.pitch))
    return events


def normalize_notes(
    notes: List[NoteEvent],
    pitch_min: int | None = None,
    pitch_max: int | None = None,
) -> tuple[List[NoteEvent], int, int]:
    if not notes:
        return [], 0, 0

    pmin = min(n.pitch for n in notes) if pitch_min is None else int(pitch_min)
    pmax = max(n.pitch for n in notes) if pitch_max is None else int(pitch_max)

    filtered = [n for n in notes if pmin <= n.pitch <= pmax]
    return filtered, pmin, pmax
