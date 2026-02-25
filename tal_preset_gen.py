#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".ogg"}
IGNORE_EXTS = {".reapeaks", ".asd"}

# Match notes even when surrounded by "_" (underscore is a "word char", so \b fails)
NOTE_RE = re.compile(r"(?:^|[^A-Za-z0-9])([A-Ga-g])([#bB]?)(-?\d+)(?=$|[^A-Za-z0-9])")

NOTE_TO_SEMI = {
    "C": 0, "C#": 1, "DB": 1,
    "D": 2, "D#": 3, "EB": 3,
    "E": 4,
    "F": 5, "F#": 6, "GB": 6,
    "G": 7, "G#": 8, "AB": 8,
    "A": 9, "A#": 10, "BB": 10,
    "B": 11,
}

@dataclass
class SampleEntry:
    path: str
    root_midi: int
    vel_hi: Optional[int]

def note_to_midi(note: str, middle_c=4):
    m = re.match(r"^([A-Ga-g])([#bB]?)(-?\d+)$", note)
    if not m:
        return None
    l, a, o = m.groups()
    key = l.upper() + a.upper()
    if key not in NOTE_TO_SEMI:
        return None
    return 60 + 12 * (int(o) - middle_c) + NOTE_TO_SEMI[key]

def build_regex_from_pattern(pattern: str):
    esc = re.escape(pattern)
    esc = esc.replace(r"\{note\}", r"(?P<note>[A-Ga-g][#bB]?-?\d+)")
    esc = esc.replace(r"\{vel\}", r"(?P<vel>\d+)")
    return re.compile(rf"^{esc}$")

def auto_detect(name, middle_c):
    root = None
    vel = None

    m = NOTE_RE.search(name)
    if m:
        root = note_to_midi("".join(m.groups()), middle_c)

    vm = re.search(r"(?:vel|v)[ _\-]?(\d{1,3})", name, re.I)
    if vm:
        v = int(vm.group(1))
        if 1 <= v <= 127:
            vel = v

    return root, vel

def list_samples(folder: str) -> List[str]:
    folder = os.path.abspath(os.path.expanduser(folder))
    out: List[str] = []
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in IGNORE_EXTS:
                continue
            if ext in AUDIO_EXTS:
                out.append(os.path.join(root, fn))
    return sorted(out)

def compute_key_ranges(sorted_roots, low_spread=None, high_spread=None):
    ranges = {}
    n = len(sorted_roots)

    for i, r in enumerate(sorted_roots):
        if i == 0:
            lo = 0 if low_spread is None else max(0, r - low_spread)
        else:
            lo = (sorted_roots[i-1] + r) // 2 + 1

        if i == n - 1:
            hi = 127 if high_spread is None else min(127, r + high_spread)
        else:
            hi = (r + sorted_roots[i+1]) // 2

        ranges[r] = (lo, hi)
    return ranges

def compute_vel_ranges(vels):
    vels = sorted(vels)
    out = []
    lo = 0
    for v in vels:
        out.append((v, lo, v))
        lo = v + 1
    if out:
        v, lo0, hi = out[-1]
        out[-1] = (v, lo0, 127)
    return out

def relpath(sample, preset_dir):
    return os.path.relpath(sample, preset_dir).replace("\\", "/")

def derive_output_path(out_arg, sample_paths):
    base = os.path.dirname(os.path.abspath(sample_paths[0]))
    if not out_arg:
        return os.path.join(base, "instrument.talsmpl")
    if out_arg.lower().endswith(".talsmpl"):
        return out_arg
    os.makedirs(out_arg, exist_ok=True)
    return os.path.join(out_arg, "instrument.talsmpl")

