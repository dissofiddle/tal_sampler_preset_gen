#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional
import soundfile as sf


NOTE_TO_SEMI = {
    "C": 0, "C#": 1, "DB": 1,
    "D": 2, "D#": 3, "EB": 3,
    "E": 4,
    "F": 5, "F#": 6, "GB": 6,
    "G": 7, "G#": 8, "AB": 8,
    "A": 9, "A#": 10, "BB": 10,
    "B": 11,
}

NOTE_RE = re.compile(r"^([A-Ga-g])([#bB]?)(-?\d+)$")


@dataclass
class NoteSpec:
    name: str
    midi: int


@dataclass
class Segment:
    root_midi: int
    start: int
    end: int
    path: Path


def note_to_midi(note: str, middle_c: int = 3) -> int:
    m = NOTE_RE.match(note.strip())
    if not m:
        raise ValueError(f"Invalid note format: {note}")

    letter, accidental, octave = m.groups()
    key = letter.upper() + accidental.upper()

    if key not in NOTE_TO_SEMI:
        raise ValueError(f"Unsupported note name: {note}")

    return 60 + 12 * (int(octave) - middle_c) + NOTE_TO_SEMI[key]


def load_note_config(config_path: Path, middle_c: int) -> List[NoteSpec]:
    text = config_path.read_text(encoding="utf-8")
    tokens = re.findall(r"[A-Ga-g][#bB]?-?\d+", text)

    if not tokens:
        raise ValueError("No valid notes found in config file")

    return [NoteSpec(t, note_to_midi(t, middle_c)) for t in tokens]


def find_wavs(inputs: List[Path]) -> List[Tuple[Path, Path]]:
    out = []
    for root in inputs:
        for wav in root.rglob("*.wav"):
            out.append((root, wav))
    return sorted(out)


def compute_key_ranges(sorted_roots, low_spread, high_spread):
    ranges = {}
    n = len(sorted_roots)

    for i, r in enumerate(sorted_roots):
        if i == 0:
            lo = max(0, r - low_spread)
        else:
            lo = (sorted_roots[i - 1] + r) // 2 + 1

        if i == n - 1:
            hi = min(127, r + high_spread)
        else:
            hi = (r + sorted_roots[i + 1]) // 2

        ranges[r] = (lo, hi)

    return ranges


def compute_segments(wav_path: Path, notes: List[NoteSpec]):

    info = sf.info(str(wav_path))
    total_frames = info.frames

    if total_frames == 0:
        raise ValueError("Empty audio file")

    n = len(notes)

    base = total_frames // n
    remainder = total_frames % n

    segments = []
    cursor = 0

    for i, note in enumerate(notes):
        length = base + (1 if i < remainder else 0)
        start = cursor
        end = cursor + length - 1

        segments.append((note, start, end))
        cursor += length

    return segments


def no_split_segments(wav_path: Path, segments):
    return [Segment(note.midi, start, end, wav_path)
            for note, start, end in segments]


def relpath_posix(path: Path, base: Path):
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def write_preset(preset_path: Path, segments: List[Segment],
                 low_spread, high_spread):

    preset_path.parent.mkdir(parents=True, exist_ok=True)

    roots = sorted({s.root_midi for s in segments})
    key_ranges = compute_key_ranges(roots, low_spread, high_spread)

    root_xml = ET.Element("tal", {"curprogram": "0", "version": "11"})
    programs = ET.SubElement(root_xml, "programs")
    program = ET.SubElement(programs, "program",
                            {"programname": preset_path.stem})

    layer = ET.SubElement(program, "samplelayer0")
    multis = ET.SubElement(layer, "multisamples")

    for s in segments:

        lo, hi = key_ranges[s.root_midi]
        rel = relpath_posix(s.path, preset_path.parent)

        ET.SubElement(multis, "multisample", {
            "url": rel,
            "urlRelativeToPresetDirectory": rel,
            "rootkey": str(s.root_midi),
            "lowkey": str(lo),
            "highkey": str(hi),
            "velocitystart": "0",
            "velocityend": "127",

            # 🔥 slicing correct TAL
            "startsample": str(s.start),
            "endsample": str(s.end),

            "loopstartsample": "0",
            "loopendsample": str(s.end),
            "fadeinsamples": "0",
            "loopenabled": "0",
            "volume": "1",
            "detune": "0.5",
            "isromsample": "0",
            "slice": "0",
            "reverse": "0",
            "autozerocrossingloop": "0",
        })

    tree = ET.ElementTree(root_xml)
    ET.indent(tree, space="  ")
    tree.write(preset_path, encoding="utf-8", xml_declaration=True)


def build_output_dir(source_root: Path, wav_path: Path,
                     out_root: Optional[Path], multi_source):

    # 🔥 mode par défaut → à côté du wav
    if out_root is None:
        return wav_path.parent

    rel = wav_path.relative_to(source_root)

    if multi_source:
        return out_root / source_root.name / rel.parent

    return out_root / rel.parent


def process_wav(source_root, wav_path, out_root, notes,
                multi_source, low_spread, high_spread):

    base = build_output_dir(source_root, wav_path, out_root, multi_source)
    preset_path = base / f"{wav_path.stem}.talsmpl"

    segments = compute_segments(wav_path, notes)
    segments = no_split_segments(wav_path, segments)

    write_preset(preset_path, segments, low_spread, high_spread)

    return preset_path


def main():

    ap = argparse.ArgumentParser(
        description="Create TAL Sampler presets from multi-note WAV files."
    )

    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--out", help="Optional output root")
    ap.add_argument("--config", required=True)
    ap.add_argument("--middle-c", type=int, default=3)
    ap.add_argument("--low-spread", type=int, default=12)
    ap.add_argument("--high-spread", type=int, default=12)

    args = ap.parse_args()

    inputs = [Path(p).expanduser().resolve() for p in args.inputs]

    out_root = None
    if args.out:
        out_root = Path(args.out).expanduser().resolve()

    config = Path(args.config).expanduser().resolve()

    notes = load_note_config(config, args.middle_c)
    wavs = find_wavs(inputs)

    if not wavs:
        print("no wav found")
        sys.exit(1)

    multi_source = len(inputs) > 1

    for source_root, wav in wavs:
        try:
            preset = process_wav(
                source_root,
                wav,
                out_root,
                notes,
                multi_source,
                args.low_spread,
                args.high_spread
            )
            print(preset)

        except Exception as e:
            print(f"FAILED: {wav} -> {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
