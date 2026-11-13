"""Stage 2 of the lesson-library ingestion: describe a video by its motion.

    python -m jumpsight_coach.ingest.describe_motion VIDEO_DIR [--out FILE]

Input:  a folder of lesson videos (*.mp4, *.mov).
Output: STATE_DIR/lesson_library/library_motion.json (or --out), one entry per
        video with measured motion features from a pose skeleton (not from
        captions or narration): one-leg stance, free-leg height, horizontal
        torso, hop count, holds, and a short text for embeddings.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.signal import find_peaks, savgol_filter

from jumpsight_core.paths import LESSON_LIBRARY_DIR

STRIDE = 2
MAX_SIDE = 480


def _pose_series(video: str):
    import mediapipe as mp

    pose = mp.solutions.pose.Pose(
        static_image_mode=False, model_complexity=0, min_detection_confidence=0.4, min_tracking_confidence=0.4
    )
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    rows, idx = [], 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % STRIDE:
            idx += 1
            continue
        ok, frame = cap.retrieve()
        if not ok:
            break
        h, w = frame.shape[:2]
        s = MAX_SIDE / max(h, w)
        if s < 1.0:
            frame = cv2.resize(frame, (int(w * s), int(h * s)))
        res = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        idx += 1
        if not res.pose_landmarks:
            rows.append(None)
            continue
        lm = res.pose_landmarks.landmark
        if lm[27].visibility < 0.4 or lm[28].visibility < 0.4:
            rows.append(None)
            continue
        rows.append(
            {k: (lm[i].x, lm[i].y) for k, i in {"ls": 11, "rs": 12, "lh": 23, "rh": 24, "la": 27, "ra": 28}.items()}
        )
    cap.release()
    pose.close()
    return rows, fps / STRIDE


def describe(video: str) -> dict:
    rows, eff_fps = _pose_series(video)
    n = len(rows)
    ok = [r for r in rows if r]
    if n == 0 or len(ok) < n * 0.3:
        return {"file": Path(video).name, "error": "pose not tracked"}
    scale = np.median([abs(((r["la"][1] + r["ra"][1]) / 2) - ((r["ls"][1] + r["rs"][1]) / 2)) for r in ok]) or 0.5

    one_leg = leg_hip = leg_sho = horiz = 0
    hip_y, t_ok = [], []
    for i, r in enumerate(rows):
        if not r:
            continue
        d_ank = abs(r["la"][1] - r["ra"][1]) / scale
        hi = min(r["la"][1], r["ra"][1])  # higher ankle (smaller y)
        hip = (r["lh"][1] + r["rh"][1]) / 2
        sho = (r["ls"][1] + r["rs"][1]) / 2
        if d_ank > 0.15:
            one_leg += 1
        if hi < hip:
            leg_hip += 1
        if hi < sho:
            leg_sho += 1
        # angle of the torso to the vertical
        dx = ((r["ls"][0] + r["rs"][0]) / 2) - ((r["lh"][0] + r["rh"][0]) / 2)
        dy = sho - hip
        ang = np.degrees(np.arctan2(abs(dx), abs(dy) + 1e-6))
        if ang > 50:
            horiz += 1
        hip_y.append(hip)
        t_ok.append(i / eff_fps)
    hop_count = 0
    if len(hip_y) > 12:
        y = savgol_filter(np.array(hip_y), min(9, len(hip_y) // 2 * 2 - 1), 2)
        pk, _ = find_peaks(-y, prominence=0.05 * scale, distance=max(2, int(0.30 * eff_fps)))
        hop_count = int(len(pk))
    # hold: windows of >=2 s with a small total change in pose
    holds, cur = [], 0.0
    for a, b in zip(hip_y[:-1], hip_y[1:]):
        if abs(b - a) < 0.006 * scale / 0.5:
            cur += 1 / eff_fps
        else:
            if cur >= 2.0:
                holds.append(round(cur, 1))
            cur = 0.0
    if cur >= 2.0:
        holds.append(round(cur, 1))
    m = len(ok)
    d = {
        "file": Path(video).name,
        "dur_s": round(n / eff_fps, 1),
        "pose_rate": round(m / n, 2),
        "one_leg_frac": round(one_leg / m, 2),
        "leg_above_hip_frac": round(leg_hip / m, 2),
        "leg_above_shoulder_frac": round(leg_sho / m, 2),
        "torso_horizontal_frac": round(horiz / m, 2),
        "hop_count": hop_count,
        "holds_s": holds[:6],
    }
    bits = []
    if d["one_leg_frac"] > 0.4:
        bits.append(f"one-leg stance {int(d['one_leg_frac'] * 100)}% of the time")
    if d["leg_above_shoulder_frac"] > 0.1:
        bits.append("free leg rises above the shoulder (Biellmann-like position)")
    elif d["leg_above_hip_frac"] > 0.15:
        bits.append("free leg above the hip (arabesque / spiral)")
    if d["torso_horizontal_frac"] > 0.25:
        bits.append(f"torso horizontal {int(d['torso_horizontal_frac'] * 100)}% of the time")
    if hop_count >= 4:
        bits.append(f"~{hop_count} hops (measured from the pelvis)")
    elif hop_count == 0:
        bits.append("no hops, a static balance drill")
    if holds:
        bits.append(f"position holds: {len(holds)}, up to {max(holds)} s")
    d["motion_text"] = "; ".join(bits) if bits else "movement without distinct markers"
    return d


def main(folder: str, out_path: str | None = None) -> None:
    out = {}
    videos = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in (".mp4", ".mov"))
    for f in videos:
        d = describe(str(f))
        out[f.stem] = d
        print(f"{f.stem}: {d.get('motion_text', d.get('error'))}")
    dest = Path(out_path) if out_path else LESSON_LIBRARY_DIR / "library_motion.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{dest}: {len(out)} videos")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video_dir")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    main(a.video_dir, a.out)