def make_tal(entries: List[SampleEntry], preset_path, copy_samples,
             on_duplicate, low_spread, high_spread):

    preset_dir = os.path.dirname(os.path.abspath(preset_path))
    os.makedirs(preset_dir, exist_ok=True)

    sample_out = preset_dir
    if copy_samples:
        sample_out = os.path.join(preset_dir, "Samples")
        os.makedirs(sample_out, exist_ok=True)

    by_note: Dict[int, List[SampleEntry]] = {}
    for e in entries:
        by_note.setdefault(e.root_midi, []).append(e)

    roots = sorted(by_note.keys())
    key_ranges = compute_key_ranges(roots, low_spread, high_spread)

    root_xml = ET.Element("tal", {"curprogram": "0", "version": "11"})
    programs = ET.SubElement(root_xml, "programs")
    program = ET.SubElement(programs, "program", {"programname": "auto"})

    layer = ET.SubElement(program, "samplelayer0")
    multis = ET.SubElement(layer, "multisamples")

    for r in roots:
        loNote, hiNote = key_ranges[r]
        samples = by_note[r]

        if not any(s.vel_hi for s in samples):
            s = samples[0]
            src = s.path
            if copy_samples:
                dst = os.path.join(sample_out, os.path.basename(src))
                shutil.copy2(src, dst)
                path = relpath(dst, preset_dir)
            else:
                path = relpath(src, preset_dir)

            ET.SubElement(multis, "multisample", {
                "url": path,
                "urlRelativeToPresetDirectory": path,
                "rootkey": str(r),
                "lowkey": str(loNote),
                "highkey": str(hiNote),
                "velocitystart": "0",
                "velocityend": "127"
            })
            continue

        vel_map: Dict[int, SampleEntry] = {}
        for s in samples:
            if s.vel_hi is None:
                continue
            v = s.vel_hi
            if v in vel_map:
                if on_duplicate == "error":
                    raise ValueError("duplicate velocity")
                if on_duplicate == "keep-last":
                    vel_map[v] = s
            else:
                vel_map[v] = s

        vel_ranges = compute_vel_ranges(sorted(vel_map.keys()))

        for vhi, loVel, hiVel in vel_ranges:
            s = vel_map[vhi]
            src = s.path

            if copy_samples:
                dst = os.path.join(sample_out, os.path.basename(src))
                shutil.copy2(src, dst)
                path = relpath(dst, preset_dir)
            else:
                path = relpath(src, preset_dir)

            ET.SubElement(multis, "multisample", {
                "url": path,
                "urlRelativeToPresetDirectory": path,
                "rootkey": str(r),
                "lowkey": str(loNote),
                "highkey": str(hiNote),
                "velocitystart": str(loVel),
                "velocityend": str(hiVel)
            })

    tree = ET.ElementTree(root_xml)
    ET.indent(tree, space="  ")
    tree.write(preset_path, encoding="utf-8", xml_declaration=True)

def main():
    ap = argparse.ArgumentParser(
        description="Generate a TAL Sampler .talsmpl from multisamples.")

    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--folder")
    src.add_argument("--samples", nargs="+")

    ap.add_argument("--out")
    ap.add_argument("--pattern")
    ap.add_argument("--middle-c", type=int, default=3)
    ap.add_argument("--copy-samples", action="store_true")
    ap.add_argument("--on-duplicate",
                    choices=["error", "keep-first", "keep-last"],
                    default="keep-last")
    ap.add_argument("--low-spread", type=int, default=12)
    ap.add_argument("--high-spread", type=int, default=12)

    args = ap.parse_args()

    if args.folder:
        sample_paths = list_samples(args.folder)
    else:
        sample_paths = args.samples

    if not sample_paths:
        print("no samples")
        sys.exit(1)

    rx = build_regex_from_pattern(args.pattern) if args.pattern else None

    entries: List[SampleEntry] = []

    for p in sample_paths:
        stem = os.path.splitext(os.path.basename(p))[0]

        if rx:
            m = rx.match(stem)
            if not m:
                continue
            note = m.groupdict().get("note")
            vel = m.groupdict().get("vel")
            root = note_to_midi(note, args.middle_c) if note else None
            vel = int(vel) if vel else None
        else:
            root, vel = auto_detect(stem, args.middle_c)

        if root is None:
            continue

        entries.append(SampleEntry(os.path.abspath(p), root, vel))

    if not entries:
        print("no valid samples")
        sys.exit(2)

    out_path = derive_output_path(args.out, sample_paths)

    make_tal(entries, out_path,
             args.copy_samples,
             args.on_duplicate,
             args.low_spread,
             args.high_spread)

    print(out_path)

if __name__ == "__main__":
    main()
