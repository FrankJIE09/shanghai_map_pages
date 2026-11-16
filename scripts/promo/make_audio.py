#!/usr/bin/env python3
"""Render the promo's original, sample-free instrumental (24 seconds by default).

Requires numpy. Usage: python3 scripts/promo/make_audio.py /tmp/promo/audio.wav
Optional: --duration 24, or --plan scripts/promo/editorial-plan.json.
All oscillators, percussion and effects are synthesized here; no licensed loops,
downloaded samples, voice, or network access are used.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import wave

import numpy as np


RATE = 48_000
DURATION = 24.0
BPM = 120
SEED = 20261116
CHAPTERS = (0.0, 3.0, 6.5, 10.5, 14.0, 17.0, 21.0, 24.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--duration", type=float, help="Seconds; overrides --plan, otherwise defaults to 24.")
    parser.add_argument("--plan", type=Path, help="Read delivery.duration_seconds and chapter starts from an editorial plan.")
    parser.add_argument("--fade-out", type=float, default=.7, help="Final fade duration in seconds (default: 0.7).")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text()) if args.plan else {}
    duration = args.duration if args.duration is not None else float(plan.get("delivery", {}).get("duration_seconds", DURATION))
    if not math.isfinite(duration) or duration <= 0:
        parser.error("--duration must be a finite positive number")
    if not math.isfinite(args.fade_out) or not 0 < args.fade_out <= duration:
        parser.error("--fade-out must be positive and no longer than the soundtrack")
    chapter_starts = [float(beat["start"]) for beat in plan.get("beats", [])] or CHAPTERS
    chapters = sorted(set(at for at in chapter_starts if 0 < at < duration))
    rng = np.random.default_rng(SEED)
    mix = np.zeros((round(RATE * duration), 2), dtype=np.float64)
    beat_seconds = 60 / BPM
    bar_seconds = 4 * beat_seconds
    bars = math.ceil(duration / bar_seconds)
    groove_end = max(0, duration - args.fade_out - .2)

    def hz(note: float) -> float:
        return 440 * 2 ** ((note - 69) / 12)

    def place(sound: np.ndarray, start: float, gain: float = 1, pan: float = 0) -> None:
        i = round(start * RATE)
        if i >= len(mix):
            return
        sound = sound[:len(mix) - i]
        gains = np.array([np.cos((pan + 1) * np.pi / 4),
                          np.sin((pan + 1) * np.pi / 4)])
        mix[i:i + len(sound)] += gain * sound[:, None] * gains

    def keys(note: float, duration: float = 2.2) -> np.ndarray:
        t = np.arange(round(duration * RATE)) / RATE
        f = hz(note)
        body = (np.sin(2 * np.pi * f * t)
                + .22 * np.exp(-2.0 * t) * np.sin(2 * np.pi * f * 2.002 * t)
                + .07 * np.exp(-5.0 * t) * np.sin(2 * np.pi * f * 3.998 * t))
        env = (1 - np.exp(-t * 170)) * np.exp(-t * 2.1)
        env *= np.minimum(1, (duration - t) / .12)
        return body * env

    # A complete 12-bar arrangement at the default length. The middle section
    # opens into Am7/Gm9; C7sus and Fmaj9 give the final chapter a real cadence.
    # Longer renders continue the arrangement, rather than padding its tail.
    chords = [([57, 60, 64, 67], 41), ([57, 60, 64, 69], 38),
              ([57, 60, 62, 65], 34), ([55, 57, 60, 64], 36),
              ([57, 60, 64, 67], 41), ([55, 60, 64, 67], 33),
              ([57, 60, 64, 69], 38), ([57, 58, 62, 65], 31),
              ([57, 60, 62, 65], 34), ([55, 57, 60, 64], 36)]
    melody_bars = [
        [(0.25, 72), (.75, 76), (1.50, 79)],
        [(.75, 76), (1.25, 74)],
        [(.25, 72), (1.00, 69), (1.50, 72)],
        [(.25, 74), (1.00, 76), (1.50, 72)],
        [(.25, 76), (1.00, 79), (1.75, 77)],
        [(.25, 76), (1.25, 72), (1.75, 67)],
        [(.25, 69), (.75, 72), (1.50, 76)],
        [(.25, 74), (1.00, 77), (1.50, 81)],
        [(.25, 77), (.75, 74), (1.50, 72)],
        [(.25, 76), (1.00, 74), (1.50, 72)],
    ]
    melody = []
    for bar in range(bars):
        notes, bass_note = chords[bar % len(chords)]
        motif = melody_bars[bar % len(melody_bars)]
        if bar == bars - 2:
            notes, bass_note = [58, 60, 65, 67], 36
            motif = [(.25, 77), (.75, 76), (1.50, 72)]
        if bar == bars - 1:
            notes, bass_note = chords[0]
            motif = [(.125, 69), (.50, 72), (1.00, 77)]
        start = bar * bar_seconds
        melody.extend((start + offset, note) for offset, note in motif
                      if start + offset < duration - args.fade_out)
        for j, note in enumerate(notes):
            s = keys(note, 2.4)
            place(s, start + .012 * j, .17, (j - 1.5) * .25)
            place(s, start + .19, .022, -(j - 1.5) * .35)
        # A softer syncopated chord answers each downbeat.
        if bar < bars - 1:
            for j, note in enumerate(notes):
                place(keys(note, 1.0), start + 1.25, .07, (j - 1.5) * .25)
        for offset, length in [(0, .43), (.75, .23), (1.5, .35)]:
            if start + offset >= groove_end:
                continue
            t = np.arange(round(length * RATE)) / RATE
            env = (1 - np.exp(-180 * t)) * np.exp(-3 * t)
            env *= np.minimum(1, (length - t) / .06)
            bass = (np.sin(2 * np.pi * hz(bass_note) * t)
                    + .15 * np.sin(2 * np.pi * hz(bass_note) * 2 * t)) * env
            place(bass, start + offset, .26)

    # Sparse original motif, with a new response in the second half and a
    # final F that rings through the 0.7-second fade instead of an empty tail.
    for n, (start, note) in enumerate(melody):
        s = keys(note, 1.6)
        pan = .17 if n % 2 else -.17
        place(s, start, .115, pan)
        place(s, start + .375, .027, -pan)

    def kick() -> np.ndarray:
        t = np.arange(round(.32 * RATE)) / RATE
        phase = 2 * np.pi * (48 * t + 55 * .023 * (1 - np.exp(-t / .023)))
        return np.sin(phase) * np.exp(-t * 19) * np.minimum(1, t / .003)

    def clap() -> np.ndarray:
        t = np.arange(round(.16 * RATE)) / RATE
        noise = rng.normal(0, 1, len(t))
        # Differenced then smoothed noise keeps the clap soft and compact.
        noise = np.r_[0, np.diff(noise)]
        noise = np.convolve(noise, np.ones(4) / 4, mode="same")
        return noise * np.exp(-t * 35) * np.minimum(1, t / .002)

    def hat() -> np.ndarray:
        t = np.arange(round(.065 * RATE)) / RATE
        noise = rng.normal(0, 1, len(t))
        noise -= np.convolve(noise, np.ones(8) / 8, mode="same")
        return noise * np.exp(-t * 85) * np.minimum(1, t / .002)

    for beat in range(math.ceil(duration / beat_seconds)):
        at = beat * beat_seconds
        if at >= groove_end:
            break
        if beat % 4 in (0, 2):
            place(kick(), at, .37)
        if beat % 4 in (1, 3):
            place(clap(), at, .19, -.06)
        place(hat(), at, .033, .42)
        if at + .27 < groove_end:
            place(hat(), at + .27, .023, -.42)
    # Quiet airy transitions, with no prominent high-frequency riser.
    for center in chapters:
        t = np.arange(round(.38 * RATE)) / RATE
        noise = rng.normal(0, 1, len(t))
        noise = np.convolve(noise, np.ones(32) / 32, mode="same")
        airy = noise * np.sin(np.pi * t / .38) ** 2
        place(airy, center - .20, .10, -.25)
        place(keys(84, .55), center, .025, .25)

    t = np.arange(len(mix)) / RATE
    fade_out = np.sin(np.pi / 2 * np.clip((duration - t) / args.fade_out, 0, 1)) ** 2
    fade = np.minimum(1, t / .035) * fade_out
    mix *= fade[:, None]
    peak = float(np.max(np.abs(mix)))
    mix *= .82 / peak
    pcm = np.round(mix * 32767).astype("<i2")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.output), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm.tobytes())
    print(f"{args.output}: {len(pcm) / RATE:.3f}s, {RATE}Hz stereo PCM16, "
          f"peak {20 * np.log10(np.max(np.abs(mix))):.2f}dBFS; seed={SEED}; "
          f"{bars} bars, {len(melody)} melody notes, fade={args.fade_out:.2f}s; "
          f"chapter accents={chapters}")


if __name__ == "__main__":
    main()
