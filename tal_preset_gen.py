#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}
NOTE_RE = re.compile(r"\b([A-Ga-g])([#bB]?)(-?\d+)\b")

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
class Sample:
    path: str
    root: int
    vel: Optional[int]

def note_to_midi(note: str) -> Optional[int]:
    m = re.match(r"([A-Ga-g])([#bB]?)(-?\d+)", note)
    if not m:
        return None
    l, a, o = m.groups()
    key = l.upper() + a.upper()
    if key not in NOTE_TO_SEMI:
        return None
    return 12 * (int(o) + 1) + NOTE_TO_SEMI[key]

def detect(name: str):
    root = None
    vel = None

    m = NOTE_RE.search(name)
    if m:
        root = note_to_midi("".join(m.groups()))

    vm = re.search(r"(?:vel|v)(\d+)", name, re.I)
    if vm:
        vel = int(vm.group(1))

    return root, vel

def list_samples(folder):
    out = []
    for f in os.listdir(folder):
        p = os.path.join(folder, f)
        if os.path.isfile(p) and os.path.splitext(f)[1].lower() in AUDIO_EXTS:
            out.append(p)
    return sorted(out)

def compute_key_ranges(roots):
    ranges = {}
    roots = sorted(roots)
    for i, r in enumerate(roots):
        if i == 0:
            lo = 0
        else:
            lo = (roots[i-1] + r) // 2 + 1
        if i == len(roots)-1:
            hi = 127
        else:
            hi = (r + roots[i+1]) // 2
        ranges[r] = (lo, hi)
    return ranges

def compute_vel_ranges(vels):
    vels = sorted(vels)
    out = []
    lo = 0
    for v in vels:
        out.append((lo, v))
        lo = v + 1
    if out:
        last_lo, last_hi = out[-1]
        out[-1] = (last_lo, 127)
    return out

def make_tal(samples: List[Sample], out_path: str):
    by_note: Dict[int, List[Sample]] = {}
    for s in samples:
        by_note.setdefault(s.root, []).append(s)

    roots = sorted(by_note.keys())
    key_ranges = compute_key_ranges(roots)

    root_xml = ET.Element("tal", {"curprogram": "0", "version": "11"})
    programs = ET.SubElement(root_xml, "programs")
    program = ET.SubElement(programs, "program", {"programname": "auto"})

    layer = ET.SubElement(program, "samplelayer0")
    multis = ET.SubElement(layer, "multisamples")

    for r in roots:
        lo, hi = key_ranges[r]
        samps = by_note[r]

        if all(s.vel is None for s in samps):
            s = samps[0]
            ET.SubElement(multis, "multisample", {
                "url": s.path,
                "urlRelativeToPresetDirectory": s.path,
                "rootkey": str(r),
                "lowkey": str(lo),
                "highkey": str(hi),
                "velocitystart": "0",
                "velocityend": "127"
            })
        else:
            vel_map = {s.vel: s for s in samps if s.vel is not None}
            vel_ranges = compute_vel_ranges(sorted(vel_map.keys()))
            for v_lo, v_hi in vel_ranges:
                s = vel_map.get(v_hi)
                if not s:
                    continue
                ET.SubElement(multis, "multisample", {
                    "url": s.path,
                    "urlRelativeToPresetDirectory": s.path,
                    "rootkey": str(r),
                    "lowkey": str(lo),
                    "highkey": str(hi),
                    "velocitystart": str(v_lo),
                    "velocityend": str(v_hi)
                })

    tree = ET.ElementTree(root_xml)
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="utf-8", xml_declaration=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    files = list_samples(args.folder)
    samples = []

    for p in files:
        stem = os.path.splitext(os.path.basename(p))[0]
        root, vel = detect(stem)
        if root is not None:
            samples.append(Sample(p, root, vel))

    if not samples:
        print("no samples")
        return

    make_tal(samples, args.out)
    print("done", args.out)

if __name__ == "__main__":
    main()
