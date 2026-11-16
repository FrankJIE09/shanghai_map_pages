#!/usr/bin/env python3
"""Render the promo's original, sample-free 15-second instrumental.

Requires numpy. Usage: python3 scripts/promo/make_audio.py /tmp/promo/audio.wav
All oscillators, percussion and effects are synthesized here; no licensed loops,
downloaded samples, voice, or network access are used.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import wave

import numpy as np


RATE = 48_000
DURATION = 15.0
BPM = 120
SEED = 20261116


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rng = np.random.default_rng(SEED)
    mix = np.zeros((int(RATE * DURATION), 2), dtype=np.float64)

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

    # Fmaj9 / Dm9 / Bbmaj9 / C6: a warm, relaxed city-walk progression.
    chords = [([57, 60, 64, 67], 41), ([57, 60, 64, 69], 38),
              ([57, 60, 62, 65], 34), ([55, 57, 60, 64], 36),
              ([57, 60, 64, 67], 41), ([57, 60, 62, 65], 34),
              ([57, 60, 64, 67], 41)]
    for bar, (notes, bass_note) in enumerate(chords):
        start = bar * 2.0
        for j, note in enumerate(notes):
            s = keys(note, 2.4)
            place(s, start + .012 * j, .17, (j - 1.5) * .25)
            place(s, start + .19, .022, -(j - 1.5) * .35)
        # A softer syncopated chord answers each downbeat.
        if bar < 6:
            for j, note in enumerate(notes):
                place(keys(note, 1.0), start + 1.25, .07, (j - 1.5) * .25)
        for offset, length in [(0, .43), (.75, .23), (1.5, .35)]:
            if start + offset >= 13.5:
                continue
            t = np.arange(round(length * RATE)) / RATE
            env = (1 - np.exp(-180 * t)) * np.exp(-3 * t)
            env *= np.minimum(1, (length - t) / .06)
            bass = (np.sin(2 * np.pi * hz(bass_note) * t)
                    + .15 * np.sin(2 * np.pi * hz(bass_note) * 2 * t)) * env
            place(bass, start + offset, .26)

    # Sparse pentatonic motif. The close resolves into the final tonic chord.
    melody = [(0.25, 72), (.75, 76), (1.50, 79), (2.75, 76),
              (3.25, 74), (4.25, 72), (5.00, 69), (5.50, 72),
              (6.25, 74), (7.00, 76), (7.50, 72), (8.25, 76),
              (9.00, 79), (9.75, 77), (10.5, 76), (11.25, 72),
              (12.25, 76), (12.75, 79), (13.5, 77)]
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

    for beat in range(28):
        at = beat * 60 / BPM
        if beat % 4 in (0, 2):
            place(kick(), at, .37)
        if beat % 4 in (1, 3):
            place(clap(), at, .19, -.06)
        place(hat(), at, .033, .42)
        if beat < 26:
            place(hat(), at + .27, .023, -.42)
    # Quiet airy transitions, with no prominent high-frequency riser.
    for center in (2.5, 6, 9, 12):
        t = np.arange(round(.38 * RATE)) / RATE
        noise = rng.normal(0, 1, len(t))
        noise = np.convolve(noise, np.ones(32) / 32, mode="same")
        airy = noise * np.sin(np.pi * t / .38) ** 2
        place(airy, center - .20, .10, -.25)
        place(keys(84, .55), center, .025, .25)

    t = np.arange(len(mix)) / RATE
    fade = np.minimum(1, t / .035) * np.minimum(1, (DURATION - t) / .60)
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
          f"peak {20 * np.log10(np.max(np.abs(mix))):.2f}dBFS; seed={SEED}")


if __name__ == "__main__":
    main()
