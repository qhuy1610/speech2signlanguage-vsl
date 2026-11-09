# # # # # # #!/usr/bin/env python3
# # # # # # # -*- coding: utf-8 -*-
# # # # # # """
# # # # # # sign_to_avatar.py
# # # # # # =================
# # # # # # import argparse
# # # # # # import base64
# # # # # # import csv
# # # # # # import difflib
# # # # # # import io
# # # # # # import json
# # # # # # import os
# # # # # # Gloss list  ->  videos of the dataset  ->  3D landmarks (cached .npz)
# # # # # #             ->  ONE continuous animation of the Xbot avatar (standalone .html).

# # # # # # Example:
# # # # # #     python sign_to_avatar.py --glosses "bạn" "đi học" "có không"
# # # # # #     python sign_to_avatar.py --sentence "bạn | đi học | có không" --open
# # # # # #     python sign_to_avatar.py --search "địa chỉ"

# # # # # # The output .html is a single file: double-click it, no server / localhost needed.
# # # # # # (It only needs Internet once per open, to load three.js from a CDN.)
# # # # # # """
# # # # # # import re
# # # # # # import sys
# # # # # # import unicodedata
# # # # # # import webbrowser
# # # # # # from pathlib import Path

# # # # # # import numpy as np

# # # # # # # =====================================================================
# # # # # # # DEFAULTS (edit these once, then you never need to type the paths)
# # # # # # # =====================================================================
# # # # # # DEFAULT_VIDEOS = r"C:\Users\ADMIN\qh\vsl-vietnamese-sign-languages\versions\5\Dataset\Videos"
# # # # # # DEFAULT_XBOT = os.path.join("frontend_dis", "models", "Xbot.glb")
# # # # # # DEFAULT_CACHE = "landmark_cache"
# # # # # # DEFAULT_OUT = os.path.join("output", "sentence.html")

# # # # # # CACHE_VERSION = 1
# # # # # # VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")

# # # # # # BODY_NAMES = [
# # # # # #     "Hips", "Spine1", "Spine2", "Neck", "Head",
# # # # # #     "LeftArm", "LeftForeArm", "LeftHand",
# # # # # #     "RightArm", "RightForeArm", "RightHand",
# # # # # #     "LeftUpLeg", "LeftLeg", "LeftFoot",
# # # # # #     "RightUpLeg", "RightLeg", "RightFoot",
# # # # # # ]

# # # # # # try:  # make Vietnamese text safe to print on any console
# # # # # #     sys.stdout.reconfigure(errors="replace")
# # # # # #     sys.stderr.reconfigure(errors="replace")
# # # # # # except Exception:
# # # # # #     pass


# # # # # # # =====================================================================
# # # # # # # 1. Text helpers
# # # # # # # =====================================================================
# # # # # # def norm(s):
# # # # # #     """NFC + lower-case + collapsed spaces."""
# # # # # #     return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s)).strip().lower())


# # # # # # def strip_accents(s):
# # # # # #     s = norm(s).replace("đ", "d")
# # # # # #     s = unicodedata.normalize("NFD", s)
# # # # # #     return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# # # # # # def without_parens(s):
# # # # # #     return norm(re.sub(r"\([^)]*\)", " ", str(s)))


# # # # # # def natural_key(s):
# # # # # #     return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


# # # # # # VIDEO_RE = re.compile(r"^(?P<base>.*\d)(?P<reg>[NTBntb])?$")


# # # # # # def parse_video(name):
# # # # # #     """'D0001N.mp4' -> ('D0001', 'N');  'D0002.mp4' -> ('D0002', '')."""
# # # # # #     stem = Path(str(name).strip()).stem
# # # # # #     m = VIDEO_RE.match(stem)
# # # # # #     if m:
# # # # # #         return m.group("base"), (m.group("reg") or "").upper()
# # # # # #     return stem, ""


# # # # # # def label_keys(label):
# # # # # #     """All the lookup keys under which a dataset label can be found."""
# # # # # #     plain = without_parens(label)
# # # # # #     parts = {norm(label), plain}
# # # # # #     for p in re.split(r"\s*[;/,]\s*", plain):
# # # # # #         if p.strip():
# # # # # #             parts.add(norm(p))
# # # # # #     keys = set()
# # # # # #     for p in parts:
# # # # # #         if p:
# # # # # #             keys.add(p)
# # # # # #             keys.add(strip_accents(p))
# # # # # #     return keys


# # # # # # # =====================================================================
# # # # # # # 2. Reading the label file (csv / tsv / txt / xlsx / json)
# # # # # # # =====================================================================
# # # # # # def read_text_auto(path):
# # # # # #     raw = Path(path).read_bytes()
# # # # # #     if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:200]:
# # # # # #         return raw.decode("utf-16", errors="replace")
# # # # # #     try:
# # # # # #         return raw.decode("utf-8-sig")
# # # # # #     except UnicodeDecodeError:
# # # # # #         return raw.decode("cp1258", errors="replace")


# # # # # # def _pick_columns(header):
# # # # # #     h = [norm(c) for c in header]
# # # # # #     vi = next((i for i, c in enumerate(h) if c in ("video", "file", "filename", "name")), None)
# # # # # #     li = next((i for i, c in enumerate(h) if c in ("label", "gloss", "nhan", "nhãn", "text")), None)
# # # # # #     return vi, li


# # # # # # def load_records(path):
# # # # # #     """Return [(video_name, label), ...] from any supported file type."""
# # # # # #     path = str(path)
# # # # # #     ext = Path(path).suffix.lower()

# # # # # #     if ext == ".json":
# # # # # #         data = json.loads(read_text_auto(path))
# # # # # #         recs = []
# # # # # #         if isinstance(data, dict):
# # # # # #             for gloss, vids in data.items():
# # # # # #                 if isinstance(vids, (str, dict)):
# # # # # #                     vids = [vids]
# # # # # #                 for v in vids:
# # # # # #                     recs.append((v["video"] if isinstance(v, dict) else v, gloss))
# # # # # #         else:
# # # # # #             for item in data:
# # # # # #                 if isinstance(item, dict):
# # # # # #                     low = {norm(k): v for k, v in item.items()}
# # # # # #                     recs.append((low.get("video") or low.get("file"),
# # # # # #                                  low.get("label") or low.get("gloss")))
# # # # # #                 else:
# # # # # #                     recs.append((item[0], item[1]))
# # # # # #         return [(str(v), str(l)) for v, l in recs if v and l]

# # # # # #     if ext in (".xlsx", ".xls", ".xlsm"):
# # # # # #         import pandas as pd  # needs openpyxl for .xlsx
# # # # # #         df = pd.read_excel(path, dtype=str).fillna("")
# # # # # #         rows = [list(df.columns)] + df.values.tolist()
# # # # # #     else:
# # # # # #         text = read_text_auto(path)
# # # # # #         first = text.splitlines()[0] if text else ""
# # # # # #         delim = max(["\t", ",", ";"], key=first.count)
# # # # # #         rows = list(csv.reader(io.StringIO(text), delimiter=delim))

# # # # # #     rows = [r for r in rows if r and any(str(c).strip() for c in r)]
# # # # # #     if not rows:
# # # # # #         return []
# # # # # #     vi, li = _pick_columns(rows[0])
# # # # # #     start = 1
# # # # # #     if vi is None or li is None:  # no header: first two columns
# # # # # #         vi, li = 0, 1
# # # # # #         start = 0 if Path(str(rows[0][0])).suffix.lower() in VIDEO_EXTS else 1
# # # # # #     out = []
# # # # # #     for r in rows[start:]:
# # # # # #         if len(r) > max(vi, li) and str(r[vi]).strip() and str(r[li]).strip():
# # # # # #             out.append((str(r[vi]).strip(), str(r[li]).strip()))
# # # # # #     return out


# # # # # # def find_labels_file(videos_dir):
# # # # # #     vd = Path(videos_dir)
# # # # # #     exts = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json")
# # # # # #     cands = []
# # # # # #     for d in (vd, vd.parent, vd.parent.parent):
# # # # # #         if d.is_dir():
# # # # # #             cands += [p for p in d.iterdir() if p.suffix.lower() in exts]
# # # # # #     hits = [p for p in cands if "label" in p.name.lower()]
# # # # # #     if len(hits) >= 1:
# # # # # #         return str(sorted(hits, key=lambda p: len(str(p)))[0])
# # # # # #     return None


# # # # # # # =====================================================================
# # # # # # # 3. Gloss index: label -> video
# # # # # # # =====================================================================
# # # # # # class GlossIndex:
# # # # # #     def __init__(self, records, region_pref=("B", "T", "N")):
# # # # # #         self.region_pref = [r.upper() for r in region_pref]
# # # # # #         self.recs = []
# # # # # #         self.by_key = {}
# # # # # #         self.by_stem = {}
# # # # # #         for video, label in records:
# # # # # #             base, reg = parse_video(video)
# # # # # #             rec = {"video": Path(video).name, "stem": Path(video).stem,
# # # # # #                    "base": base, "region": reg, "label": label}
# # # # # #             self.recs.append(rec)
# # # # # #             self.by_stem[norm(rec["stem"])] = rec
# # # # # #             for k in label_keys(label):
# # # # # #                 self.by_key.setdefault(k, []).append(rec)

# # # # # #     def lookup(self, text):
# # # # # #         for v in (norm(text), without_parens(text),
# # # # # #                   strip_accents(text), strip_accents(without_parens(text))):
# # # # # #             if v and v in self.by_key:
# # # # # #                 return self.by_key[v]
# # # # # #         return []

# # # # # #     def choose(self, recs):
# # # # # #         """One video for a gloss: first sign (lowest id), preferred region."""
# # # # # #         groups = {}
# # # # # #         for r in recs:
# # # # # #             groups.setdefault(r["base"], []).append(r)
# # # # # #         bases = sorted(groups, key=natural_key)
# # # # # #         group = groups[bases[0]]
# # # # # #         group.sort(key=lambda r: (self.region_pref.index(r["region"])
# # # # # #                                   if r["region"] in self.region_pref else 99,
# # # # # #                                   natural_key(r["stem"])))
# # # # # #         return group[0], len(bases) - 1

# # # # # #     def resolve_one(self, gloss):
# # # # # #         """Return (list of (gloss_text, rec, note), list of missing words)."""
# # # # # #         g = str(gloss).strip()
# # # # # #         if not g:
# # # # # #             return [], []
# # # # # #         # a video id typed directly, e.g. "D0001T"
# # # # # #         rec = self.by_stem.get(norm(Path(g).stem))
# # # # # #         if rec is not None and re.fullmatch(r"[dD]\d+[NTBntb]?(\.\w+)?", g):
# # # # # #             return [(g, rec, "")], []

# # # # # #         recs = self.lookup(g)
# # # # # #         if recs:
# # # # # #             rec, extra = self.choose(recs)
# # # # # #             note = f"còn {extra} cách ký khác" if extra > 0 else ""
# # # # # #             return [(g, rec, note)], []

# # # # # #         # not a known gloss: split into the longest known pieces
# # # # # #         words = norm(g).split()
# # # # # #         found, missing, i = [], [], 0
# # # # # #         while i < len(words):
# # # # # #             for j in range(len(words), i, -1):
# # # # # #                 phrase = " ".join(words[i:j])
# # # # # #                 recs = self.lookup(phrase)
# # # # # #                 if recs:
# # # # # #                     rec, extra = self.choose(recs)
# # # # # #                     found.append((phrase, rec, f'tách từ "{g}"'))
# # # # # #                     i = j
# # # # # #                     break
# # # # # #             else:
# # # # # #                 missing.append(words[i])
# # # # # #                 i += 1
# # # # # #         if not found:
# # # # # #             return [], [g]
# # # # # #         return found, missing

# # # # # #     def suggest(self, text, n=4):
# # # # # #         pool = {}
# # # # # #         for k, recs in self.by_key.items():
# # # # # #             if strip_accents(k) == k:
# # # # # #                 pool[k] = recs[0]["label"]
# # # # # #         close = difflib.get_close_matches(strip_accents(text), list(pool), n=n, cutoff=0.6)
# # # # # #         return [pool[c] for c in close]

# # # # # #     def search(self, text, limit=30):
# # # # # #         t = strip_accents(text)
# # # # # #         hits = [r for r in self.recs if t in strip_accents(r["label"])]
# # # # # #         return sorted(hits, key=lambda r: natural_key(r["stem"]))[:limit]


# # # # # # # =====================================================================
# # # # # # # 4. Landmark extraction (MediaPipe) + cache
# # # # # # # =====================================================================
# # # # # # def assign_hands(hands, left_wrist, right_wrist):
# # # # # #     """
# # # # # #     hands: [(image_wrist_xy, world_21x3, label)], wrists in normalised image coords.
# # # # # #     Decide which detected hand is the person's LEFT / RIGHT by comparing with the
# # # # # #     body-pose wrists (more reliable than the handedness label for un-mirrored video).
# # # # # #     """
# # # # # #     res = {"L": None, "R": None}
# # # # # #     if not hands:
# # # # # #         return res

# # # # # #     def d(a, b):
# # # # # #         return float(np.hypot(a[0] - b[0], a[1] - b[1]))

# # # # # #     if left_wrist is not None and right_wrist is not None:
# # # # # #         if len(hands) == 1:
# # # # # #             h = hands[0]
# # # # # #             res["L" if d(h[0], left_wrist) <= d(h[0], right_wrist) else "R"] = h[1]
# # # # # #         else:
# # # # # #             h0, h1 = hands[0], hands[1]
# # # # # #             a = d(h0[0], left_wrist) + d(h1[0], right_wrist)
# # # # # #             b = d(h0[0], right_wrist) + d(h1[0], left_wrist)
# # # # # #             if a <= b:
# # # # # #                 res["L"], res["R"] = h0[1], h1[1]
# # # # # #             else:
# # # # # #                 res["L"], res["R"] = h1[1], h0[1]
# # # # # #     else:  # no body wrists: use the label (MediaPipe assumes a mirrored image -> swap)
# # # # # #         for h in hands:
# # # # # #             res["R" if h[2] == "Left" else "L"] = h[1]
# # # # # #     return res


# # # # # # class MediaPipeDetector:
# # # # # #     """Pose (33 world landmarks) + Hands (21 world landmarks each), one video at a time."""

# # # # # #     def __init__(self, complexity=1):
# # # # # #         import mediapipe as mp
# # # # # #         self.pose = mp.solutions.pose.Pose(
# # # # # #             static_image_mode=False, model_complexity=complexity, smooth_landmarks=True,
# # # # # #             min_detection_confidence=0.5, min_tracking_confidence=0.5)
# # # # # #         self.hands = mp.solutions.hands.Hands(
# # # # # #             static_image_mode=False, max_num_hands=2, model_complexity=1,
# # # # # #             min_detection_confidence=0.5, min_tracking_confidence=0.5)

# # # # # #     def __enter__(self):
# # # # # #         return self

# # # # # #     def __exit__(self, *a):
# # # # # #         self.pose.close()
# # # # # #         self.hands.close()
# # # # # #         return False

# # # # # #     def process(self, rgb):
# # # # # #         pr = self.pose.process(rgb)
# # # # # #         hr = self.hands.process(rgb)
# # # # # #         pose_world = left_w = right_w = None
# # # # # #         if pr.pose_world_landmarks:
# # # # # #             pose_world = np.array([[l.x, l.y, l.z] for l in pr.pose_world_landmarks.landmark],
# # # # # #                                   dtype=np.float32)
# # # # # #         if pr.pose_landmarks:
# # # # # #             lm = pr.pose_landmarks.landmark
# # # # # #             left_w, right_w = (lm[15].x, lm[15].y), (lm[16].x, lm[16].y)
# # # # # #         hands = []
# # # # # #         if hr.multi_hand_world_landmarks and hr.multi_hand_landmarks:
# # # # # #             for wl, il, hd in zip(hr.multi_hand_world_landmarks,
# # # # # #                                   hr.multi_hand_landmarks, hr.multi_handedness):
# # # # # #                 world = np.array([[l.x, l.y, l.z] for l in wl.landmark], dtype=np.float32)
# # # # # #                 hands.append(((il.landmark[0].x, il.landmark[0].y), world,
# # # # # #                               hd.classification[0].label))
# # # # # #         return {"pose": pose_world, "left_wrist": left_w, "right_wrist": right_w, "hands": hands}


# # # # # # def extract_video(video_path, detector_factory, target_width=640):
# # # # # #     """Run the detector on every frame. Returns dict of arrays (NaN = not detected)."""
# # # # # #     import cv2
# # # # # #     cap = cv2.VideoCapture(str(video_path))
# # # # # #     if not cap.isOpened():
# # # # # #         raise IOError(f"Không mở được video: {video_path}")
# # # # # #     fps = cap.get(cv2.CAP_PROP_FPS)
# # # # # #     if not fps or fps != fps or fps <= 1:
# # # # # #         fps = 30.0
# # # # # #     pose_l, lh_l, rh_l = [], [], []
# # # # # #     nan_pose = np.full((33, 3), np.nan, np.float32)
# # # # # #     nan_hand = np.full((21, 3), np.nan, np.float32)
# # # # # #     with detector_factory() as det:
# # # # # #         while True:
# # # # # #             ok, frame = cap.read()
# # # # # #             if not ok:
# # # # # #                 break
# # # # # #             h, w = frame.shape[:2]
# # # # # #             if w != target_width and w > 0:
# # # # # #                 frame = cv2.resize(frame, (target_width, int(h * target_width / w)))
# # # # # #             rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
# # # # # #             r = det.process(rgb)
# # # # # #             pose_l.append(r["pose"] if r["pose"] is not None else nan_pose)
# # # # # #             a = assign_hands(r["hands"], r["left_wrist"], r["right_wrist"])
# # # # # #             lh_l.append(a["L"] if a["L"] is not None else nan_hand)
# # # # # #             rh_l.append(a["R"] if a["R"] is not None else nan_hand)
# # # # # #     cap.release()
# # # # # #     if not pose_l:
# # # # # #         raise IOError(f"Video rỗng: {video_path}")
# # # # # #     return {"pose": np.stack(pose_l).astype(np.float32),
# # # # # #             "lhand": np.stack(lh_l).astype(np.float32),
# # # # # #             "rhand": np.stack(rh_l).astype(np.float32),
# # # # # #             "fps": float(fps)}


# # # # # # def get_clip_data(video_path, cache_dir, detector_factory):
# # # # # #     cache_path = Path(cache_dir) / (Path(video_path).stem + ".npz")
# # # # # #     if cache_path.exists():
# # # # # #         try:
# # # # # #             d = np.load(cache_path)
# # # # # #             if int(d["version"]) == CACHE_VERSION:
# # # # # #                 data = {k: d[k] for k in ("pose", "lhand", "rhand")}
# # # # # #                 data["fps"] = float(d["fps"])
# # # # # #                 return data, True
# # # # # #         except Exception:
# # # # # #             pass
# # # # # #     data = extract_video(video_path, detector_factory)
# # # # # #     cache_path.parent.mkdir(parents=True, exist_ok=True)
# # # # # #     np.savez_compressed(cache_path, pose=data["pose"], lhand=data["lhand"],
# # # # # #                         rhand=data["rhand"], fps=data["fps"], version=CACHE_VERSION)
# # # # # #     return data, False


# # # # # # # =====================================================================
# # # # # # # 5. Clean-up: resample, fill gaps, smooth, trim, join
# # # # # # # =====================================================================
# # # # # # def resample(arr, src_fps, dst_fps):
# # # # # #     T = len(arr)
# # # # # #     if T < 2 or abs(src_fps - dst_fps) < 1e-3:
# # # # # #         return arr
# # # # # #     new_T = max(2, int(round((T - 1) * dst_fps / src_fps)) + 1)
# # # # # #     t = np.linspace(0, T - 1, new_T)
# # # # # #     i0 = np.floor(t).astype(int)
# # # # # #     i1 = np.minimum(i0 + 1, T - 1)
# # # # # #     a = (t - i0).reshape((-1,) + (1,) * (arr.ndim - 1))
# # # # # #     return arr[i0] * (1 - a) + arr[i1] * a   # NaN stays NaN if either neighbour is missing


# # # # # # def fill_gaps(arr, max_gap, hold_edges):
# # # # # #     T = len(arr)
# # # # # #     flat = arr.reshape(T, -1).astype(np.float64)
# # # # # #     valid = ~np.isnan(flat).any(axis=1)
# # # # # #     idx = np.where(valid)[0]
# # # # # #     if len(idx) == 0:
# # # # # #         return arr
# # # # # #     out = flat.copy()
# # # # # #     for a, b in zip(idx[:-1], idx[1:]):
# # # # # #         gap = b - a - 1
# # # # # #         if 0 < gap <= max_gap:
# # # # # #             for k in range(1, gap + 1):
# # # # # #                 w = k / (gap + 1)
# # # # # #                 out[a + k] = flat[a] * (1 - w) + flat[b] * w
# # # # # #     if hold_edges:
# # # # # #         out[:idx[0]] = flat[idx[0]]
# # # # # #         out[idx[-1] + 1:] = flat[idx[-1]]
# # # # # #     return out.reshape(arr.shape).astype(np.float32)


# # # # # # def hold_last_valid(arr):
# # # # # #     """Replace remaining NaN frames by the previous (or next) valid frame."""
# # # # # #     T = len(arr)
# # # # # #     flat = arr.reshape(T, -1).copy()
# # # # # #     valid = ~np.isnan(flat).any(axis=1)
# # # # # #     if not valid.any():
# # # # # #         return arr
# # # # # #     last = None
# # # # # #     for i in range(T):
# # # # # #         if valid[i]:
# # # # # #             last = flat[i].copy()
# # # # # #         elif last is not None:
# # # # # #             flat[i] = last
# # # # # #     first = np.where(valid)[0][0]
# # # # # #     flat[:first] = flat[first]
# # # # # #     return flat.reshape(arr.shape)


# # # # # # def smooth_nan(arr, sigma):
# # # # # #     """Gaussian smoothing along time; invalid (NaN) frames stay invalid."""
# # # # # #     T = len(arr)
# # # # # #     if sigma <= 0 or T < 2:
# # # # # #         return arr
# # # # # #     flat = arr.reshape(T, -1).astype(np.float64)
# # # # # #     valid = ~np.isnan(flat).any(axis=1)
# # # # # #     if not valid.any():
# # # # # #         return arr
# # # # # #     i = np.arange(T)
# # # # # #     W = np.exp(-0.5 * ((i[:, None] - i[None, :]) / sigma) ** 2) * valid[None, :]
# # # # # #     num = W @ np.where(valid[:, None], flat, 0.0)
# # # # # #     den = np.maximum(W.sum(axis=1, keepdims=True), 1e-9)
# # # # # #     out = num / den
# # # # # #     out[~valid] = np.nan
# # # # # #     return out.reshape(arr.shape).astype(np.float32)


# # # # # # def body_keypoints(pose):
# # # # # #     """(T,33,3) MediaPipe pose -> (T,17,3) avatar keypoints (order = BODY_NAMES)."""
# # # # # #     hips = (pose[:, 23] + pose[:, 24]) / 2
# # # # # #     neck = (pose[:, 11] + pose[:, 12]) / 2
# # # # # #     head = (pose[:, 7] + pose[:, 8]) / 2
# # # # # #     spine1 = hips + (neck - hips) / 3
# # # # # #     spine2 = hips + (neck - hips) * 2 / 3
# # # # # #     kp = [hips, spine1, spine2, neck, head,
# # # # # #           pose[:, 11], pose[:, 13], pose[:, 15],
# # # # # #           pose[:, 12], pose[:, 14], pose[:, 16],
# # # # # #           pose[:, 23], pose[:, 25], pose[:, 27],
# # # # # #           pose[:, 24], pose[:, 26], pose[:, 28]]
# # # # # #     return np.stack(kp, axis=1).astype(np.float32)


# # # # # # def active_range(pose, threshold, pad):
# # # # # #     """Frames where at least one wrist is clearly above the hips (= signing)."""
# # # # # #     T = len(pose)
# # # # # #     hips_y = (pose[:, 23, 1] + pose[:, 24, 1]) / 2
# # # # # #     wrist_y = np.minimum(pose[:, 15, 1], pose[:, 16, 1])   # MediaPipe y points DOWN
# # # # # #     idx = np.where(wrist_y < hips_y - threshold)[0]
# # # # # #     if len(idx) == 0:
# # # # # #         return 0, T
# # # # # #     return max(0, int(idx[0]) - pad), min(T, int(idx[-1]) + pad + 1)


# # # # # # def process_clip(raw, fps, args):
# # # # # #     pose = resample(raw["pose"], raw["fps"], fps)
# # # # # #     lh = resample(raw["lhand"], raw["fps"], fps)
# # # # # #     rh = resample(raw["rhand"], raw["fps"], fps)

# # # # # #     ok_ratio = float((~np.isnan(pose.reshape(len(pose), -1)).any(axis=1)).mean())
# # # # # #     if ok_ratio < 0.3:
# # # # # #         return None, ok_ratio

# # # # # #     pose = fill_gaps(pose, max_gap=int(fps * 0.6), hold_edges=True)
# # # # # #     pose = hold_last_valid(pose)
# # # # # #     pose = smooth_nan(pose, args.smooth_body)
# # # # # #     lh = smooth_nan(fill_gaps(lh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)
# # # # # #     rh = smooth_nan(fill_gaps(rh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)

# # # # # #     if not args.no_trim:
# # # # # #         a, b = active_range(pose, args.rest_threshold, int(round(fps * 0.12)))
# # # # # #         pose, lh, rh = pose[a:b], lh[a:b], rh[a:b]
# # # # # #     return {"body": body_keypoints(pose), "lh": lh, "rh": rh}, ok_ratio


# # # # # # def _ease(w):
# # # # # #     return 0.5 - 0.5 * np.cos(np.pi * w)


# # # # # # def assemble(clips, fps, transition_s, hold_s):
# # # # # #     """clips: [{gloss, video, body, lh, rh}] -> one timeline."""
# # # # # #     ntr = max(0, int(round(transition_s * fps)))
# # # # # #     hold = max(0, int(round(hold_s * fps)))
# # # # # #     B, LH, RH, segs = [], [], [], []
# # # # # #     cursor = 0

# # # # # #     def add(body, lh, rh):
# # # # # #         nonlocal cursor
# # # # # #         B.append(body)
# # # # # #         LH.append(lh)
# # # # # #         RH.append(rh)
# # # # # #         cursor += len(body)

# # # # # #     for i, c in enumerate(clips):
# # # # # #         seg_start = cursor
# # # # # #         if i == 0 and hold:
# # # # # #             add(np.repeat(c["body"][:1], hold, 0), np.repeat(c["lh"][:1], hold, 0),
# # # # # #                 np.repeat(c["rh"][:1], hold, 0))
# # # # # #         if i > 0 and ntr:
# # # # # #             p = clips[i - 1]
# # # # # #             w = _ease(np.arange(1, ntr + 1) / (ntr + 1)).reshape(-1, 1, 1)
# # # # # #             body = p["body"][-1][None] * (1 - w) + c["body"][0][None] * w
# # # # # #             lh = p["lh"][-1][None] * (1 - w) + c["lh"][0][None] * w     # NaN if either is missing
# # # # # #             rh = p["rh"][-1][None] * (1 - w) + c["rh"][0][None] * w
# # # # # #             add(body, lh, rh)
# # # # # #         add(c["body"], c["lh"], c["rh"])
# # # # # #         if i == len(clips) - 1 and hold:
# # # # # #             add(np.repeat(c["body"][-1:], hold, 0), np.repeat(c["lh"][-1:], hold, 0),
# # # # # #                 np.repeat(c["rh"][-1:], hold, 0))
# # # # # #         segs.append({"s": seg_start, "e": cursor, "gloss": c["gloss"], "video": c["video"]})

# # # # # #     body = np.concatenate(B).astype(np.float64)
# # # # # #     lh = np.concatenate(LH).astype(np.float64)
# # # # # #     rh = np.concatenate(RH).astype(np.float64)
# # # # # #     lv = (~np.isnan(lh.reshape(len(lh), -1)).any(axis=1)).astype(int)
# # # # # #     rv = (~np.isnan(rh.reshape(len(rh), -1)).any(axis=1)).astype(int)
# # # # # #     lh = np.nan_to_num(lh, nan=0.0)
# # # # # #     rh = np.nan_to_num(rh, nan=0.0)
# # # # # #     return {"fps": fps, "n": int(len(body)),
# # # # # #             "body": np.round(body, 4).ravel().tolist(),
# # # # # #             "lh": np.round(lh, 4).ravel().tolist(),
# # # # # #             "rh": np.round(rh, 4).ravel().tolist(),
# # # # # #             "lv": lv.tolist(), "rv": rv.tolist(), "segments": segs}


# # # # # # # =====================================================================
# # # # # # # 6. The standalone player (HTML + JavaScript, three.js r128 from a CDN)
# # # # # # # =====================================================================
# # # # # # HTML_TEMPLATE = r'''<!DOCTYPE html>
# # # # # # <html lang="vi">
# # # # # # <head>
# # # # # # <meta charset="utf-8">
# # # # # # <meta name="viewport" content="width=device-width, initial-scale=1">
# # # # # # <title>__TITLE__</title>
# # # # # # <style>
# # # # # #   :root { color-scheme: dark; }
# # # # # #   html, body { margin: 0; height: 100%; overflow: hidden; background: #0b1220; color: #e5e7eb;
# # # # # #                font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
# # # # # #   #stage { position: fixed; inset: 0; }
# # # # # #   #stage canvas { display: block; }
# # # # # #   #caption { position: fixed; top: 18px; left: 0; right: 0; text-align: center; pointer-events: none;
# # # # # #              font-size: 38px; font-weight: 700; text-shadow: 0 2px 12px #000; min-height: 46px; }
# # # # # #   #panel { position: fixed; left: 12px; right: 12px; bottom: 12px; padding: 10px 14px;
# # # # # #            background: rgba(15, 23, 42, .90); border: 1px solid #334155; border-radius: 12px; }
# # # # # #   .row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 5px 0; }
# # # # # #   button, select { background: #1e293b; color: #e5e7eb; border: 1px solid #475569; border-radius: 8px;
# # # # # #                    padding: 6px 12px; font-size: 14px; cursor: pointer; }
# # # # # #   button:hover { background: #334155; }
# # # # # #   button.rec { border-color: #ef4444; }
# # # # # #   input[type=range] { flex: 1; min-width: 160px; }
# # # # # #   label { font-size: 13px; color: #cbd5e1; display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
# # # # # #   .chip { padding: 3px 10px; border-radius: 999px; border: 1px solid #475569; font-size: 13px; cursor: pointer; }
# # # # # #   .chip.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
# # # # # #   #status { font-size: 12px; color: #94a3b8; }
# # # # # #   #status.err { color: #fca5a5; font-size: 14px; }
# # # # # # </style>
# # # # # # </head>
# # # # # # <body>
# # # # # # <div id="stage"></div>
# # # # # # <div id="caption"></div>
# # # # # # <div id="panel">
# # # # # #   <div class="row">
# # # # # #     <button id="play">Tạm dừng</button>
# # # # # #     <button id="restart">Phát lại</button>
# # # # # #     <input type="range" id="seek" min="0" max="1" step="1" value="0">
# # # # # #     <span id="time">0.0 / 0.0 s</span>
# # # # # #     <select id="speed" title="Tốc độ">
# # # # # #       <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
# # # # # #       <option value="1" selected>1x</option><option value="1.5">1.5x</option>
# # # # # #     </select>
# # # # # #   </div>
# # # # # #   <div class="row" id="chips"></div>
# # # # # #   <div class="row">
# # # # # #     <label><input type="checkbox" id="o_loop" checked> Lặp lại</label>
# # # # # #     <label><input type="checkbox" id="o_fingers" checked> Ngón tay</label>
# # # # # #     <label><input type="checkbox" id="o_legs"> Chân</label>
# # # # # #     <label><input type="checkbox" id="o_mirror"> Lật trái/phải</label>
# # # # # #     <label><input type="checkbox" id="o_flipz"> Đảo chiều sâu</label>
# # # # # #     <label><input type="checkbox" id="o_swap"> Đổi tay trái/phải</label>
# # # # # #     <button id="rec" class="rec">Ghi video (.webm)</button>
# # # # # #   </div>
# # # # # #   <div id="status">Đang tải mô hình...</div>
# # # # # # </div>

# # # # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
# # # # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
# # # # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
# # # # # # <script>
# # # # # # "use strict";
# # # # # # const DATA = __DATA_JSON__;
# # # # # # const GLB_B64 = "__GLB_B64__";
# # # # # # const $ = (id) => document.getElementById(id);

# # # # # # function fail(msg) { const s = $("status"); s.textContent = msg; s.className = "err"; }

# # # # # # const N = DATA.n, FPS = DATA.fps;
# # # # # # const body = DATA.body, lh = DATA.lh, rh = DATA.rh, lv = DATA.lv, rv = DATA.rv;
# # # # # # const opts = { mirror: false, flipZ: false, swapHands: false, legs: false,
# # # # # #                fingers: true, loop: true, speed: 1 };

# # # # # # // ==== RETARGET START ====
# # # # # # // Turns MediaPipe 3D points into bone rotations of the Mixamo-style Xbot skeleton.
# # # # # # const BODY = ["Hips","Spine1","Spine2","Neck","Head","LeftArm","LeftForeArm","LeftHand",
# # # # # #   "RightArm","RightForeArm","RightHand","LeftUpLeg","LeftLeg","LeftFoot","RightUpLeg","RightLeg","RightFoot"];
# # # # # # const FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"];
# # # # # # // [bone, bone it must point to] - parents first
# # # # # # const AIM_PAIRS = [
# # # # # #   ["Hips","Spine1"], ["Spine1","Spine2"], ["Spine2","Neck"], ["Neck","Head"],
# # # # # #   ["LeftArm","LeftForeArm"], ["LeftForeArm","LeftHand"],
# # # # # #   ["RightArm","RightForeArm"], ["RightForeArm","RightHand"],
# # # # # #   ["LeftUpLeg","LeftLeg"], ["LeftLeg","LeftFoot"],
# # # # # #   ["RightUpLeg","RightLeg"], ["RightLeg","RightFoot"],
# # # # # # ];
# # # # # # const LEG_BONES = ["LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"];

# # # # # # const bones = {};      // clean name -> bone
# # # # # # const restQ = {};      // clean name -> rest-pose rotation
# # # # # # let rootObj = null;
# # # # # # const handState = { Left: { w: 0, last: null }, Right: { w: 0, last: null } };

# # # # # # function cleanName(n) { return n.replace(/^mixamorig:?/, ""); }

# # # # # # function setupModel(model) {
# # # # # #   rootObj = model;
# # # # # #   model.traverse((o) => {
# # # # # #     if (o.isBone) { const c = cleanName(o.name); bones[c] = o; restQ[c] = o.quaternion.clone(); }
# # # # # #   });
# # # # # #   let fingerBases = 0;
# # # # # #   for (const s of ["Left", "Right"]) for (const f of FINGERS) if (bones[s + "Hand" + f + "1"]) fingerBases++;
# # # # # #   return { bones: Object.keys(bones).length, fingerBases };
# # # # # # }

# # # # # # function resetPose() {
# # # # # #   for (const k in bones) bones[k].quaternion.copy(restQ[k]);
# # # # # #   if (rootObj) rootObj.updateMatrixWorld(true);
# # # # # # }

# # # # # # // Rotate a bone by a rotation given in WORLD space.
# # # # # # function applyWorldRotation(bone, qWorld) {
# # # # # #   if (!bone || !bone.parent) return;
# # # # # #   bone.parent.updateWorldMatrix(true, false);
# # # # # #   const pq = bone.parent.getWorldQuaternion(new THREE.Quaternion());
# # # # # #   const adj = pq.clone().invert().multiply(qWorld).multiply(pq);
# # # # # #   bone.quaternion.premultiply(adj);
# # # # # #   bone.updateMatrixWorld(true);
# # # # # # }

# # # # # # // Make the direction  bone -> child  point along `dir` (world space).
# # # # # # function aimBone(bone, child, dir) {
# # # # # #   if (!bone || !child || dir.lengthSq() < 1e-10) return;
# # # # # #   bone.updateWorldMatrix(true, true);
# # # # # #   const p = bone.getWorldPosition(new THREE.Vector3());
# # # # # #   const c = child.getWorldPosition(new THREE.Vector3());
# # # # # #   const cur = c.sub(p);
# # # # # #   if (cur.lengthSq() < 1e-12) return;
# # # # # #   cur.normalize();
# # # # # #   applyWorldRotation(bone, new THREE.Quaternion().setFromUnitVectors(cur, dir.clone().normalize()));
# # # # # # }

# # # # # # // Twist a bone around `axisDir` so that curSide lines up with tgtSide (palm orientation).
# # # # # # function rollBoneAround(bone, axisDir, curSide, tgtSide) {
# # # # # #   const a = axisDir.clone().normalize();
# # # # # #   const c = curSide.clone().sub(a.clone().multiplyScalar(curSide.dot(a)));
# # # # # #   const t = tgtSide.clone().sub(a.clone().multiplyScalar(tgtSide.dot(a)));
# # # # # #   if (c.lengthSq() < 1e-10 || t.lengthSq() < 1e-10) return;
# # # # # #   c.normalize(); t.normalize();
# # # # # #   let angle = Math.acos(THREE.MathUtils.clamp(c.dot(t), -1, 1));
# # # # # #   if (new THREE.Vector3().crossVectors(c, t).dot(a) < 0) angle = -angle;
# # # # # #   applyWorldRotation(bone, new THREE.Quaternion().setFromAxisAngle(a, angle));
# # # # # # }

# # # # # # function blendToRest(name, w) {
# # # # # #   if (w >= 0.999 || !bones[name]) return;
# # # # # #   const q = bones[name].quaternion.clone();
# # # # # #   bones[name].quaternion.copy(restQ[name]).slerp(q, w);
# # # # # #   bones[name].updateMatrixWorld(true);
# # # # # # }

# # # # # # function applyBody(P) {
# # # # # #   for (const [a, b] of AIM_PAIRS) {
# # # # # #     if (!opts.legs && LEG_BONES.includes(a)) continue;
# # # # # #     if (!bones[a] || !bones[b] || !P[a] || !P[b]) continue;
# # # # # #     aimBone(bones[a], bones[b], P[b].clone().sub(P[a]));
# # # # # #   }
# # # # # # }

# # # # # # // H: {Wrist, Thumb1..Pinky4} -> Vector3 ; w: 0..1 blend weight (0 = rest pose)
# # # # # # function applyHand(side, H, w) {
# # # # # #   if (!H || w <= 0.001) return;
# # # # # #   const wrist = bones[side + "Hand"], mid1 = bones[side + "HandMiddle1"];
# # # # # #   const idx1 = bones[side + "HandIndex1"], pky1 = bones[side + "HandPinky1"];
# # # # # #   if (wrist && mid1 && H.Wrist && H.Middle1) {
# # # # # #     const axis = H.Middle1.clone().sub(H.Wrist);
# # # # # #     aimBone(wrist, mid1, axis);
# # # # # #     if (idx1 && pky1 && H.Index1 && H.Pinky1) {
# # # # # #       const a = idx1.getWorldPosition(new THREE.Vector3());
# # # # # #       const b = pky1.getWorldPosition(new THREE.Vector3());
# # # # # #       rollBoneAround(wrist, axis, a.sub(b), H.Index1.clone().sub(H.Pinky1));
# # # # # #     }
# # # # # #     blendToRest(side + "Hand", w);
# # # # # #   }
# # # # # #   for (const f of FINGERS) {
# # # # # #     for (let n = 1; n <= 3; n++) {
# # # # # #       const name = side + "Hand" + f + n;
# # # # # #       const bone = bones[name], child = bones[side + "Hand" + f + (n + 1)];
# # # # # #       const p0 = H[f + n], p1 = H[f + (n + 1)];
# # # # # #       if (bone && child && p0 && p1) {
# # # # # #         aimBone(bone, child, p1.clone().sub(p0));
# # # # # #         blendToRest(name, w);
# # # # # #       }
# # # # # #     }
# # # # # #   }
# # # # # # }

# # # # # # // MediaPipe camera frame (x right, y down, z away) -> model frame (x right, y up, z towards viewer)
# # # # # # function toModel(x, y, z) {
# # # # # #   return new THREE.Vector3((opts.mirror ? -1 : 1) * x, -y, -(opts.flipZ ? -1 : 1) * z);
# # # # # # }

# # # # # # function sampleFrame(f) {
# # # # # #   const f0 = Math.max(0, Math.min(N - 1, Math.floor(f)));
# # # # # #   const f1 = Math.min(f0 + 1, N - 1);
# # # # # #   const a = Math.max(0, Math.min(1, f - f0));
# # # # # #   const lerp = (u, v) => u + (v - u) * a;

# # # # # #   const P = {};
# # # # # #   for (let j = 0; j < BODY.length; j++) {
# # # # # #     const o0 = (f0 * BODY.length + j) * 3, o1 = (f1 * BODY.length + j) * 3;
# # # # # #     P[BODY[j]] = toModel(lerp(body[o0], body[o1]), lerp(body[o0 + 1], body[o1 + 1]), lerp(body[o0 + 2], body[o1 + 2]));
# # # # # #   }

# # # # # #   const hands = { Left: null, Right: null };
# # # # # #   const srcs = opts.swapHands
# # # # # #     ? [["Left", rh, rv], ["Right", lh, lv]]
# # # # # #     : [["Left", lh, lv], ["Right", rh, rv]];
# # # # # #   for (const [side, arr, val] of srcs) {
# # # # # #     if (!(val[f0] && val[f1])) continue;
# # # # # #     const pt = (k) => {
# # # # # #       const o0 = (f0 * 21 + k) * 3, o1 = (f1 * 21 + k) * 3;
# # # # # #       return toModel(lerp(arr[o0], arr[o1]), lerp(arr[o0 + 1], arr[o1 + 1]), lerp(arr[o0 + 2], arr[o1 + 2]));
# # # # # #     };
# # # # # #     const H = { Wrist: pt(0) };
# # # # # #     FINGERS.forEach((fn, fi) => { for (let n = 1; n <= 4; n++) H[fn + n] = pt(1 + 4 * fi + (n - 1)); });
# # # # # #     hands[side] = H;
# # # # # #   }
# # # # # #   return { P, hands };
# # # # # # }

# # # # # # // Pose the whole avatar for (fractional) frame f. dt = seconds since last call.
# # # # # # function applyFrame(f, dt) {
# # # # # #   if (!rootObj) return;
# # # # # #   const { P, hands } = sampleFrame(f);
# # # # # #   resetPose();                      // always start from the rest pose: no drift, no accumulated twist
# # # # # #   applyBody(P);
# # # # # #   for (const side of ["Left", "Right"]) {
# # # # # #     const st = handState[side], H = hands[side];
# # # # # #     if (H && opts.fingers) { st.last = H; st.w = Math.min(1, st.w + dt / 0.12); }
# # # # # #     else { st.w = Math.max(0, st.w - dt / 0.12); }
# # # # # #     if (st.last && st.w > 0) applyHand(side, H && opts.fingers ? H : st.last, st.w);
# # # # # #   }
# # # # # #   rootObj.updateMatrixWorld(true);
# # # # # # }
# # # # # # const RETARGET = { bones, restQ, setupModel, applyFrame, sampleFrame, handState, opts, resetPose };
# # # # # # // ==== RETARGET END ====

# # # # # # (function main() {
# # # # # #   if (typeof THREE === "undefined" || !THREE.GLTFLoader || !THREE.OrbitControls) {
# # # # # #     fail("Không tải được three.js từ CDN. Hãy kiểm tra kết nối Internet rồi mở lại trang.");
# # # # # #     return;
# # # # # #   }

# # # # # #   // ---------- scene ----------
# # # # # #   const stage = $("stage");
# # # # # #   const renderer = new THREE.WebGLRenderer({ antialias: true });
# # # # # #   renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
# # # # # #   renderer.outputEncoding = THREE.sRGBEncoding;
# # # # # #   renderer.shadowMap.enabled = true;
# # # # # #   stage.appendChild(renderer.domElement);

# # # # # #   const scene = new THREE.Scene();
# # # # # #   scene.background = new THREE.Color(0x0b1220);
# # # # # #   const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
# # # # # #   camera.position.set(0, 1.5, 2.7);
# # # # # #   const controls = new THREE.OrbitControls(camera, renderer.domElement);
# # # # # #   controls.target.set(0, 1.3, 0);
# # # # # #   controls.update();

# # # # # #   scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 0.9));
# # # # # #   const sun = new THREE.DirectionalLight(0xffffff, 0.8);
# # # # # #   sun.position.set(2, 4, 3);
# # # # # #   sun.castShadow = true;
# # # # # #   scene.add(sun);
# # # # # #   const ground = new THREE.Mesh(new THREE.CircleGeometry(3, 48),
# # # # # #     new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 1 }));
# # # # # #   ground.rotation.x = -Math.PI / 2;
# # # # # #   ground.receiveShadow = true;
# # # # # #   scene.add(ground);
# # # # # #   scene.add(new THREE.GridHelper(6, 24, 0x334155, 0x1f2937));

# # # # # #   function resize() {
# # # # # #     const w = window.innerWidth, h = window.innerHeight;
# # # # # #     renderer.setSize(w, h);
# # # # # #     camera.aspect = w / h;
# # # # # #     camera.updateProjectionMatrix();
# # # # # #   }
# # # # # #   window.addEventListener("resize", resize);
# # # # # #   resize();

# # # # # #   // ---------- UI ----------
# # # # # #   const seek = $("seek");
# # # # # #   seek.max = Math.max(1, N - 1);
# # # # # #   const chips = $("chips");
# # # # # #   const segEls = DATA.segments.map((s, i) => {
# # # # # #     const el = document.createElement("span");
# # # # # #     el.className = "chip";
# # # # # #     el.textContent = s.gloss;
# # # # # #     el.title = s.video;
# # # # # #     el.onclick = () => { tFrame = s.s; };
# # # # # #     chips.appendChild(el);
# # # # # #     return el;
# # # # # #   });

# # # # # #   let playing = true, tFrame = 0, recording = null;
# # # # # #   const setPlayLabel = () => { $("play").textContent = playing ? "Tạm dừng" : "Phát"; };
# # # # # #   $("play").onclick = () => { playing = !playing; if (playing && tFrame >= N - 1) tFrame = 0; setPlayLabel(); };
# # # # # #   $("restart").onclick = () => { tFrame = 0; playing = true; setPlayLabel(); };
# # # # # #   seek.oninput = () => { tFrame = +seek.value; };
# # # # # #   $("speed").onchange = (e) => { opts.speed = +e.target.value; };
# # # # # #   for (const [id, key] of [["o_loop","loop"],["o_fingers","fingers"],["o_legs","legs"],
# # # # # #                            ["o_mirror","mirror"],["o_flipz","flipZ"],["o_swap","swapHands"]]) {
# # # # # #     $(id).onchange = (e) => { opts[key] = e.target.checked; };
# # # # # #   }
# # # # # #   window.addEventListener("keydown", (e) => { if (e.code === "Space") { e.preventDefault(); $("play").click(); } });

# # # # # #   $("rec").onclick = () => {
# # # # # #     if (!window.MediaRecorder) { alert("Trình duyệt không hỗ trợ ghi video. Hãy dùng Chrome hoặc Edge."); return; }
# # # # # #     if (recording) return;
# # # # # #     const stream = renderer.domElement.captureStream(30);
# # # # # #     const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]
# # # # # #       .find((m) => MediaRecorder.isTypeSupported(m));
# # # # # #     const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 6000000 });
# # # # # #     const chunks = [];
# # # # # #     rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
# # # # # #     rec.onstop = () => {
# # # # # #       const a = document.createElement("a");
# # # # # #       a.href = URL.createObjectURL(new Blob(chunks, { type: "video/webm" }));
# # # # # #       a.download = "sign_avatar.webm";
# # # # # #       a.click();
# # # # # #       recording = null;
# # # # # #       $("rec").textContent = "Ghi video (.webm)";
# # # # # #     };
# # # # # #     recording = { rec, prevLoop: opts.loop };
# # # # # #     opts.loop = false;
# # # # # #     tFrame = 0; playing = true; setPlayLabel();
# # # # # #     rec.start();
# # # # # #     $("rec").textContent = "Đang ghi...";
# # # # # #   };

# # # # # #   // ---------- model ----------
# # # # # #   let loaded = false;
# # # # # #   try {
# # # # # #     const bin = atob(GLB_B64);
# # # # # #     const buf = new Uint8Array(bin.length);
# # # # # #     for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
# # # # # #     new THREE.GLTFLoader().parse(buf.buffer, "", (gltf) => {
# # # # # #       const model = gltf.scene;
# # # # # #       let box = new THREE.Box3().setFromObject(model);
# # # # # #       model.scale.setScalar(1.75 / Math.max(0.01, box.max.y - box.min.y));
# # # # # #       box = new THREE.Box3().setFromObject(model);
# # # # # #       model.position.y -= box.min.y;
# # # # # #       model.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
# # # # # #       scene.add(model);
# # # # # #       const info = setupModel(model);
# # # # # #       loaded = true;
# # # # # #       $("status").textContent = "Xương: " + info.bones + " | xương ngón tay: " + info.fingerBases +
# # # # # #         "/10 | " + N + " khung hình, " + FPS + " fps | các từ: " + DATA.segments.map((s) => s.gloss).join(" → ");
# # # # # #       if (info.fingerBases < 10) $("status").textContent += "  (mô hình thiếu xương ngón tay: ngón sẽ không cử động)";
# # # # # #     }, (err) => { fail("Không đọc được mô hình Xbot: " + (err && err.message ? err.message : err)); });
# # # # # #   } catch (e) { fail("Lỗi nạp mô hình: " + e); }

# # # # # #   // ---------- loop ----------
# # # # # #   let last = performance.now();
# # # # # #   function tick(now) {
# # # # # #     const dt = Math.min(0.1, (now - last) / 1000);
# # # # # #     last = now;
# # # # # #     if (playing) {
# # # # # #       tFrame += dt * FPS * opts.speed;
# # # # # #       if (tFrame >= N - 1) {
# # # # # #         if (recording) {
# # # # # #           tFrame = N - 1; playing = false; setPlayLabel();
# # # # # #           opts.loop = recording.prevLoop;
# # # # # #           const r = recording.rec; setTimeout(() => r.state !== "inactive" && r.stop(), 250);
# # # # # #         } else if (opts.loop) tFrame = 0;
# # # # # #         else { tFrame = N - 1; playing = false; setPlayLabel(); }
# # # # # #       }
# # # # # #     }
# # # # # #     if (loaded) applyFrame(tFrame, dt);
# # # # # #     const fi = Math.floor(tFrame);
# # # # # #     const idx = DATA.segments.findIndex((s) => fi >= s.s && fi < s.e);
# # # # # #     const cur = idx >= 0 ? idx : DATA.segments.length - 1;
# # # # # #     $("caption").textContent = DATA.segments[cur] ? DATA.segments[cur].gloss : "";
# # # # # #     segEls.forEach((el, i) => el.classList.toggle("on", i === cur));
# # # # # #     seek.value = fi;
# # # # # #     $("time").textContent = (tFrame / FPS).toFixed(1) + " / " + (N / FPS).toFixed(1) + " s";
# # # # # #     controls.update();
# # # # # #     renderer.render(scene, camera);
# # # # # #     requestAnimationFrame(tick);
# # # # # #   }
# # # # # #   requestAnimationFrame(tick);
# # # # # # })();
# # # # # # </script>
# # # # # # </body>
# # # # # # </html>
# # # # # # '''


# # # # # # def write_html(timeline, xbot_path, out_path, title):
# # # # # #     glb = Path(xbot_path).read_bytes()
# # # # # #     data_json = json.dumps(timeline, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
# # # # # #     html = (HTML_TEMPLATE
# # # # # #             .replace("__TITLE__", title.replace("<", "&lt;"))
# # # # # #             .replace("__DATA_JSON__", data_json)
# # # # # #             .replace("__GLB_B64__", base64.b64encode(glb).decode("ascii")))
# # # # # #     out = Path(out_path)
# # # # # #     out.parent.mkdir(parents=True, exist_ok=True)
# # # # # #     out.write_text(html, encoding="utf-8")
# # # # # #     return out


# # # # # # # =====================================================================
# # # # # # # 7. Command line
# # # # # # # =====================================================================
# # # # # # def build_parser():
# # # # # #     p = argparse.ArgumentParser(
# # # # # #         description="Chuỗi gloss -> avatar Xbot chuyển động liên tục (file HTML độc lập).")
# # # # # #     g = p.add_argument_group("đầu vào")
# # # # # #     g.add_argument("--glosses", nargs="+", help='Danh sách gloss, ví dụ: --glosses "bạn" "đi học" "có không"')
# # # # # #     g.add_argument("--sentence", help='Các gloss ngăn cách bằng dấu |, ví dụ: "bạn | đi học | có không"')
# # # # # #     g.add_argument("--glosses-file", help="File .json (list) hoặc .txt (mỗi dòng 1 gloss)")
# # # # # #     g = p.add_argument_group("đường dẫn")
# # # # # #     g.add_argument("--labels", help="File ánh xạ VIDEO/LABEL (csv, tsv, txt, xlsx, json)")
# # # # # #     g.add_argument("--videos", default=DEFAULT_VIDEOS, help="Thư mục chứa các video của dataset")
# # # # # #     g.add_argument("--xbot", default=DEFAULT_XBOT, help="File Xbot.glb")
# # # # # #     g.add_argument("--cache", default=DEFAULT_CACHE, help="Thư mục lưu tọa độ đã tính (.npz)")
# # # # # #     g.add_argument("--out", default=DEFAULT_OUT, help="File HTML đầu ra")
# # # # # #     g = p.add_argument_group("chọn video")
# # # # # #     g.add_argument("--region", default="B,T,N", help="Thứ tự ưu tiên giọng vùng: B=Bắc, T=Trung, N=Nam")
# # # # # #     g.add_argument("--search", help="Tìm nhãn chứa chuỗi này (không cần dấu) rồi thoát")
# # # # # #     g.add_argument("--precompute-all", action="store_true",
# # # # # #                    help="Tính trước tọa độ cho mọi gloss (lâu, chạy một lần)")
# # # # # #     g = p.add_argument_group("chuyển động")
# # # # # #     g.add_argument("--fps", type=float, default=30.0)
# # # # # #     g.add_argument("--transition", type=float, default=0.25, help="Giây chuyển tiếp giữa 2 từ")
# # # # # #     g.add_argument("--hold", type=float, default=0.2, help="Giây giữ tư thế đầu/cuối")
# # # # # #     g.add_argument("--smooth-body", type=float, default=1.5, help="Độ mượt thân (khung hình, 0 = tắt)")
# # # # # #     g.add_argument("--smooth-hands", type=float, default=1.0, help="Độ mượt ngón tay (0 = tắt)")
# # # # # #     g.add_argument("--hand-gap", type=int, default=6, help="Nội suy khi mất tay tối đa N khung")
# # # # # #     g.add_argument("--no-trim", action="store_true", help="Không cắt đoạn tay buông ở đầu/cuối video")
# # # # # #     g.add_argument("--rest-threshold", type=float, default=0.10,
# # # # # #                    help="Cổ tay phải cao hơn hông bao nhiêu mét để tính là đang ký")
# # # # # #     g.add_argument("--complexity", type=int, default=1, choices=[0, 1, 2],
# # # # # #                    help="Độ chính xác MediaPipe Pose (2 = chính xác nhất, chậm nhất)")
# # # # # #     p.add_argument("--open", action="store_true", help="Mở file HTML sau khi tạo")
# # # # # #     return p


# # # # # # def get_glosses(args):
# # # # # #     if args.glosses:
# # # # # #         return [g for g in args.glosses if g.strip()]
# # # # # #     if args.sentence:
# # # # # #         return [g.strip() for g in args.sentence.split("|") if g.strip()]
# # # # # #     if args.glosses_file:
# # # # # #         txt = read_text_auto(args.glosses_file)
# # # # # #         if args.glosses_file.lower().endswith(".json"):
# # # # # #             return [str(g) for g in json.loads(txt)]
# # # # # #         return [l.strip() for l in txt.splitlines() if l.strip()]
# # # # # #     return []


# # # # # # def main(argv=None, detector_factory=None):
# # # # # #     args = build_parser().parse_args(argv)
# # # # # #     videos_dir = Path(args.videos)

# # # # # #     labels = args.labels or find_labels_file(videos_dir)
# # # # # #     if not labels or not Path(labels).exists():
# # # # # #         print("Không tìm thấy file nhãn. Hãy chỉ rõ bằng --labels \"đường\\dẫn\\file.csv\"")
# # # # # #         return 2
# # # # # #     records = load_records(labels)
# # # # # #     index = GlossIndex(records, args.region.split(","))
# # # # # #     print(f"Đã đọc {len(records)} video / {len(index.by_key)} khóa tra cứu từ: {labels}")

# # # # # #     if args.search:
# # # # # #         hits = index.search(args.search)
# # # # # #         print(f'\nCác nhãn chứa "{args.search}" ({len(hits)} kết quả đầu):')
# # # # # #         for r in hits:
# # # # # #             print(f"  {r['video']:<14} {r['label']}")
# # # # # #         return 0

# # # # # #     if detector_factory is None:
# # # # # #         detector_factory = lambda: MediaPipeDetector(args.complexity)

# # # # # #     if args.precompute_all:
# # # # # #         picks = {}
# # # # # #         for rec in index.recs:
# # # # # #             key = norm(rec["label"])
# # # # # #             if key not in picks:
# # # # # #                 picks[key] = index.choose(index.lookup(rec["label"]))[0]
# # # # # #         todo = sorted(picks.values(), key=lambda r: natural_key(r["stem"]))
# # # # # #         print(f"Tính trước {len(todo)} video (mỗi gloss một video)...")
# # # # # #         for i, rec in enumerate(todo, 1):
# # # # # #             vp = videos_dir / rec["video"]
# # # # # #             try:
# # # # # #                 _, hit = get_clip_data(vp, args.cache, detector_factory)
# # # # # #                 print(f"[{i}/{len(todo)}] {rec['video']} {'(đã có)' if hit else 'xong'}")
# # # # # #             except Exception as e:
# # # # # #                 print(f"[{i}/{len(todo)}] {rec['video']} LỖI: {e}")
# # # # # #         return 0

# # # # # #     glosses = get_glosses(args)
# # # # # #     if not glosses:
# # # # # #         raw = input('Nhập các gloss, ngăn cách bằng dấu | (ví dụ: bạn | đi học | có không): ')
# # # # # #         glosses = [g.strip() for g in raw.split("|") if g.strip()]
# # # # # #     if not glosses:
# # # # # #         print("Chưa có gloss nào.")
# # # # # #         return 2

# # # # # #     # ---- gloss -> video ----
# # # # # #     picks, problems = [], []
# # # # # #     for g in glosses:
# # # # # #         found, missing = index.resolve_one(g)
# # # # # #         picks += found
# # # # # #         for w in missing:
# # # # # #             sug = index.suggest(w)
# # # # # #             problems.append(f'Không có gloss "{w}"' + (f" (gần giống: {', '.join(sug)})" if sug else ""))
# # # # # #     print("\nChuỗi gloss -> video:")
# # # # # #     for g, rec, note in picks:
# # # # # #         print(f"  {g:<18} -> {rec['video']:<14} [{rec['label']}]" + (f"  ({note})" if note else ""))
# # # # # #     for p in problems:
# # # # # #         print("  CẢNH BÁO:", p)
# # # # # #     if not picks:
# # # # # #         return 1

# # # # # #     # ---- landmarks (cached) ----
# # # # # #     clips = []
# # # # # #     for i, (g, rec, _) in enumerate(picks, 1):
# # # # # #         vp = videos_dir / rec["video"]
# # # # # #         cache_file = Path(args.cache) / (rec["stem"] + ".npz")
# # # # # #         if not vp.exists() and not cache_file.exists():
# # # # # #             print(f"  CẢNH BÁO: không thấy video {vp}")
# # # # # #             continue
# # # # # #         try:
# # # # # #             raw, hit = get_clip_data(vp, args.cache, detector_factory)
# # # # # #         except Exception as e:
# # # # # #             print(f"  CẢNH BÁO: lỗi với {rec['video']}: {e}")
# # # # # #             continue
# # # # # #         clip, ok = process_clip(raw, args.fps, args)
# # # # # #         if clip is None:
# # # # # #             print(f"  CẢNH BÁO: {rec['video']} chỉ nhận diện được {ok:.0%} khung hình, bỏ qua")
# # # # # #             continue
# # # # # #         hands_ok = [float((~np.isnan(clip[k].reshape(len(clip[k]), -1)).any(axis=1)).mean())
# # # # # #                     for k in ("lh", "rh")]
# # # # # #         print(f"  [{i}/{len(picks)}] {rec['video']}: {len(clip['body'])} khung ({len(clip['body'])/args.fps:.1f}s), "
# # # # # #               f"có tay trái {hands_ok[0]:.0%} / tay phải {hands_ok[1]:.0%}" + ("" if hit else "  (vừa tính xong, đã lưu cache)"))
# # # # # #         clip.update({"gloss": g, "video": rec["video"]})
# # # # # #         clips.append(clip)
# # # # # #     if not clips:
# # # # # #         print("Không có video nào dùng được.")
# # # # # #         return 1

# # # # # #     # ---- one continuous timeline -> html ----
# # # # # #     timeline = assemble(clips, args.fps, args.transition, args.hold)
# # # # # #     if not Path(args.xbot).exists():
# # # # # #         print(f"Không thấy file Xbot: {args.xbot}  (dùng --xbot để chỉ đường dẫn)")
# # # # # #         return 2
# # # # # #     out = write_html(timeline, args.xbot, args.out, "Avatar: " + " | ".join(c["gloss"] for c in clips))
# # # # # #     print(f"\nXong: {timeline['n']} khung hình = {timeline['n']/args.fps:.1f} giây")
# # # # # #     print(f"Mở file này (bấm đúp): {out.resolve()}")
# # # # # #     if args.open:
# # # # # #         webbrowser.open(out.resolve().as_uri())
# # # # # #     return 0


# # # # # # if __name__ == "__main__":
# # # # # #     sys.exit(main())

























# # # # # #!/usr/bin/env python3
# # # # # # -*- coding: utf-8 -*-
# # # # # """
# # # # # sign_to_avatar.py
# # # # # =================
# # # # # Gloss list  ->  videos of the dataset  ->  3D landmarks (cached .npz)
# # # # #             ->  ONE continuous animation of the Xbot avatar (standalone .html).

# # # # # Example:
# # # # #     python sign_to_avatar.py --glosses "bạn" "đi học" "có không"
# # # # #     python sign_to_avatar.py --sentence "bạn | đi học | có không" --open
# # # # #     python sign_to_avatar.py --search "địa chỉ"

# # # # # The output .html is a single file: double-click it, no server / localhost needed.
# # # # # (It only needs Internet once per open, to load three.js from a CDN.)
# # # # # """
# # # # # import argparse
# # # # # import base64
# # # # # import csv
# # # # # import difflib
# # # # # import io
# # # # # import json
# # # # # import os
# # # # # import re
# # # # # import sys
# # # # # import unicodedata
# # # # # import webbrowser
# # # # # from pathlib import Path

# # # # # import numpy as np

# # # # # # =====================================================================
# # # # # # DEFAULTS (edit these once, then you never need to type the paths)
# # # # # # =====================================================================
# # # # # DEFAULT_VIDEOS = r"C:\Users\ADMIN\qh\vsl-vietnamese-sign-languages\versions\5\Dataset\Videos"
# # # # # DEFAULT_XBOT = os.path.join("frontend_dis", "models", "Xbot.glb")
# # # # # DEFAULT_CACHE = "landmark_cache"
# # # # # DEFAULT_OUT = os.path.join("output", "sentence.html")

# # # # # CACHE_VERSION = 1
# # # # # VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")

# # # # # BODY_NAMES = [
# # # # #     "Hips", "Spine1", "Spine2", "Neck", "Head",
# # # # #     "LeftArm", "LeftForeArm", "LeftHand",
# # # # #     "RightArm", "RightForeArm", "RightHand",
# # # # #     "LeftUpLeg", "LeftLeg", "LeftFoot",
# # # # #     "RightUpLeg", "RightLeg", "RightFoot",
# # # # # ]

# # # # # try:  # make Vietnamese text safe to print on any console
# # # # #     sys.stdout.reconfigure(errors="replace")
# # # # #     sys.stderr.reconfigure(errors="replace")
# # # # # except Exception:
# # # # #     pass


# # # # # # =====================================================================
# # # # # # 1. Text helpers
# # # # # # =====================================================================
# # # # # def norm(s):
# # # # #     """NFC + lower-case + collapsed spaces."""
# # # # #     return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s)).strip().lower())


# # # # # def strip_accents(s):
# # # # #     s = norm(s).replace("đ", "d")
# # # # #     s = unicodedata.normalize("NFD", s)
# # # # #     return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# # # # # def without_parens(s):
# # # # #     return norm(re.sub(r"\([^)]*\)", " ", str(s)))


# # # # # def natural_key(s):
# # # # #     return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


# # # # # VIDEO_RE = re.compile(r"^(?P<base>.*\d)(?P<reg>[NTBntb])?$")


# # # # # def parse_video(name):
# # # # #     """'D0001N.mp4' -> ('D0001', 'N');  'D0002.mp4' -> ('D0002', '')."""
# # # # #     stem = Path(str(name).strip()).stem
# # # # #     m = VIDEO_RE.match(stem)
# # # # #     if m:
# # # # #         return m.group("base"), (m.group("reg") or "").upper()
# # # # #     return stem, ""


# # # # # def label_keys(label):
# # # # #     """All the lookup keys under which a dataset label can be found."""
# # # # #     plain = without_parens(label)
# # # # #     parts = {norm(label), plain}
# # # # #     for p in re.split(r"\s*[;/,]\s*", plain):
# # # # #         if p.strip():
# # # # #             parts.add(norm(p))
# # # # #     keys = set()
# # # # #     for p in parts:
# # # # #         if p:
# # # # #             keys.add(p)
# # # # #             keys.add(strip_accents(p))
# # # # #     return keys


# # # # # # =====================================================================
# # # # # # 2. Reading the label file (csv / tsv / txt / xlsx / json)
# # # # # # =====================================================================
# # # # # def read_text_auto(path):
# # # # #     raw = Path(path).read_bytes()
# # # # #     if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:200]:
# # # # #         return raw.decode("utf-16", errors="replace")
# # # # #     try:
# # # # #         return raw.decode("utf-8-sig")
# # # # #     except UnicodeDecodeError:
# # # # #         return raw.decode("cp1258", errors="replace")


# # # # # def _pick_columns(header):
# # # # #     h = [norm(c) for c in header]
# # # # #     vi = next((i for i, c in enumerate(h) if c in ("video", "file", "filename", "name")), None)
# # # # #     li = next((i for i, c in enumerate(h) if c in ("label", "gloss", "nhan", "nhãn", "text")), None)
# # # # #     return vi, li


# # # # # def load_records(path):
# # # # #     """Return [(video_name, label), ...] from any supported file type."""
# # # # #     path = str(path)
# # # # #     ext = Path(path).suffix.lower()

# # # # #     if ext == ".json":
# # # # #         data = json.loads(read_text_auto(path))
# # # # #         recs = []
# # # # #         if isinstance(data, dict):
# # # # #             for gloss, vids in data.items():
# # # # #                 if isinstance(vids, (str, dict)):
# # # # #                     vids = [vids]
# # # # #                 for v in vids:
# # # # #                     recs.append((v["video"] if isinstance(v, dict) else v, gloss))
# # # # #         else:
# # # # #             for item in data:
# # # # #                 if isinstance(item, dict):
# # # # #                     low = {norm(k): v for k, v in item.items()}
# # # # #                     recs.append((low.get("video") or low.get("file"),
# # # # #                                  low.get("label") or low.get("gloss")))
# # # # #                 else:
# # # # #                     recs.append((item[0], item[1]))
# # # # #         return [(str(v), str(l)) for v, l in recs if v and l]

# # # # #     if ext in (".xlsx", ".xls", ".xlsm"):
# # # # #         import pandas as pd  # needs openpyxl for .xlsx
# # # # #         df = pd.read_excel(path, dtype=str).fillna("")
# # # # #         rows = [list(df.columns)] + df.values.tolist()
# # # # #     else:
# # # # #         text = read_text_auto(path)
# # # # #         first = text.splitlines()[0] if text else ""
# # # # #         delim = max(["\t", ",", ";"], key=first.count)
# # # # #         rows = list(csv.reader(io.StringIO(text), delimiter=delim))

# # # # #     rows = [r for r in rows if r and any(str(c).strip() for c in r)]
# # # # #     if not rows:
# # # # #         return []
# # # # #     vi, li = _pick_columns(rows[0])
# # # # #     start = 1
# # # # #     if vi is None or li is None:  # no header: first two columns
# # # # #         vi, li = 0, 1
# # # # #         start = 0 if Path(str(rows[0][0])).suffix.lower() in VIDEO_EXTS else 1
# # # # #     out = []
# # # # #     for r in rows[start:]:
# # # # #         if len(r) > max(vi, li) and str(r[vi]).strip() and str(r[li]).strip():
# # # # #             out.append((str(r[vi]).strip(), str(r[li]).strip()))
# # # # #     return out


# # # # # def find_labels_file(videos_dir):
# # # # #     vd = Path(videos_dir)
# # # # #     exts = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json")
# # # # #     cands = []
# # # # #     for d in (vd, vd.parent, vd.parent.parent):
# # # # #         if d.is_dir():
# # # # #             cands += [p for p in d.iterdir() if p.suffix.lower() in exts]
# # # # #     hits = [p for p in cands if "label" in p.name.lower()]
# # # # #     if len(hits) >= 1:
# # # # #         return str(sorted(hits, key=lambda p: len(str(p)))[0])
# # # # #     return None


# # # # # # =====================================================================
# # # # # # 3. Gloss index: label -> video
# # # # # # =====================================================================
# # # # # class GlossIndex:
# # # # #     def __init__(self, records, region_pref=("B", "T", "N")):
# # # # #         self.region_pref = [r.upper() for r in region_pref]
# # # # #         self.recs = []
# # # # #         self.by_key = {}
# # # # #         self.by_stem = {}
# # # # #         for video, label in records:
# # # # #             base, reg = parse_video(video)
# # # # #             rec = {"video": Path(video).name, "stem": Path(video).stem,
# # # # #                    "base": base, "region": reg, "label": label}
# # # # #             self.recs.append(rec)
# # # # #             self.by_stem[norm(rec["stem"])] = rec
# # # # #             for k in label_keys(label):
# # # # #                 self.by_key.setdefault(k, []).append(rec)

# # # # #     def lookup(self, text):
# # # # #         for v in (norm(text), without_parens(text),
# # # # #                   strip_accents(text), strip_accents(without_parens(text))):
# # # # #             if v and v in self.by_key:
# # # # #                 return self.by_key[v]
# # # # #         return []

# # # # #     def choose(self, recs):
# # # # #         """One video for a gloss: first sign (lowest id), preferred region."""
# # # # #         groups = {}
# # # # #         for r in recs:
# # # # #             groups.setdefault(r["base"], []).append(r)
# # # # #         bases = sorted(groups, key=natural_key)
# # # # #         group = groups[bases[0]]
# # # # #         group.sort(key=lambda r: (self.region_pref.index(r["region"])
# # # # #                                   if r["region"] in self.region_pref else 99,
# # # # #                                   natural_key(r["stem"])))
# # # # #         return group[0], len(bases) - 1

# # # # #     def resolve_one(self, gloss):
# # # # #         """Return (list of (gloss_text, rec, note), list of missing words)."""
# # # # #         g = str(gloss).strip()
# # # # #         if not g:
# # # # #             return [], []
# # # # #         # a video id typed directly, e.g. "D0001T"
# # # # #         rec = self.by_stem.get(norm(Path(g).stem))
# # # # #         if rec is not None and re.fullmatch(r"[dD]\d+[NTBntb]?(\.\w+)?", g):
# # # # #             return [(g, rec, "")], []

# # # # #         recs = self.lookup(g)
# # # # #         if recs:
# # # # #             rec, extra = self.choose(recs)
# # # # #             note = f"còn {extra} cách ký khác" if extra > 0 else ""
# # # # #             return [(g, rec, note)], []

# # # # #         # not a known gloss: split into the longest known pieces
# # # # #         words = norm(g).split()
# # # # #         found, missing, i = [], [], 0
# # # # #         while i < len(words):
# # # # #             for j in range(len(words), i, -1):
# # # # #                 phrase = " ".join(words[i:j])
# # # # #                 recs = self.lookup(phrase)
# # # # #                 if recs:
# # # # #                     rec, extra = self.choose(recs)
# # # # #                     found.append((phrase, rec, f'tách từ "{g}"'))
# # # # #                     i = j
# # # # #                     break
# # # # #             else:
# # # # #                 missing.append(words[i])
# # # # #                 i += 1
# # # # #         if not found:
# # # # #             return [], [g]
# # # # #         return found, missing

# # # # #     def suggest(self, text, n=4):
# # # # #         pool = {}
# # # # #         for k, recs in self.by_key.items():
# # # # #             if strip_accents(k) == k:
# # # # #                 pool[k] = recs[0]["label"]
# # # # #         close = difflib.get_close_matches(strip_accents(text), list(pool), n=n, cutoff=0.6)
# # # # #         return [pool[c] for c in close]

# # # # #     def search(self, text, limit=30):
# # # # #         t = strip_accents(text)
# # # # #         hits = [r for r in self.recs if t in strip_accents(r["label"])]
# # # # #         return sorted(hits, key=lambda r: natural_key(r["stem"]))[:limit]


# # # # # # =====================================================================
# # # # # # 4. Landmark extraction (MediaPipe) + cache
# # # # # # =====================================================================
# # # # # def assign_hands(hands, left_wrist, right_wrist):
# # # # #     """
# # # # #     hands: [(image_wrist_xy, world_21x3, label)], wrists in normalised image coords.
# # # # #     Decide which detected hand is the person's LEFT / RIGHT by comparing with the
# # # # #     body-pose wrists (more reliable than the handedness label for un-mirrored video).
# # # # #     """
# # # # #     res = {"L": None, "R": None}
# # # # #     if not hands:
# # # # #         return res

# # # # #     def d(a, b):
# # # # #         return float(np.hypot(a[0] - b[0], a[1] - b[1]))

# # # # #     if left_wrist is not None and right_wrist is not None:
# # # # #         if len(hands) == 1:
# # # # #             h = hands[0]
# # # # #             res["L" if d(h[0], left_wrist) <= d(h[0], right_wrist) else "R"] = h[1]
# # # # #         else:
# # # # #             h0, h1 = hands[0], hands[1]
# # # # #             a = d(h0[0], left_wrist) + d(h1[0], right_wrist)
# # # # #             b = d(h0[0], right_wrist) + d(h1[0], left_wrist)
# # # # #             if a <= b:
# # # # #                 res["L"], res["R"] = h0[1], h1[1]
# # # # #             else:
# # # # #                 res["L"], res["R"] = h1[1], h0[1]
# # # # #     else:  # no body wrists: use the label (MediaPipe assumes a mirrored image -> swap)
# # # # #         for h in hands:
# # # # #             res["R" if h[2] == "Left" else "L"] = h[1]
# # # # #     return res


# # # # # class MediaPipeDetector:
# # # # #     """Pose (33 world landmarks) + Hands (21 world landmarks each), one video at a time."""

# # # # #     def __init__(self, complexity=1):
# # # # #         import mediapipe as mp
# # # # #         self.pose = mp.solutions.pose.Pose(
# # # # #             static_image_mode=False, model_complexity=complexity, smooth_landmarks=True,
# # # # #             min_detection_confidence=0.5, min_tracking_confidence=0.5)
# # # # #         self.hands = mp.solutions.hands.Hands(
# # # # #             static_image_mode=False, max_num_hands=2, model_complexity=1,
# # # # #             min_detection_confidence=0.5, min_tracking_confidence=0.5)

# # # # #     def __enter__(self):
# # # # #         return self

# # # # #     def __exit__(self, *a):
# # # # #         self.pose.close()
# # # # #         self.hands.close()
# # # # #         return False

# # # # #     def process(self, rgb):
# # # # #         pr = self.pose.process(rgb)
# # # # #         hr = self.hands.process(rgb)
# # # # #         pose_world = left_w = right_w = None
# # # # #         if pr.pose_world_landmarks:
# # # # #             pose_world = np.array([[l.x, l.y, l.z] for l in pr.pose_world_landmarks.landmark],
# # # # #                                   dtype=np.float32)
# # # # #         if pr.pose_landmarks:
# # # # #             lm = pr.pose_landmarks.landmark
# # # # #             left_w, right_w = (lm[15].x, lm[15].y), (lm[16].x, lm[16].y)
# # # # #         hands = []
# # # # #         if hr.multi_hand_world_landmarks and hr.multi_hand_landmarks:
# # # # #             for wl, il, hd in zip(hr.multi_hand_world_landmarks,
# # # # #                                   hr.multi_hand_landmarks, hr.multi_handedness):
# # # # #                 world = np.array([[l.x, l.y, l.z] for l in wl.landmark], dtype=np.float32)
# # # # #                 hands.append(((il.landmark[0].x, il.landmark[0].y), world,
# # # # #                               hd.classification[0].label))
# # # # #         return {"pose": pose_world, "left_wrist": left_w, "right_wrist": right_w, "hands": hands}


# # # # # def extract_video(video_path, detector_factory, target_width=640):
# # # # #     """Run the detector on every frame. Returns dict of arrays (NaN = not detected)."""
# # # # #     import cv2
# # # # #     cap = cv2.VideoCapture(str(video_path))
# # # # #     if not cap.isOpened():
# # # # #         raise IOError(f"Không mở được video: {video_path}")
# # # # #     fps = cap.get(cv2.CAP_PROP_FPS)
# # # # #     if not fps or fps != fps or fps <= 1:
# # # # #         fps = 30.0
# # # # #     pose_l, lh_l, rh_l = [], [], []
# # # # #     nan_pose = np.full((33, 3), np.nan, np.float32)
# # # # #     nan_hand = np.full((21, 3), np.nan, np.float32)
# # # # #     with detector_factory() as det:
# # # # #         while True:
# # # # #             ok, frame = cap.read()
# # # # #             if not ok:
# # # # #                 break
# # # # #             h, w = frame.shape[:2]
# # # # #             if w != target_width and w > 0:
# # # # #                 frame = cv2.resize(frame, (target_width, int(h * target_width / w)))
# # # # #             rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
# # # # #             r = det.process(rgb)
# # # # #             pose_l.append(r["pose"] if r["pose"] is not None else nan_pose)
# # # # #             a = assign_hands(r["hands"], r["left_wrist"], r["right_wrist"])
# # # # #             lh_l.append(a["L"] if a["L"] is not None else nan_hand)
# # # # #             rh_l.append(a["R"] if a["R"] is not None else nan_hand)
# # # # #     cap.release()
# # # # #     if not pose_l:
# # # # #         raise IOError(f"Video rỗng: {video_path}")
# # # # #     return {"pose": np.stack(pose_l).astype(np.float32),
# # # # #             "lhand": np.stack(lh_l).astype(np.float32),
# # # # #             "rhand": np.stack(rh_l).astype(np.float32),
# # # # #             "fps": float(fps)}


# # # # # def get_clip_data(video_path, cache_dir, detector_factory):
# # # # #     cache_path = Path(cache_dir) / (Path(video_path).stem + ".npz")
# # # # #     if cache_path.exists():
# # # # #         try:
# # # # #             d = np.load(cache_path)
# # # # #             if int(d["version"]) == CACHE_VERSION:
# # # # #                 data = {k: d[k] for k in ("pose", "lhand", "rhand")}
# # # # #                 data["fps"] = float(d["fps"])
# # # # #                 return data, True
# # # # #         except Exception:
# # # # #             pass
# # # # #     data = extract_video(video_path, detector_factory)
# # # # #     cache_path.parent.mkdir(parents=True, exist_ok=True)
# # # # #     np.savez_compressed(cache_path, pose=data["pose"], lhand=data["lhand"],
# # # # #                         rhand=data["rhand"], fps=data["fps"], version=CACHE_VERSION)
# # # # #     return data, False


# # # # # # =====================================================================
# # # # # # 5. Clean-up: resample, fill gaps, smooth, trim, join
# # # # # # =====================================================================
# # # # # def resample(arr, src_fps, dst_fps):
# # # # #     T = len(arr)
# # # # #     if T < 2 or abs(src_fps - dst_fps) < 1e-3:
# # # # #         return arr
# # # # #     new_T = max(2, int(round((T - 1) * dst_fps / src_fps)) + 1)
# # # # #     t = np.linspace(0, T - 1, new_T)
# # # # #     i0 = np.floor(t).astype(int)
# # # # #     i1 = np.minimum(i0 + 1, T - 1)
# # # # #     a = (t - i0).reshape((-1,) + (1,) * (arr.ndim - 1))
# # # # #     return arr[i0] * (1 - a) + arr[i1] * a   # NaN stays NaN if either neighbour is missing


# # # # # def fill_gaps(arr, max_gap, hold_edges):
# # # # #     T = len(arr)
# # # # #     flat = arr.reshape(T, -1).astype(np.float64)
# # # # #     valid = ~np.isnan(flat).any(axis=1)
# # # # #     idx = np.where(valid)[0]
# # # # #     if len(idx) == 0:
# # # # #         return arr
# # # # #     out = flat.copy()
# # # # #     for a, b in zip(idx[:-1], idx[1:]):
# # # # #         gap = b - a - 1
# # # # #         if 0 < gap <= max_gap:
# # # # #             for k in range(1, gap + 1):
# # # # #                 w = k / (gap + 1)
# # # # #                 out[a + k] = flat[a] * (1 - w) + flat[b] * w
# # # # #     if hold_edges:
# # # # #         out[:idx[0]] = flat[idx[0]]
# # # # #         out[idx[-1] + 1:] = flat[idx[-1]]
# # # # #     return out.reshape(arr.shape).astype(np.float32)


# # # # # def hold_last_valid(arr):
# # # # #     """Replace remaining NaN frames by the previous (or next) valid frame."""
# # # # #     T = len(arr)
# # # # #     flat = arr.reshape(T, -1).copy()
# # # # #     valid = ~np.isnan(flat).any(axis=1)
# # # # #     if not valid.any():
# # # # #         return arr
# # # # #     last = None
# # # # #     for i in range(T):
# # # # #         if valid[i]:
# # # # #             last = flat[i].copy()
# # # # #         elif last is not None:
# # # # #             flat[i] = last
# # # # #     first = np.where(valid)[0][0]
# # # # #     flat[:first] = flat[first]
# # # # #     return flat.reshape(arr.shape)


# # # # # def smooth_nan(arr, sigma):
# # # # #     """Gaussian smoothing along time; invalid (NaN) frames stay invalid."""
# # # # #     T = len(arr)
# # # # #     if sigma <= 0 or T < 2:
# # # # #         return arr
# # # # #     flat = arr.reshape(T, -1).astype(np.float64)
# # # # #     valid = ~np.isnan(flat).any(axis=1)
# # # # #     if not valid.any():
# # # # #         return arr
# # # # #     i = np.arange(T)
# # # # #     W = np.exp(-0.5 * ((i[:, None] - i[None, :]) / sigma) ** 2) * valid[None, :]
# # # # #     num = W @ np.where(valid[:, None], flat, 0.0)
# # # # #     den = np.maximum(W.sum(axis=1, keepdims=True), 1e-9)
# # # # #     out = num / den
# # # # #     out[~valid] = np.nan
# # # # #     return out.reshape(arr.shape).astype(np.float32)


# # # # # def body_keypoints(pose):
# # # # #     """(T,33,3) MediaPipe pose -> (T,17,3) avatar keypoints (order = BODY_NAMES)."""
# # # # #     hips = (pose[:, 23] + pose[:, 24]) / 2
# # # # #     neck = (pose[:, 11] + pose[:, 12]) / 2
# # # # #     head = (pose[:, 7] + pose[:, 8]) / 2
# # # # #     spine1 = hips + (neck - hips) / 3
# # # # #     spine2 = hips + (neck - hips) * 2 / 3
# # # # #     kp = [hips, spine1, spine2, neck, head,
# # # # #           pose[:, 11], pose[:, 13], pose[:, 15],
# # # # #           pose[:, 12], pose[:, 14], pose[:, 16],
# # # # #           pose[:, 23], pose[:, 25], pose[:, 27],
# # # # #           pose[:, 24], pose[:, 26], pose[:, 28]]
# # # # #     return np.stack(kp, axis=1).astype(np.float32)


# # # # # def active_range(pose, threshold, pad):
# # # # #     """Frames where at least one wrist is clearly above the hips (= signing)."""
# # # # #     T = len(pose)
# # # # #     hips_y = (pose[:, 23, 1] + pose[:, 24, 1]) / 2
# # # # #     wrist_y = np.minimum(pose[:, 15, 1], pose[:, 16, 1])   # MediaPipe y points DOWN
# # # # #     idx = np.where(wrist_y < hips_y - threshold)[0]
# # # # #     if len(idx) == 0:
# # # # #         return 0, T
# # # # #     return max(0, int(idx[0]) - pad), min(T, int(idx[-1]) + pad + 1)


# # # # # def process_clip(raw, fps, args):
# # # # #     pose = resample(raw["pose"], raw["fps"], fps)
# # # # #     lh = resample(raw["lhand"], raw["fps"], fps)
# # # # #     rh = resample(raw["rhand"], raw["fps"], fps)

# # # # #     ok_ratio = float((~np.isnan(pose.reshape(len(pose), -1)).any(axis=1)).mean())
# # # # #     if ok_ratio < 0.3:
# # # # #         return None, ok_ratio

# # # # #     pose = fill_gaps(pose, max_gap=int(fps * 0.6), hold_edges=True)
# # # # #     pose = hold_last_valid(pose)
# # # # #     pose = smooth_nan(pose, args.smooth_body)
# # # # #     lh = smooth_nan(fill_gaps(lh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)
# # # # #     rh = smooth_nan(fill_gaps(rh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)

# # # # #     if not args.no_trim:
# # # # #         a, b = active_range(pose, args.rest_threshold, int(round(fps * 0.12)))
# # # # #         pose, lh, rh = pose[a:b], lh[a:b], rh[a:b]
# # # # #     return {"body": body_keypoints(pose), "lh": lh, "rh": rh}, ok_ratio


# # # # # def _ease(w):
# # # # #     return 0.5 - 0.5 * np.cos(np.pi * w)


# # # # # def assemble(clips, fps, transition_s, hold_s):
# # # # #     """clips: [{gloss, video, body, lh, rh}] -> one timeline."""
# # # # #     ntr = max(0, int(round(transition_s * fps)))
# # # # #     hold = max(0, int(round(hold_s * fps)))
# # # # #     B, LH, RH, segs = [], [], [], []
# # # # #     cursor = 0

# # # # #     def add(body, lh, rh):
# # # # #         nonlocal cursor
# # # # #         B.append(body)
# # # # #         LH.append(lh)
# # # # #         RH.append(rh)
# # # # #         cursor += len(body)

# # # # #     for i, c in enumerate(clips):
# # # # #         seg_start = cursor
# # # # #         if i == 0 and hold:
# # # # #             add(np.repeat(c["body"][:1], hold, 0), np.repeat(c["lh"][:1], hold, 0),
# # # # #                 np.repeat(c["rh"][:1], hold, 0))
# # # # #         if i > 0 and ntr:
# # # # #             p = clips[i - 1]
# # # # #             w = _ease(np.arange(1, ntr + 1) / (ntr + 1)).reshape(-1, 1, 1)
# # # # #             body = p["body"][-1][None] * (1 - w) + c["body"][0][None] * w
# # # # #             lh = p["lh"][-1][None] * (1 - w) + c["lh"][0][None] * w     # NaN if either is missing
# # # # #             rh = p["rh"][-1][None] * (1 - w) + c["rh"][0][None] * w
# # # # #             add(body, lh, rh)
# # # # #         add(c["body"], c["lh"], c["rh"])
# # # # #         if i == len(clips) - 1 and hold:
# # # # #             add(np.repeat(c["body"][-1:], hold, 0), np.repeat(c["lh"][-1:], hold, 0),
# # # # #                 np.repeat(c["rh"][-1:], hold, 0))
# # # # #         segs.append({"s": seg_start, "e": cursor, "gloss": c["gloss"], "video": c["video"]})

# # # # #     body = np.concatenate(B).astype(np.float64)
# # # # #     lh = np.concatenate(LH).astype(np.float64)
# # # # #     rh = np.concatenate(RH).astype(np.float64)
# # # # #     lv = (~np.isnan(lh.reshape(len(lh), -1)).any(axis=1)).astype(int)
# # # # #     rv = (~np.isnan(rh.reshape(len(rh), -1)).any(axis=1)).astype(int)
# # # # #     lh = np.nan_to_num(lh, nan=0.0)
# # # # #     rh = np.nan_to_num(rh, nan=0.0)
# # # # #     return {"fps": fps, "n": int(len(body)),
# # # # #             "body": np.round(body, 4).ravel().tolist(),
# # # # #             "lh": np.round(lh, 4).ravel().tolist(),
# # # # #             "rh": np.round(rh, 4).ravel().tolist(),
# # # # #             "lv": lv.tolist(), "rv": rv.tolist(), "segments": segs}


# # # # # # =====================================================================
# # # # # # 6. The standalone player (HTML + JavaScript, three.js r128 from a CDN)
# # # # # # =====================================================================
# # # # # HTML_TEMPLATE = r'''<!DOCTYPE html>
# # # # # <html lang="vi">
# # # # # <head>
# # # # # <meta charset="utf-8">
# # # # # <meta name="viewport" content="width=device-width, initial-scale=1">
# # # # # <title>__TITLE__</title>
# # # # # <style>
# # # # #   :root { color-scheme: dark; }
# # # # #   html, body { margin: 0; height: 100%; overflow: hidden; background: #0b1220; color: #e5e7eb;
# # # # #                font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
# # # # #   #stage { position: fixed; inset: 0; }
# # # # #   #stage canvas { display: block; }
# # # # #   #caption { position: fixed; top: 18px; left: 0; right: 0; text-align: center; pointer-events: none;
# # # # #              font-size: 38px; font-weight: 700; text-shadow: 0 2px 12px #000; min-height: 46px; }
# # # # #   #panel { position: fixed; left: 12px; right: 12px; bottom: 12px; padding: 10px 14px;
# # # # #            background: rgba(15, 23, 42, .90); border: 1px solid #334155; border-radius: 12px; }
# # # # #   .row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 5px 0; }
# # # # #   button, select { background: #1e293b; color: #e5e7eb; border: 1px solid #475569; border-radius: 8px;
# # # # #                    padding: 6px 12px; font-size: 14px; cursor: pointer; }
# # # # #   button:hover { background: #334155; }
# # # # #   button.rec { border-color: #ef4444; }
# # # # #   input[type=range] { flex: 1; min-width: 160px; }
# # # # #   label { font-size: 13px; color: #cbd5e1; display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
# # # # #   .chip { padding: 3px 10px; border-radius: 999px; border: 1px solid #475569; font-size: 13px; cursor: pointer; }
# # # # #   .chip.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
# # # # #   #status { font-size: 12px; color: #94a3b8; }
# # # # #   #status.err { color: #fca5a5; font-size: 14px; }
# # # # # </style>
# # # # # </head>
# # # # # <body>
# # # # # <div id="stage"></div>
# # # # # <div id="caption"></div>
# # # # # <div id="panel">
# # # # #   <div class="row">
# # # # #     <button id="play">Tạm dừng</button>
# # # # #     <button id="restart">Phát lại</button>
# # # # #     <input type="range" id="seek" min="0" max="1" step="1" value="0">
# # # # #     <span id="time">0.0 / 0.0 s</span>
# # # # #     <select id="speed" title="Tốc độ">
# # # # #       <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
# # # # #       <option value="1" selected>1x</option><option value="1.5">1.5x</option>
# # # # #     </select>
# # # # #     <select id="view" title="Khung nhìn">
# # # # #       <option value="upper" selected>Thân trên</option>
# # # # #       <option value="hands">Cận tay</option>
# # # # #       <option value="full">Toàn thân</option>
# # # # #     </select>
# # # # #   </div>
# # # # #   <div class="row" id="chips"></div>
# # # # #   <div class="row">
# # # # #     <label><input type="checkbox" id="o_loop" checked> Lặp lại</label>
# # # # #     <label><input type="checkbox" id="o_fingers" checked> Ngón tay</label>
# # # # #     <label><input type="checkbox" id="o_legs"> Chân</label>
# # # # #     <label><input type="checkbox" id="o_mirror"> Lật trái/phải</label>
# # # # #     <label><input type="checkbox" id="o_flipz"> Đảo chiều sâu</label>
# # # # #     <label><input type="checkbox" id="o_swap"> Đổi tay trái/phải</label>
# # # # #     <button id="rec" class="rec">Ghi video (.webm)</button>
# # # # #   </div>
# # # # #   <div id="status">Đang tải mô hình...</div>
# # # # # </div>

# # # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
# # # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
# # # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
# # # # # <script>
# # # # # "use strict";
# # # # # const DATA = __DATA_JSON__;
# # # # # const GLB_B64 = "__GLB_B64__";
# # # # # const $ = (id) => document.getElementById(id);

# # # # # function fail(msg) { const s = $("status"); s.textContent = msg; s.className = "err"; }

# # # # # const N = DATA.n, FPS = DATA.fps;
# # # # # const body = DATA.body, lh = DATA.lh, rh = DATA.rh, lv = DATA.lv, rv = DATA.rv;
# # # # # const opts = { mirror: false, flipZ: false, swapHands: false, legs: false,
# # # # #                fingers: true, loop: true, speed: 1 };

# # # # # // ==== RETARGET START ====
# # # # # // Turns MediaPipe 3D points into bone rotations of the Mixamo-style Xbot skeleton.
# # # # # const BODY = ["Hips","Spine1","Spine2","Neck","Head","LeftArm","LeftForeArm","LeftHand",
# # # # #   "RightArm","RightForeArm","RightHand","LeftUpLeg","LeftLeg","LeftFoot","RightUpLeg","RightLeg","RightFoot"];
# # # # # const FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"];
# # # # # // [bone, bone it must point to] - parents first
# # # # # const AIM_PAIRS = [
# # # # #   ["Hips","Spine1"], ["Spine1","Spine2"], ["Spine2","Neck"], ["Neck","Head"],
# # # # #   ["LeftArm","LeftForeArm"], ["LeftForeArm","LeftHand"],
# # # # #   ["RightArm","RightForeArm"], ["RightForeArm","RightHand"],
# # # # #   ["LeftUpLeg","LeftLeg"], ["LeftLeg","LeftFoot"],
# # # # #   ["RightUpLeg","RightLeg"], ["RightLeg","RightFoot"],
# # # # # ];
# # # # # const LEG_BONES = ["LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"];

# # # # # const bones = {};      // clean name -> bone
# # # # # const restQ = {};      // clean name -> rest-pose rotation
# # # # # let rootObj = null;
# # # # # const handState = { Left: { w: 0, last: null }, Right: { w: 0, last: null } };

# # # # # function cleanName(n) { return n.replace(/^mixamorig:?/, ""); }

# # # # # function setupModel(model) {
# # # # #   rootObj = model;
# # # # #   model.traverse((o) => {
# # # # #     if (o.isBone) { const c = cleanName(o.name); bones[c] = o; restQ[c] = o.quaternion.clone(); }
# # # # #   });
# # # # #   let fingerBases = 0;
# # # # #   for (const s of ["Left", "Right"]) for (const f of FINGERS) if (bones[s + "Hand" + f + "1"]) fingerBases++;
# # # # #   return { bones: Object.keys(bones).length, fingerBases };
# # # # # }

# # # # # function resetPose() {
# # # # #   for (const k in bones) bones[k].quaternion.copy(restQ[k]);
# # # # #   if (rootObj) rootObj.updateMatrixWorld(true);
# # # # # }

# # # # # // Rotate a bone by a rotation given in WORLD space.
# # # # # function applyWorldRotation(bone, qWorld) {
# # # # #   if (!bone || !bone.parent) return;
# # # # #   bone.parent.updateWorldMatrix(true, false);
# # # # #   const pq = bone.parent.getWorldQuaternion(new THREE.Quaternion());
# # # # #   const adj = pq.clone().invert().multiply(qWorld).multiply(pq);
# # # # #   bone.quaternion.premultiply(adj);
# # # # #   bone.updateMatrixWorld(true);
# # # # # }

# # # # # // Make the direction  bone -> child  point along `dir` (world space).
# # # # # function aimBone(bone, child, dir) {
# # # # #   if (!bone || !child || dir.lengthSq() < 1e-10) return;
# # # # #   bone.updateWorldMatrix(true, true);
# # # # #   const p = bone.getWorldPosition(new THREE.Vector3());
# # # # #   const c = child.getWorldPosition(new THREE.Vector3());
# # # # #   const cur = c.sub(p);
# # # # #   if (cur.lengthSq() < 1e-12) return;
# # # # #   cur.normalize();
# # # # #   applyWorldRotation(bone, new THREE.Quaternion().setFromUnitVectors(cur, dir.clone().normalize()));
# # # # # }

# # # # # // Twist a bone around `axisDir` so that curSide lines up with tgtSide (palm orientation).
# # # # # function rollBoneAround(bone, axisDir, curSide, tgtSide) {
# # # # #   const a = axisDir.clone().normalize();
# # # # #   const c = curSide.clone().sub(a.clone().multiplyScalar(curSide.dot(a)));
# # # # #   const t = tgtSide.clone().sub(a.clone().multiplyScalar(tgtSide.dot(a)));
# # # # #   if (c.lengthSq() < 1e-10 || t.lengthSq() < 1e-10) return;
# # # # #   c.normalize(); t.normalize();
# # # # #   let angle = Math.acos(THREE.MathUtils.clamp(c.dot(t), -1, 1));
# # # # #   if (new THREE.Vector3().crossVectors(c, t).dot(a) < 0) angle = -angle;
# # # # #   applyWorldRotation(bone, new THREE.Quaternion().setFromAxisAngle(a, angle));
# # # # # }

# # # # # function blendToRest(name, w) {
# # # # #   if (w >= 0.999 || !bones[name]) return;
# # # # #   const q = bones[name].quaternion.clone();
# # # # #   bones[name].quaternion.copy(restQ[name]).slerp(q, w);
# # # # #   bones[name].updateMatrixWorld(true);
# # # # # }

# # # # # function applyBody(P) {
# # # # #   for (const [a, b] of AIM_PAIRS) {
# # # # #     if (!opts.legs && LEG_BONES.includes(a)) continue;
# # # # #     if (!bones[a] || !bones[b] || !P[a] || !P[b]) continue;
# # # # #     aimBone(bones[a], bones[b], P[b].clone().sub(P[a]));
# # # # #   }
# # # # # }

# # # # # // H: {Wrist, Thumb1..Pinky4} -> Vector3 ; w: 0..1 blend weight (0 = rest pose)
# # # # # function applyHand(side, H, w) {
# # # # #   if (!H || w <= 0.001) return;
# # # # #   const wrist = bones[side + "Hand"], mid1 = bones[side + "HandMiddle1"];
# # # # #   const idx1 = bones[side + "HandIndex1"], pky1 = bones[side + "HandPinky1"];
# # # # #   if (wrist && mid1 && H.Wrist && H.Middle1) {
# # # # #     const axis = H.Middle1.clone().sub(H.Wrist);
# # # # #     aimBone(wrist, mid1, axis);
# # # # #     if (idx1 && pky1 && H.Index1 && H.Pinky1) {
# # # # #       const a = idx1.getWorldPosition(new THREE.Vector3());
# # # # #       const b = pky1.getWorldPosition(new THREE.Vector3());
# # # # #       rollBoneAround(wrist, axis, a.sub(b), H.Index1.clone().sub(H.Pinky1));
# # # # #     }
# # # # #     blendToRest(side + "Hand", w);
# # # # #   }
# # # # #   for (const f of FINGERS) {
# # # # #     for (let n = 1; n <= 3; n++) {
# # # # #       const name = side + "Hand" + f + n;
# # # # #       const bone = bones[name], child = bones[side + "Hand" + f + (n + 1)];
# # # # #       const p0 = H[f + n], p1 = H[f + (n + 1)];
# # # # #       if (bone && child && p0 && p1) {
# # # # #         aimBone(bone, child, p1.clone().sub(p0));
# # # # #         blendToRest(name, w);
# # # # #       }
# # # # #     }
# # # # #   }
# # # # # }

# # # # # // MediaPipe camera frame (x right, y down, z away) -> model frame (x right, y up, z towards viewer)
# # # # # function toModel(x, y, z) {
# # # # #   return new THREE.Vector3((opts.mirror ? -1 : 1) * x, -y, -(opts.flipZ ? -1 : 1) * z);
# # # # # }

# # # # # function sampleFrame(f) {
# # # # #   const f0 = Math.max(0, Math.min(N - 1, Math.floor(f)));
# # # # #   const f1 = Math.min(f0 + 1, N - 1);
# # # # #   const a = Math.max(0, Math.min(1, f - f0));
# # # # #   const lerp = (u, v) => u + (v - u) * a;

# # # # #   const P = {};
# # # # #   for (let j = 0; j < BODY.length; j++) {
# # # # #     const o0 = (f0 * BODY.length + j) * 3, o1 = (f1 * BODY.length + j) * 3;
# # # # #     P[BODY[j]] = toModel(lerp(body[o0], body[o1]), lerp(body[o0 + 1], body[o1 + 1]), lerp(body[o0 + 2], body[o1 + 2]));
# # # # #   }

# # # # #   const hands = { Left: null, Right: null };
# # # # #   const srcs = opts.swapHands
# # # # #     ? [["Left", rh, rv], ["Right", lh, lv]]
# # # # #     : [["Left", lh, lv], ["Right", rh, rv]];
# # # # #   for (const [side, arr, val] of srcs) {
# # # # #     if (!(val[f0] && val[f1])) continue;
# # # # #     const pt = (k) => {
# # # # #       const o0 = (f0 * 21 + k) * 3, o1 = (f1 * 21 + k) * 3;
# # # # #       return toModel(lerp(arr[o0], arr[o1]), lerp(arr[o0 + 1], arr[o1 + 1]), lerp(arr[o0 + 2], arr[o1 + 2]));
# # # # #     };
# # # # #     const H = { Wrist: pt(0) };
# # # # #     FINGERS.forEach((fn, fi) => { for (let n = 1; n <= 4; n++) H[fn + n] = pt(1 + 4 * fi + (n - 1)); });
# # # # #     hands[side] = H;
# # # # #   }
# # # # #   return { P, hands };
# # # # # }

# # # # # // Pose the whole avatar for (fractional) frame f. dt = seconds since last call.
# # # # # function applyFrame(f, dt) {
# # # # #   if (!rootObj) return;
# # # # #   const { P, hands } = sampleFrame(f);
# # # # #   resetPose();                      // always start from the rest pose: no drift, no accumulated twist
# # # # #   applyBody(P);
# # # # #   for (const side of ["Left", "Right"]) {
# # # # #     const st = handState[side], H = hands[side];
# # # # #     if (H && opts.fingers) { st.last = H; st.w = Math.min(1, st.w + dt / 0.12); }
# # # # #     else { st.w = Math.max(0, st.w - dt / 0.12); }
# # # # #     if (st.last && st.w > 0) applyHand(side, H && opts.fingers ? H : st.last, st.w);
# # # # #   }
# # # # #   rootObj.updateMatrixWorld(true);
# # # # # }
# # # # # // ---- size and camera: measured from the SKELETON (the mesh bounding box is unreliable for skinned models) ----
# # # # # function computeFit() {
# # # # #   rootObj.updateMatrixWorld(true);
# # # # #   let minY = Infinity, maxY = -Infinity;
# # # # #   for (const k in bones) {
# # # # #     const y = bones[k].getWorldPosition(new THREE.Vector3()).y;
# # # # #     if (y < minY) minY = y;
# # # # #     if (y > maxY) maxY = y;
# # # # #   }
# # # # #   const hips = bones.Hips ? bones.Hips.getWorldPosition(new THREE.Vector3()) : null;
# # # # #   const head = bones.Head ? bones.Head.getWorldPosition(new THREE.Vector3()) : null;
# # # # #   return { hips, footY: minY, topY: maxY,
# # # # #            hipsY: hips ? hips.y : (minY + maxY) / 2, headY: head ? head.y : maxY };
# # # # # }

# # # # # // view: "upper" | "hands" | "full".  H = window height (px), panelH / captionH = UI that covers the scene (px)
# # # # # function computeView(fit, view, aspect, fovDeg, H, panelH, captionH) {
# # # # #   const bodyH = fit.headY - fit.hipsY;
# # # # #   let lo, hi, halfW;
# # # # #   if (view === "full") { lo = fit.footY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
# # # # #   else if (view === "hands") { lo = fit.hipsY + 0.45 * bodyH; hi = fit.headY + 0.25; halfW = 0.60; }
# # # # #   else { lo = fit.hipsY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
# # # # #   const avail = Math.max(0.3, (H - panelH - captionH) / H);      // share of the screen that is free
# # # # #   const t = Math.tan(fovDeg * Math.PI / 360);
# # # # #   const dV = ((hi - lo) / avail) / (2 * t);
# # # # #   const dH = halfW / (t * aspect);
# # # # #   const d = Math.max(dV, dH) * 1.05;
# # # # #   const visH = 2 * d * t;
# # # # #   const centerY = (lo + hi) / 2;
# # # # #   const ty = centerY + ((captionH - panelH) / 2) * (visH / H);   // put the avatar in the free part of the screen
# # # # #   return { target: [0, ty, 0], position: [0, ty, d] };
# # # # # }

# # # # # const RETARGET = { bones, restQ, setupModel, applyFrame, sampleFrame, handState, opts, resetPose, computeFit, computeView };
# # # # # // ==== RETARGET END ====

# # # # # (function main() {
# # # # #   if (typeof THREE === "undefined" || !THREE.GLTFLoader || !THREE.OrbitControls) {
# # # # #     fail("Không tải được three.js từ CDN. Hãy kiểm tra kết nối Internet rồi mở lại trang.");
# # # # #     return;
# # # # #   }

# # # # #   // ---------- scene ----------
# # # # #   const stage = $("stage");
# # # # #   const renderer = new THREE.WebGLRenderer({ antialias: true });
# # # # #   renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
# # # # #   renderer.outputEncoding = THREE.sRGBEncoding;
# # # # #   renderer.shadowMap.enabled = true;
# # # # #   stage.appendChild(renderer.domElement);

# # # # #   const scene = new THREE.Scene();
# # # # #   scene.background = new THREE.Color(0x0b1220);
# # # # #   const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
# # # # #   camera.position.set(0, 1.0, 2.6);
# # # # #   const controls = new THREE.OrbitControls(camera, renderer.domElement);
# # # # #   controls.target.set(0, 0.9, 0);
# # # # #   controls.minDistance = 0.5;
# # # # #   controls.maxDistance = 10;
# # # # #   controls.update();
# # # # #   let fit = null;                      // skeleton measurements, filled in when the model is loaded

# # # # #   function applyView() {
# # # # #     if (!fit) return;
# # # # #     const v = computeView(fit, $("view").value, camera.aspect, camera.fov,
# # # # #                           window.innerHeight, $("panel").offsetHeight + 12, 70);
# # # # #     camera.position.set(v.position[0], v.position[1], v.position[2]);
# # # # #     controls.target.set(v.target[0], v.target[1], v.target[2]);
# # # # #     controls.update();
# # # # #   }

# # # # #   scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 0.9));
# # # # #   const sun = new THREE.DirectionalLight(0xffffff, 0.8);
# # # # #   sun.position.set(2, 4, 3);
# # # # #   sun.castShadow = true;
# # # # #   scene.add(sun);
# # # # #   const ground = new THREE.Mesh(new THREE.CircleGeometry(3, 48),
# # # # #     new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 1 }));
# # # # #   ground.rotation.x = -Math.PI / 2;
# # # # #   ground.receiveShadow = true;
# # # # #   scene.add(ground);
# # # # #   scene.add(new THREE.GridHelper(6, 24, 0x334155, 0x1f2937));

# # # # #   function resize() {
# # # # #     const w = window.innerWidth, h = window.innerHeight;
# # # # #     renderer.setSize(w, h);
# # # # #     camera.aspect = w / h;
# # # # #     camera.updateProjectionMatrix();
# # # # #     applyView();
# # # # #   }
# # # # #   window.addEventListener("resize", resize);
# # # # #   resize();

# # # # #   // ---------- UI ----------
# # # # #   const seek = $("seek");
# # # # #   seek.max = Math.max(1, N - 1);
# # # # #   const chips = $("chips");
# # # # #   const segEls = DATA.segments.map((s, i) => {
# # # # #     const el = document.createElement("span");
# # # # #     el.className = "chip";
# # # # #     el.textContent = s.gloss;
# # # # #     el.title = s.video;
# # # # #     el.onclick = () => { tFrame = s.s; };
# # # # #     chips.appendChild(el);
# # # # #     return el;
# # # # #   });

# # # # #   let playing = true, tFrame = 0, recording = null;
# # # # #   const setPlayLabel = () => { $("play").textContent = playing ? "Tạm dừng" : "Phát"; };
# # # # #   $("play").onclick = () => { playing = !playing; if (playing && tFrame >= N - 1) tFrame = 0; setPlayLabel(); };
# # # # #   $("restart").onclick = () => { tFrame = 0; playing = true; setPlayLabel(); };
# # # # #   seek.oninput = () => { tFrame = +seek.value; };
# # # # #   $("speed").onchange = (e) => { opts.speed = +e.target.value; };
# # # # #   $("view").onchange = applyView;
# # # # #   for (const [id, key] of [["o_loop","loop"],["o_fingers","fingers"],["o_legs","legs"],
# # # # #                            ["o_mirror","mirror"],["o_flipz","flipZ"],["o_swap","swapHands"]]) {
# # # # #     $(id).onchange = (e) => { opts[key] = e.target.checked; };
# # # # #   }
# # # # #   window.addEventListener("keydown", (e) => { if (e.code === "Space") { e.preventDefault(); $("play").click(); } });

# # # # #   $("rec").onclick = () => {
# # # # #     if (!window.MediaRecorder) { alert("Trình duyệt không hỗ trợ ghi video. Hãy dùng Chrome hoặc Edge."); return; }
# # # # #     if (recording) return;
# # # # #     const stream = renderer.domElement.captureStream(30);
# # # # #     const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]
# # # # #       .find((m) => MediaRecorder.isTypeSupported(m));
# # # # #     const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 6000000 });
# # # # #     const chunks = [];
# # # # #     rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
# # # # #     rec.onstop = () => {
# # # # #       const a = document.createElement("a");
# # # # #       a.href = URL.createObjectURL(new Blob(chunks, { type: "video/webm" }));
# # # # #       a.download = "sign_avatar.webm";
# # # # #       a.click();
# # # # #       recording = null;
# # # # #       $("rec").textContent = "Ghi video (.webm)";
# # # # #     };
# # # # #     recording = { rec, prevLoop: opts.loop };
# # # # #     opts.loop = false;
# # # # #     tFrame = 0; playing = true; setPlayLabel();
# # # # #     rec.start();
# # # # #     $("rec").textContent = "Đang ghi...";
# # # # #   };

# # # # #   // ---------- model ----------
# # # # #   let loaded = false;
# # # # #   try {
# # # # #     const bin = atob(GLB_B64);
# # # # #     const buf = new Uint8Array(bin.length);
# # # # #     for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
# # # # #     new THREE.GLTFLoader().parse(buf.buffer, "", (gltf) => {
# # # # #       const model = gltf.scene;
# # # # #       model.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
# # # # #       scene.add(model);
# # # # #       const info = setupModel(model);
# # # # #       // size the avatar from its skeleton: feet -> head bone = 1.55 m (about a 1.75 m person)
# # # # #       let ft = computeFit();
# # # # #       model.scale.multiplyScalar(1.55 / Math.max(1e-6, ft.headY - ft.footY));
# # # # #       ft = computeFit();
# # # # #       model.position.y -= ft.footY;
# # # # #       if (ft.hips) { model.position.x -= ft.hips.x; model.position.z -= ft.hips.z; }
# # # # #       fit = computeFit();
# # # # #       applyView();
# # # # #       loaded = true;
# # # # #       $("status").textContent = "Xương: " + info.bones + " | xương ngón tay: " + info.fingerBases +
# # # # #         "/10 | " + N + " khung hình, " + FPS + " fps | các từ: " + DATA.segments.map((s) => s.gloss).join(" → ");
# # # # #       if (info.fingerBases < 10) $("status").textContent += "  (mô hình thiếu xương ngón tay: ngón sẽ không cử động)";
# # # # #     }, (err) => { fail("Không đọc được mô hình Xbot: " + (err && err.message ? err.message : err)); });
# # # # #   } catch (e) { fail("Lỗi nạp mô hình: " + e); }

# # # # #   // ---------- loop ----------
# # # # #   let last = performance.now();
# # # # #   function tick(now) {
# # # # #     const dt = Math.min(0.1, (now - last) / 1000);
# # # # #     last = now;
# # # # #     if (playing) {
# # # # #       tFrame += dt * FPS * opts.speed;
# # # # #       if (tFrame >= N - 1) {
# # # # #         if (recording) {
# # # # #           tFrame = N - 1; playing = false; setPlayLabel();
# # # # #           opts.loop = recording.prevLoop;
# # # # #           const r = recording.rec; setTimeout(() => r.state !== "inactive" && r.stop(), 250);
# # # # #         } else if (opts.loop) tFrame = 0;
# # # # #         else { tFrame = N - 1; playing = false; setPlayLabel(); }
# # # # #       }
# # # # #     }
# # # # #     if (loaded) applyFrame(tFrame, dt);
# # # # #     const fi = Math.floor(tFrame);
# # # # #     const idx = DATA.segments.findIndex((s) => fi >= s.s && fi < s.e);
# # # # #     const cur = idx >= 0 ? idx : DATA.segments.length - 1;
# # # # #     $("caption").textContent = DATA.segments[cur] ? DATA.segments[cur].gloss : "";
# # # # #     segEls.forEach((el, i) => el.classList.toggle("on", i === cur));
# # # # #     seek.value = fi;
# # # # #     $("time").textContent = (tFrame / FPS).toFixed(1) + " / " + (N / FPS).toFixed(1) + " s";
# # # # #     controls.update();
# # # # #     renderer.render(scene, camera);
# # # # #     requestAnimationFrame(tick);
# # # # #   }
# # # # #   requestAnimationFrame(tick);
# # # # # })();
# # # # # </script>
# # # # # </body>
# # # # # </html>
# # # # # '''


# # # # # def write_html(timeline, xbot_path, out_path, title):
# # # # #     glb = Path(xbot_path).read_bytes()
# # # # #     data_json = json.dumps(timeline, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
# # # # #     html = (HTML_TEMPLATE
# # # # #             .replace("__TITLE__", title.replace("<", "&lt;"))
# # # # #             .replace("__DATA_JSON__", data_json)
# # # # #             .replace("__GLB_B64__", base64.b64encode(glb).decode("ascii")))
# # # # #     out = Path(out_path)
# # # # #     out.parent.mkdir(parents=True, exist_ok=True)
# # # # #     out.write_text(html, encoding="utf-8")
# # # # #     return out


# # # # # # =====================================================================
# # # # # # 7. Command line
# # # # # # =====================================================================
# # # # # def build_parser():
# # # # #     p = argparse.ArgumentParser(
# # # # #         description="Chuỗi gloss -> avatar Xbot chuyển động liên tục (file HTML độc lập).")
# # # # #     g = p.add_argument_group("đầu vào")
# # # # #     g.add_argument("--glosses", nargs="+", help='Danh sách gloss, ví dụ: --glosses "bạn" "đi học" "có không"')
# # # # #     g.add_argument("--sentence", help='Các gloss ngăn cách bằng dấu |, ví dụ: "bạn | đi học | có không"')
# # # # #     g.add_argument("--glosses-file", help="File .json (list) hoặc .txt (mỗi dòng 1 gloss)")
# # # # #     g = p.add_argument_group("đường dẫn")
# # # # #     g.add_argument("--labels", help="File ánh xạ VIDEO/LABEL (csv, tsv, txt, xlsx, json)")
# # # # #     g.add_argument("--videos", default=DEFAULT_VIDEOS, help="Thư mục chứa các video của dataset")
# # # # #     g.add_argument("--xbot", default=DEFAULT_XBOT, help="File Xbot.glb")
# # # # #     g.add_argument("--cache", default=DEFAULT_CACHE, help="Thư mục lưu tọa độ đã tính (.npz)")
# # # # #     g.add_argument("--out", default=DEFAULT_OUT, help="File HTML đầu ra")
# # # # #     g = p.add_argument_group("chọn video")
# # # # #     g.add_argument("--region", default="B,T,N", help="Thứ tự ưu tiên giọng vùng: B=Bắc, T=Trung, N=Nam")
# # # # #     g.add_argument("--search", help="Tìm nhãn chứa chuỗi này (không cần dấu) rồi thoát")
# # # # #     g.add_argument("--precompute-all", action="store_true",
# # # # #                    help="Tính trước tọa độ cho mọi gloss (lâu, chạy một lần)")
# # # # #     g = p.add_argument_group("chuyển động")
# # # # #     g.add_argument("--fps", type=float, default=30.0)
# # # # #     g.add_argument("--transition", type=float, default=0.25, help="Giây chuyển tiếp giữa 2 từ")
# # # # #     g.add_argument("--hold", type=float, default=0.2, help="Giây giữ tư thế đầu/cuối")
# # # # #     g.add_argument("--smooth-body", type=float, default=1.5, help="Độ mượt thân (khung hình, 0 = tắt)")
# # # # #     g.add_argument("--smooth-hands", type=float, default=1.0, help="Độ mượt ngón tay (0 = tắt)")
# # # # #     g.add_argument("--hand-gap", type=int, default=6, help="Nội suy khi mất tay tối đa N khung")
# # # # #     g.add_argument("--no-trim", action="store_true", help="Không cắt đoạn tay buông ở đầu/cuối video")
# # # # #     g.add_argument("--rest-threshold", type=float, default=0.10,
# # # # #                    help="Cổ tay phải cao hơn hông bao nhiêu mét để tính là đang ký")
# # # # #     g.add_argument("--complexity", type=int, default=1, choices=[0, 1, 2],
# # # # #                    help="Độ chính xác MediaPipe Pose (2 = chính xác nhất, chậm nhất)")
# # # # #     p.add_argument("--open", action="store_true", help="Mở file HTML sau khi tạo")
# # # # #     return p


# # # # # def get_glosses(args):
# # # # #     if args.glosses:
# # # # #         return [g for g in args.glosses if g.strip()]
# # # # #     if args.sentence:
# # # # #         return [g.strip() for g in args.sentence.split("|") if g.strip()]
# # # # #     if args.glosses_file:
# # # # #         txt = read_text_auto(args.glosses_file)
# # # # #         if args.glosses_file.lower().endswith(".json"):
# # # # #             return [str(g) for g in json.loads(txt)]
# # # # #         return [l.strip() for l in txt.splitlines() if l.strip()]
# # # # #     return []


# # # # # def main(argv=None, detector_factory=None):
# # # # #     args = build_parser().parse_args(argv)
# # # # #     videos_dir = Path(args.videos)

# # # # #     labels = args.labels or find_labels_file(videos_dir)
# # # # #     if not labels or not Path(labels).exists():
# # # # #         print("Không tìm thấy file nhãn. Hãy chỉ rõ bằng --labels \"đường\\dẫn\\file.csv\"")
# # # # #         return 2
# # # # #     records = load_records(labels)
# # # # #     index = GlossIndex(records, args.region.split(","))
# # # # #     print(f"Đã đọc {len(records)} video / {len(index.by_key)} khóa tra cứu từ: {labels}")

# # # # #     if args.search:
# # # # #         hits = index.search(args.search)
# # # # #         print(f'\nCác nhãn chứa "{args.search}" ({len(hits)} kết quả đầu):')
# # # # #         for r in hits:
# # # # #             print(f"  {r['video']:<14} {r['label']}")
# # # # #         return 0

# # # # #     if detector_factory is None:
# # # # #         detector_factory = lambda: MediaPipeDetector(args.complexity)

# # # # #     if args.precompute_all:
# # # # #         picks = {}
# # # # #         for rec in index.recs:
# # # # #             key = norm(rec["label"])
# # # # #             if key not in picks:
# # # # #                 picks[key] = index.choose(index.lookup(rec["label"]))[0]
# # # # #         todo = sorted(picks.values(), key=lambda r: natural_key(r["stem"]))
# # # # #         print(f"Tính trước {len(todo)} video (mỗi gloss một video)...")
# # # # #         for i, rec in enumerate(todo, 1):
# # # # #             vp = videos_dir / rec["video"]
# # # # #             try:
# # # # #                 _, hit = get_clip_data(vp, args.cache, detector_factory)
# # # # #                 print(f"[{i}/{len(todo)}] {rec['video']} {'(đã có)' if hit else 'xong'}")
# # # # #             except Exception as e:
# # # # #                 print(f"[{i}/{len(todo)}] {rec['video']} LỖI: {e}")
# # # # #         return 0

# # # # #     glosses = get_glosses(args)
# # # # #     if not glosses:
# # # # #         raw = input('Nhập các gloss, ngăn cách bằng dấu | (ví dụ: bạn | đi học | có không): ')
# # # # #         glosses = [g.strip() for g in raw.split("|") if g.strip()]
# # # # #     if not glosses:
# # # # #         print("Chưa có gloss nào.")
# # # # #         return 2

# # # # #     # ---- gloss -> video ----
# # # # #     picks, problems = [], []
# # # # #     for g in glosses:
# # # # #         found, missing = index.resolve_one(g)
# # # # #         picks += found
# # # # #         for w in missing:
# # # # #             sug = index.suggest(w)
# # # # #             problems.append(f'Không có gloss "{w}"' + (f" (gần giống: {', '.join(sug)})" if sug else ""))
# # # # #     print("\nChuỗi gloss -> video:")
# # # # #     for g, rec, note in picks:
# # # # #         print(f"  {g:<18} -> {rec['video']:<14} [{rec['label']}]" + (f"  ({note})" if note else ""))
# # # # #     for p in problems:
# # # # #         print("  CẢNH BÁO:", p)
# # # # #     if not picks:
# # # # #         return 1

# # # # #     # ---- landmarks (cached) ----
# # # # #     clips = []
# # # # #     for i, (g, rec, _) in enumerate(picks, 1):
# # # # #         vp = videos_dir / rec["video"]
# # # # #         cache_file = Path(args.cache) / (rec["stem"] + ".npz")
# # # # #         if not vp.exists() and not cache_file.exists():
# # # # #             print(f"  CẢNH BÁO: không thấy video {vp}")
# # # # #             continue
# # # # #         try:
# # # # #             raw, hit = get_clip_data(vp, args.cache, detector_factory)
# # # # #         except Exception as e:
# # # # #             print(f"  CẢNH BÁO: lỗi với {rec['video']}: {e}")
# # # # #             continue
# # # # #         clip, ok = process_clip(raw, args.fps, args)
# # # # #         if clip is None:
# # # # #             print(f"  CẢNH BÁO: {rec['video']} chỉ nhận diện được {ok:.0%} khung hình, bỏ qua")
# # # # #             continue
# # # # #         hands_ok = [float((~np.isnan(clip[k].reshape(len(clip[k]), -1)).any(axis=1)).mean())
# # # # #                     for k in ("lh", "rh")]
# # # # #         print(f"  [{i}/{len(picks)}] {rec['video']}: {len(clip['body'])} khung ({len(clip['body'])/args.fps:.1f}s), "
# # # # #               f"có tay trái {hands_ok[0]:.0%} / tay phải {hands_ok[1]:.0%}" + ("" if hit else "  (vừa tính xong, đã lưu cache)"))
# # # # #         clip.update({"gloss": g, "video": rec["video"]})
# # # # #         clips.append(clip)
# # # # #     if not clips:
# # # # #         print("Không có video nào dùng được.")
# # # # #         return 1

# # # # #     # ---- one continuous timeline -> html ----
# # # # #     timeline = assemble(clips, args.fps, args.transition, args.hold)
# # # # #     if not Path(args.xbot).exists():
# # # # #         print(f"Không thấy file Xbot: {args.xbot}  (dùng --xbot để chỉ đường dẫn)")
# # # # #         return 2
# # # # #     out = write_html(timeline, args.xbot, args.out, "Avatar: " + " | ".join(c["gloss"] for c in clips))
# # # # #     print(f"\nXong: {timeline['n']} khung hình = {timeline['n']/args.fps:.1f} giây")
# # # # #     print(f"Mở file này (bấm đúp): {out.resolve()}")
# # # # #     if args.open:
# # # # #         webbrowser.open(out.resolve().as_uri())
# # # # #     return 0


# # # # # if __name__ == "__main__":
# # # # #     sys.exit(main())


































# # # # # #!/usr/bin/env python3
# # # # # # -*- coding: utf-8 -*-
# # # # # """
# # # # # sign_to_avatar.py
# # # # # =================
# # # # # Gloss list  ->  videos of the dataset  ->  3D landmarks (cached .npz)
# # # # #             ->  ONE continuous animation of the Xbot avatar (standalone .html).

# # # # # Example:
# # # # #     python sign_to_avatar.py --glosses "bạn" "đi học" "có không"
# # # # #     python sign_to_avatar.py --sentence "bạn | đi học | có không" --open
# # # # #     python sign_to_avatar.py --search "địa chỉ"

# # # # # The output .html is a single file: double-click it, no server / localhost needed.
# # # # # (It only needs Internet once per open, to load three.js from a CDN.)
# # # # # """
# # # # # import argparse
# # # # # import base64
# # # # # import csv
# # # # # import difflib
# # # # # import io
# # # # # import json
# # # # # import os
# # # # # import re
# # # # # import sys
# # # # # import unicodedata
# # # # # import webbrowser
# # # # # from pathlib import Path

# # # # # import numpy as np

# # # # # # =====================================================================
# # # # # # DEFAULTS (edit these once, then you never need to type the paths)
# # # # # # =====================================================================
# # # # # DEFAULT_VIDEOS = r"C:\Users\ADMIN\qh\vsl-vietnamese-sign-languages\versions\5\Dataset\Videos"
# # # # # DEFAULT_XBOT = os.path.join("frontend_dis", "models", "Xbot.glb")
# # # # # DEFAULT_CACHE = "landmark_cache"
# # # # # DEFAULT_OUT = os.path.join("output", "sentence.html")

# # # # # CACHE_VERSION = 1
# # # # # VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")

# # # # # BODY_NAMES = [
# # # # #     "Hips", "Spine1", "Spine2", "Neck", "Head",
# # # # #     "LeftArm", "LeftForeArm", "LeftHand",
# # # # #     "RightArm", "RightForeArm", "RightHand",
# # # # #     "LeftUpLeg", "LeftLeg", "LeftFoot",
# # # # #     "RightUpLeg", "RightLeg", "RightFoot",
# # # # # ]

# # # # # try:  # make Vietnamese text safe to print on any console
# # # # #     sys.stdout.reconfigure(errors="replace")
# # # # #     sys.stderr.reconfigure(errors="replace")
# # # # # except Exception:
# # # # #     pass


# # # # # # =====================================================================
# # # # # # 1. Text helpers
# # # # # # =====================================================================
# # # # # def norm(s):
# # # # #     """NFC + lower-case + collapsed spaces."""
# # # # #     return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s)).strip().lower())


# # # # # def strip_accents(s):
# # # # #     s = norm(s).replace("đ", "d")
# # # # #     s = unicodedata.normalize("NFD", s)
# # # # #     return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# # # # # def without_parens(s):
# # # # #     return norm(re.sub(r"\([^)]*\)", " ", str(s)))


# # # # # def natural_key(s):
# # # # #     return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


# # # # # VIDEO_RE = re.compile(r"^(?P<base>.*\d)(?P<reg>[NTBntb])?$")


# # # # # def parse_video(name):
# # # # #     """'D0001N.mp4' -> ('D0001', 'N');  'D0002.mp4' -> ('D0002', '')."""
# # # # #     stem = Path(str(name).strip()).stem
# # # # #     m = VIDEO_RE.match(stem)
# # # # #     if m:
# # # # #         return m.group("base"), (m.group("reg") or "").upper()
# # # # #     return stem, ""


# # # # # def label_keys(label):
# # # # #     """All the lookup keys under which a dataset label can be found."""
# # # # #     plain = without_parens(label)
# # # # #     parts = {norm(label), plain}
# # # # #     for p in re.split(r"\s*[;/,]\s*", plain):
# # # # #         if p.strip():
# # # # #             parts.add(norm(p))
# # # # #     keys = set()
# # # # #     for p in parts:
# # # # #         if p:
# # # # #             keys.add(p)
# # # # #             keys.add(strip_accents(p))
# # # # #     return keys


# # # # # # =====================================================================
# # # # # # 2. Reading the label file (csv / tsv / txt / xlsx / json)
# # # # # # =====================================================================
# # # # # def read_text_auto(path):
# # # # #     raw = Path(path).read_bytes()
# # # # #     if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:200]:
# # # # #         return raw.decode("utf-16", errors="replace")
# # # # #     try:
# # # # #         return raw.decode("utf-8-sig")
# # # # #     except UnicodeDecodeError:
# # # # #         return raw.decode("cp1258", errors="replace")


# # # # # def _pick_columns(header):
# # # # #     h = [norm(c) for c in header]
# # # # #     vi = next((i for i, c in enumerate(h) if c in ("video", "file", "filename", "name")), None)
# # # # #     li = next((i for i, c in enumerate(h) if c in ("label", "gloss", "nhan", "nhãn", "text")), None)
# # # # #     return vi, li


# # # # # def load_records(path):
# # # # #     """Return [(video_name, label), ...] from any supported file type."""
# # # # #     path = str(path)
# # # # #     ext = Path(path).suffix.lower()

# # # # #     if ext == ".json":
# # # # #         data = json.loads(read_text_auto(path))
# # # # #         recs = []
# # # # #         if isinstance(data, dict):
# # # # #             for gloss, vids in data.items():
# # # # #                 if isinstance(vids, (str, dict)):
# # # # #                     vids = [vids]
# # # # #                 for v in vids:
# # # # #                     recs.append((v["video"] if isinstance(v, dict) else v, gloss))
# # # # #         else:
# # # # #             for item in data:
# # # # #                 if isinstance(item, dict):
# # # # #                     low = {norm(k): v for k, v in item.items()}
# # # # #                     recs.append((low.get("video") or low.get("file"),
# # # # #                                  low.get("label") or low.get("gloss")))
# # # # #                 else:
# # # # #                     recs.append((item[0], item[1]))
# # # # #         return [(str(v), str(l)) for v, l in recs if v and l]

# # # # #     if ext in (".xlsx", ".xls", ".xlsm"):
# # # # #         import pandas as pd  # needs openpyxl for .xlsx
# # # # #         df = pd.read_excel(path, dtype=str).fillna("")
# # # # #         rows = [list(df.columns)] + df.values.tolist()
# # # # #     else:
# # # # #         text = read_text_auto(path)
# # # # #         first = text.splitlines()[0] if text else ""
# # # # #         delim = max(["\t", ",", ";"], key=first.count)
# # # # #         rows = list(csv.reader(io.StringIO(text), delimiter=delim))

# # # # #     rows = [r for r in rows if r and any(str(c).strip() for c in r)]
# # # # #     if not rows:
# # # # #         return []
# # # # #     vi, li = _pick_columns(rows[0])
# # # # #     start = 1
# # # # #     if vi is None or li is None:  # no header: first two columns
# # # # #         vi, li = 0, 1
# # # # #         start = 0 if Path(str(rows[0][0])).suffix.lower() in VIDEO_EXTS else 1
# # # # #     out = []
# # # # #     for r in rows[start:]:
# # # # #         if len(r) > max(vi, li) and str(r[vi]).strip() and str(r[li]).strip():
# # # # #             out.append((str(r[vi]).strip(), str(r[li]).strip()))
# # # # #     return out


# # # # # def find_labels_file(videos_dir):
# # # # #     vd = Path(videos_dir)
# # # # #     exts = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json")
# # # # #     cands = []
# # # # #     for d in (vd, vd.parent, vd.parent.parent):
# # # # #         if d.is_dir():
# # # # #             cands += [p for p in d.iterdir() if p.suffix.lower() in exts]
# # # # #     hits = [p for p in cands if "label" in p.name.lower()]
# # # # #     if len(hits) >= 1:
# # # # #         return str(sorted(hits, key=lambda p: len(str(p)))[0])
# # # # #     return None


# # # # # # =====================================================================
# # # # # # 3. Gloss index: label -> video
# # # # # # =====================================================================
# # # # # class GlossIndex:
# # # # #     def __init__(self, records, region_pref=("B", "T", "N")):
# # # # #         self.region_pref = [r.upper() for r in region_pref]
# # # # #         self.recs = []
# # # # #         self.by_key = {}
# # # # #         self.by_stem = {}
# # # # #         for video, label in records:
# # # # #             base, reg = parse_video(video)
# # # # #             rec = {"video": Path(video).name, "stem": Path(video).stem,
# # # # #                    "base": base, "region": reg, "label": label}
# # # # #             self.recs.append(rec)
# # # # #             self.by_stem[norm(rec["stem"])] = rec
# # # # #             for k in label_keys(label):
# # # # #                 self.by_key.setdefault(k, []).append(rec)

# # # # #     def lookup(self, text):
# # # # #         for v in (norm(text), without_parens(text),
# # # # #                   strip_accents(text), strip_accents(without_parens(text))):
# # # # #             if v and v in self.by_key:
# # # # #                 return self.by_key[v]
# # # # #         return []

# # # # #     def choose(self, recs):
# # # # #         """One video for a gloss: first sign (lowest id), preferred region."""
# # # # #         groups = {}
# # # # #         for r in recs:
# # # # #             groups.setdefault(r["base"], []).append(r)
# # # # #         bases = sorted(groups, key=natural_key)
# # # # #         group = groups[bases[0]]
# # # # #         group.sort(key=lambda r: (self.region_pref.index(r["region"])
# # # # #                                   if r["region"] in self.region_pref else 99,
# # # # #                                   natural_key(r["stem"])))
# # # # #         return group[0], len(bases) - 1

# # # # #     def resolve_one(self, gloss):
# # # # #         """Return (list of (gloss_text, rec, note), list of missing words)."""
# # # # #         g = str(gloss).strip()
# # # # #         if not g:
# # # # #             return [], []
# # # # #         # a video id typed directly, e.g. "D0001T"
# # # # #         rec = self.by_stem.get(norm(Path(g).stem))
# # # # #         if rec is not None and re.fullmatch(r"[dD]\d+[NTBntb]?(\.\w+)?", g):
# # # # #             return [(g, rec, "")], []

# # # # #         recs = self.lookup(g)
# # # # #         if recs:
# # # # #             rec, extra = self.choose(recs)
# # # # #             note = f"còn {extra} cách ký khác" if extra > 0 else ""
# # # # #             return [(g, rec, note)], []

# # # # #         # not a known gloss: split into the longest known pieces
# # # # #         words = norm(g).split()
# # # # #         found, missing, i = [], [], 0
# # # # #         while i < len(words):
# # # # #             for j in range(len(words), i, -1):
# # # # #                 phrase = " ".join(words[i:j])
# # # # #                 recs = self.lookup(phrase)
# # # # #                 if recs:
# # # # #                     rec, extra = self.choose(recs)
# # # # #                     found.append((phrase, rec, f'tách từ "{g}"'))
# # # # #                     i = j
# # # # #                     break
# # # # #             else:
# # # # #                 missing.append(words[i])
# # # # #                 i += 1
# # # # #         if not found:
# # # # #             return [], [g]
# # # # #         return found, missing

# # # # #     def suggest(self, text, n=4):
# # # # #         pool = {}
# # # # #         for k, recs in self.by_key.items():
# # # # #             if strip_accents(k) == k:
# # # # #                 pool[k] = recs[0]["label"]
# # # # #         close = difflib.get_close_matches(strip_accents(text), list(pool), n=n, cutoff=0.6)
# # # # #         return [pool[c] for c in close]

# # # # #     def search(self, text, limit=30):
# # # # #         t = strip_accents(text)
# # # # #         hits = [r for r in self.recs if t in strip_accents(r["label"])]
# # # # #         return sorted(hits, key=lambda r: natural_key(r["stem"]))[:limit]


# # # # # # =====================================================================
# # # # # # 4. Landmark extraction (MediaPipe) + cache
# # # # # # =====================================================================
# # # # # def assign_hands(hands, left_wrist, right_wrist):
# # # # #     """
# # # # #     hands: [(image_wrist_xy, world_21x3, label)], wrists in normalised image coords.
# # # # #     Decide which detected hand is the person's LEFT / RIGHT by comparing with the
# # # # #     body-pose wrists (more reliable than the handedness label for un-mirrored video).
# # # # #     """
# # # # #     res = {"L": None, "R": None}
# # # # #     if not hands:
# # # # #         return res

# # # # #     def d(a, b):
# # # # #         return float(np.hypot(a[0] - b[0], a[1] - b[1]))

# # # # #     if left_wrist is not None and right_wrist is not None:
# # # # #         if len(hands) == 1:
# # # # #             h = hands[0]
# # # # #             res["L" if d(h[0], left_wrist) <= d(h[0], right_wrist) else "R"] = h[1]
# # # # #         else:
# # # # #             h0, h1 = hands[0], hands[1]
# # # # #             a = d(h0[0], left_wrist) + d(h1[0], right_wrist)
# # # # #             b = d(h0[0], right_wrist) + d(h1[0], left_wrist)
# # # # #             if a <= b:
# # # # #                 res["L"], res["R"] = h0[1], h1[1]
# # # # #             else:
# # # # #                 res["L"], res["R"] = h1[1], h0[1]
# # # # #     else:  # no body wrists: use the label (MediaPipe assumes a mirrored image -> swap)
# # # # #         for h in hands:
# # # # #             res["R" if h[2] == "Left" else "L"] = h[1]
# # # # #     return res


# # # # # class MediaPipeDetector:
# # # # #     """Pose (33 world landmarks) + Hands (21 world landmarks each), one video at a time."""

# # # # #     def __init__(self, complexity=1):
# # # # #         import mediapipe as mp
# # # # #         self.pose = mp.solutions.pose.Pose(
# # # # #             static_image_mode=False, model_complexity=complexity, smooth_landmarks=True,
# # # # #             min_detection_confidence=0.5, min_tracking_confidence=0.5)
# # # # #         self.hands = mp.solutions.hands.Hands(
# # # # #             static_image_mode=False, max_num_hands=2, model_complexity=1,
# # # # #             min_detection_confidence=0.5, min_tracking_confidence=0.5)

# # # # #     def __enter__(self):
# # # # #         return self

# # # # #     def __exit__(self, *a):
# # # # #         self.pose.close()
# # # # #         self.hands.close()
# # # # #         return False

# # # # #     def process(self, rgb):
# # # # #         pr = self.pose.process(rgb)
# # # # #         hr = self.hands.process(rgb)
# # # # #         pose_world = left_w = right_w = None
# # # # #         if pr.pose_world_landmarks:
# # # # #             pose_world = np.array([[l.x, l.y, l.z] for l in pr.pose_world_landmarks.landmark],
# # # # #                                   dtype=np.float32)
# # # # #         if pr.pose_landmarks:
# # # # #             lm = pr.pose_landmarks.landmark
# # # # #             left_w, right_w = (lm[15].x, lm[15].y), (lm[16].x, lm[16].y)
# # # # #         hands = []
# # # # #         if hr.multi_hand_world_landmarks and hr.multi_hand_landmarks:
# # # # #             for wl, il, hd in zip(hr.multi_hand_world_landmarks,
# # # # #                                   hr.multi_hand_landmarks, hr.multi_handedness):
# # # # #                 world = np.array([[l.x, l.y, l.z] for l in wl.landmark], dtype=np.float32)
# # # # #                 hands.append(((il.landmark[0].x, il.landmark[0].y), world,
# # # # #                               hd.classification[0].label))
# # # # #         return {"pose": pose_world, "left_wrist": left_w, "right_wrist": right_w, "hands": hands}


# # # # # def extract_video(video_path, detector_factory, target_width=640):
# # # # #     """Run the detector on every frame. Returns dict of arrays (NaN = not detected)."""
# # # # #     import cv2
# # # # #     cap = cv2.VideoCapture(str(video_path))
# # # # #     if not cap.isOpened():
# # # # #         raise IOError(f"Không mở được video: {video_path}")
# # # # #     fps = cap.get(cv2.CAP_PROP_FPS)
# # # # #     if not fps or fps != fps or fps <= 1:
# # # # #         fps = 30.0
# # # # #     pose_l, lh_l, rh_l = [], [], []
# # # # #     nan_pose = np.full((33, 3), np.nan, np.float32)
# # # # #     nan_hand = np.full((21, 3), np.nan, np.float32)
# # # # #     with detector_factory() as det:
# # # # #         while True:
# # # # #             ok, frame = cap.read()
# # # # #             if not ok:
# # # # #                 break
# # # # #             h, w = frame.shape[:2]
# # # # #             if w != target_width and w > 0:
# # # # #                 frame = cv2.resize(frame, (target_width, int(h * target_width / w)))
# # # # #             rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
# # # # #             r = det.process(rgb)
# # # # #             pose_l.append(r["pose"] if r["pose"] is not None else nan_pose)
# # # # #             a = assign_hands(r["hands"], r["left_wrist"], r["right_wrist"])
# # # # #             lh_l.append(a["L"] if a["L"] is not None else nan_hand)
# # # # #             rh_l.append(a["R"] if a["R"] is not None else nan_hand)
# # # # #     cap.release()
# # # # #     if not pose_l:
# # # # #         raise IOError(f"Video rỗng: {video_path}")
# # # # #     return {"pose": np.stack(pose_l).astype(np.float32),
# # # # #             "lhand": np.stack(lh_l).astype(np.float32),
# # # # #             "rhand": np.stack(rh_l).astype(np.float32),
# # # # #             "fps": float(fps)}


# # # # # def get_clip_data(video_path, cache_dir, detector_factory):
# # # # #     cache_path = Path(cache_dir) / (Path(video_path).stem + ".npz")
# # # # #     if cache_path.exists():
# # # # #         try:
# # # # #             d = np.load(cache_path)
# # # # #             if int(d["version"]) == CACHE_VERSION:
# # # # #                 data = {k: d[k] for k in ("pose", "lhand", "rhand")}
# # # # #                 data["fps"] = float(d["fps"])
# # # # #                 return data, True
# # # # #         except Exception:
# # # # #             pass
# # # # #     data = extract_video(video_path, detector_factory)
# # # # #     cache_path.parent.mkdir(parents=True, exist_ok=True)
# # # # #     np.savez_compressed(cache_path, pose=data["pose"], lhand=data["lhand"],
# # # # #                         rhand=data["rhand"], fps=data["fps"], version=CACHE_VERSION)
# # # # #     return data, False


# # # # # # =====================================================================
# # # # # # 5. Clean-up: resample, fill gaps, smooth, trim, join
# # # # # # =====================================================================
# # # # # def resample(arr, src_fps, dst_fps):
# # # # #     T = len(arr)
# # # # #     if T < 2 or abs(src_fps - dst_fps) < 1e-3:
# # # # #         return arr
# # # # #     new_T = max(2, int(round((T - 1) * dst_fps / src_fps)) + 1)
# # # # #     t = np.linspace(0, T - 1, new_T)
# # # # #     i0 = np.floor(t).astype(int)
# # # # #     i1 = np.minimum(i0 + 1, T - 1)
# # # # #     a = (t - i0).reshape((-1,) + (1,) * (arr.ndim - 1))
# # # # #     return arr[i0] * (1 - a) + arr[i1] * a   # NaN stays NaN if either neighbour is missing


# # # # # def fill_gaps(arr, max_gap, hold_edges):
# # # # #     T = len(arr)
# # # # #     flat = arr.reshape(T, -1).astype(np.float64)
# # # # #     valid = ~np.isnan(flat).any(axis=1)
# # # # #     idx = np.where(valid)[0]
# # # # #     if len(idx) == 0:
# # # # #         return arr
# # # # #     out = flat.copy()
# # # # #     for a, b in zip(idx[:-1], idx[1:]):
# # # # #         gap = b - a - 1
# # # # #         if 0 < gap <= max_gap:
# # # # #             for k in range(1, gap + 1):
# # # # #                 w = k / (gap + 1)
# # # # #                 out[a + k] = flat[a] * (1 - w) + flat[b] * w
# # # # #     if hold_edges:
# # # # #         out[:idx[0]] = flat[idx[0]]
# # # # #         out[idx[-1] + 1:] = flat[idx[-1]]
# # # # #     return out.reshape(arr.shape).astype(np.float32)


# # # # # def hold_last_valid(arr):
# # # # #     """Replace remaining NaN frames by the previous (or next) valid frame."""
# # # # #     T = len(arr)
# # # # #     flat = arr.reshape(T, -1).copy()
# # # # #     valid = ~np.isnan(flat).any(axis=1)
# # # # #     if not valid.any():
# # # # #         return arr
# # # # #     last = None
# # # # #     for i in range(T):
# # # # #         if valid[i]:
# # # # #             last = flat[i].copy()
# # # # #         elif last is not None:
# # # # #             flat[i] = last
# # # # #     first = np.where(valid)[0][0]
# # # # #     flat[:first] = flat[first]
# # # # #     return flat.reshape(arr.shape)


# # # # # def smooth_nan(arr, sigma):
# # # # #     """Gaussian smoothing along time; invalid (NaN) frames stay invalid."""
# # # # #     T = len(arr)
# # # # #     if sigma <= 0 or T < 2:
# # # # #         return arr
# # # # #     flat = arr.reshape(T, -1).astype(np.float64)
# # # # #     valid = ~np.isnan(flat).any(axis=1)
# # # # #     if not valid.any():
# # # # #         return arr
# # # # #     i = np.arange(T)
# # # # #     W = np.exp(-0.5 * ((i[:, None] - i[None, :]) / sigma) ** 2) * valid[None, :]
# # # # #     num = W @ np.where(valid[:, None], flat, 0.0)
# # # # #     den = np.maximum(W.sum(axis=1, keepdims=True), 1e-9)
# # # # #     out = num / den
# # # # #     out[~valid] = np.nan
# # # # #     return out.reshape(arr.shape).astype(np.float32)


# # # # # def body_keypoints(pose):
# # # # #     """(T,33,3) MediaPipe pose -> (T,17,3) avatar keypoints (order = BODY_NAMES)."""
# # # # #     hips = (pose[:, 23] + pose[:, 24]) / 2
# # # # #     neck = (pose[:, 11] + pose[:, 12]) / 2
# # # # #     head = (pose[:, 7] + pose[:, 8]) / 2
# # # # #     spine1 = hips + (neck - hips) / 3
# # # # #     spine2 = hips + (neck - hips) * 2 / 3
# # # # #     kp = [hips, spine1, spine2, neck, head,
# # # # #           pose[:, 11], pose[:, 13], pose[:, 15],
# # # # #           pose[:, 12], pose[:, 14], pose[:, 16],
# # # # #           pose[:, 23], pose[:, 25], pose[:, 27],
# # # # #           pose[:, 24], pose[:, 26], pose[:, 28]]
# # # # #     return np.stack(kp, axis=1).astype(np.float32)


# # # # # def active_range(pose, threshold, pad):
# # # # #     """Frames where at least one wrist is clearly above the hips (= signing)."""
# # # # #     T = len(pose)
# # # # #     hips_y = (pose[:, 23, 1] + pose[:, 24, 1]) / 2
# # # # #     wrist_y = np.minimum(pose[:, 15, 1], pose[:, 16, 1])   # MediaPipe y points DOWN
# # # # #     idx = np.where(wrist_y < hips_y - threshold)[0]
# # # # #     if len(idx) == 0:
# # # # #         return 0, T
# # # # #     return max(0, int(idx[0]) - pad), min(T, int(idx[-1]) + pad + 1)


# # # # # def process_clip(raw, fps, args):
# # # # #     pose = resample(raw["pose"], raw["fps"], fps)
# # # # #     lh = resample(raw["lhand"], raw["fps"], fps)
# # # # #     rh = resample(raw["rhand"], raw["fps"], fps)

# # # # #     ok_ratio = float((~np.isnan(pose.reshape(len(pose), -1)).any(axis=1)).mean())
# # # # #     if ok_ratio < 0.3:
# # # # #         return None, ok_ratio

# # # # #     pose = fill_gaps(pose, max_gap=int(fps * 0.6), hold_edges=True)
# # # # #     pose = hold_last_valid(pose)
# # # # #     pose = smooth_nan(pose, args.smooth_body)
# # # # #     lh = smooth_nan(fill_gaps(lh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)
# # # # #     rh = smooth_nan(fill_gaps(rh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)

# # # # #     if not args.no_trim:
# # # # #         a, b = active_range(pose, args.rest_threshold, int(round(fps * 0.12)))
# # # # #         pose, lh, rh = pose[a:b], lh[a:b], rh[a:b]
# # # # #     return {"body": body_keypoints(pose), "lh": lh, "rh": rh}, ok_ratio


# # # # # def _ease(w):
# # # # #     return 0.5 - 0.5 * np.cos(np.pi * w)


# # # # # def assemble(clips, fps, transition_s, hold_s):
# # # # #     """clips: [{gloss, video, body, lh, rh}] -> one timeline."""
# # # # #     ntr = max(0, int(round(transition_s * fps)))
# # # # #     hold = max(0, int(round(hold_s * fps)))
# # # # #     B, LH, RH, segs = [], [], [], []
# # # # #     cursor = 0

# # # # #     def add(body, lh, rh):
# # # # #         nonlocal cursor
# # # # #         B.append(body)
# # # # #         LH.append(lh)
# # # # #         RH.append(rh)
# # # # #         cursor += len(body)

# # # # #     for i, c in enumerate(clips):
# # # # #         seg_start = cursor
# # # # #         if i == 0 and hold:
# # # # #             add(np.repeat(c["body"][:1], hold, 0), np.repeat(c["lh"][:1], hold, 0),
# # # # #                 np.repeat(c["rh"][:1], hold, 0))
# # # # #         if i > 0 and ntr:
# # # # #             p = clips[i - 1]
# # # # #             w = _ease(np.arange(1, ntr + 1) / (ntr + 1)).reshape(-1, 1, 1)
# # # # #             body = p["body"][-1][None] * (1 - w) + c["body"][0][None] * w
# # # # #             lh = p["lh"][-1][None] * (1 - w) + c["lh"][0][None] * w     # NaN if either is missing
# # # # #             rh = p["rh"][-1][None] * (1 - w) + c["rh"][0][None] * w
# # # # #             add(body, lh, rh)
# # # # #         add(c["body"], c["lh"], c["rh"])
# # # # #         if i == len(clips) - 1 and hold:
# # # # #             add(np.repeat(c["body"][-1:], hold, 0), np.repeat(c["lh"][-1:], hold, 0),
# # # # #                 np.repeat(c["rh"][-1:], hold, 0))
# # # # #         segs.append({"s": seg_start, "e": cursor, "gloss": c["gloss"], "video": c["video"]})

# # # # #     body = np.concatenate(B).astype(np.float64)
# # # # #     lh = np.concatenate(LH).astype(np.float64)
# # # # #     rh = np.concatenate(RH).astype(np.float64)
# # # # #     lv = (~np.isnan(lh.reshape(len(lh), -1)).any(axis=1)).astype(int)
# # # # #     rv = (~np.isnan(rh.reshape(len(rh), -1)).any(axis=1)).astype(int)
# # # # #     lh = np.nan_to_num(lh, nan=0.0)
# # # # #     rh = np.nan_to_num(rh, nan=0.0)
# # # # #     return {"fps": fps, "n": int(len(body)),
# # # # #             "body": np.round(body, 4).ravel().tolist(),
# # # # #             "lh": np.round(lh, 4).ravel().tolist(),
# # # # #             "rh": np.round(rh, 4).ravel().tolist(),
# # # # #             "lv": lv.tolist(), "rv": rv.tolist(), "segments": segs}


# # # # # # =====================================================================
# # # # # # 6. The standalone player (HTML + JavaScript, three.js r128 from a CDN)
# # # # # # =====================================================================
# # # # # HTML_TEMPLATE = r'''<!DOCTYPE html>
# # # # # <html lang="vi">
# # # # # <head>
# # # # # <meta charset="utf-8">
# # # # # <meta name="viewport" content="width=device-width, initial-scale=1">
# # # # # <title>__TITLE__</title>
# # # # # <style>
# # # # #   :root { color-scheme: dark; }
# # # # #   html, body { margin: 0; height: 100%; overflow: hidden; background: #0b1220; color: #e5e7eb;
# # # # #                font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
# # # # #   #stage { position: fixed; inset: 0; }
# # # # #   #stage canvas { display: block; }
# # # # #   #caption { position: fixed; top: 18px; left: 0; right: 0; text-align: center; pointer-events: none;
# # # # #              font-size: 38px; font-weight: 700; text-shadow: 0 2px 12px #000; min-height: 46px; }
# # # # #   #panel { position: fixed; left: 12px; right: 12px; bottom: 12px; padding: 10px 14px;
# # # # #            background: rgba(15, 23, 42, .90); border: 1px solid #334155; border-radius: 12px; }
# # # # #   .row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 5px 0; }
# # # # #   button, select { background: #1e293b; color: #e5e7eb; border: 1px solid #475569; border-radius: 8px;
# # # # #                    padding: 6px 12px; font-size: 14px; cursor: pointer; }
# # # # #   button:hover { background: #334155; }
# # # # #   button.rec { border-color: #ef4444; }
# # # # #   input[type=range] { flex: 1; min-width: 160px; }
# # # # #   label { font-size: 13px; color: #cbd5e1; display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
# # # # #   .chip { padding: 3px 10px; border-radius: 999px; border: 1px solid #475569; font-size: 13px; cursor: pointer; }
# # # # #   .chip.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
# # # # #   #status { font-size: 12px; color: #94a3b8; }
# # # # #   #status.err { color: #fca5a5; font-size: 14px; }
# # # # # </style>
# # # # # </head>
# # # # # <body>
# # # # # <div id="stage"></div>
# # # # # <div id="caption"></div>
# # # # # <div id="panel">
# # # # #   <div class="row">
# # # # #     <button id="play">Tạm dừng</button>
# # # # #     <button id="restart">Phát lại</button>
# # # # #     <input type="range" id="seek" min="0" max="1" step="1" value="0">
# # # # #     <span id="time">0.0 / 0.0 s</span>
# # # # #     <select id="speed" title="Tốc độ">
# # # # #       <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
# # # # #       <option value="1" selected>1x</option><option value="1.5">1.5x</option>
# # # # #     </select>
# # # # #   </div>
# # # # #   <div class="row" id="chips"></div>
# # # # #   <div class="row">
# # # # #     <label><input type="checkbox" id="o_loop" checked> Lặp lại</label>
# # # # #     <label><input type="checkbox" id="o_fingers" checked> Ngón tay</label>
# # # # #     <label><input type="checkbox" id="o_legs"> Chân</label>
# # # # #     <label><input type="checkbox" id="o_mirror"> Lật trái/phải</label>
# # # # #     <label><input type="checkbox" id="o_flipz"> Đảo chiều sâu</label>
# # # # #     <label><input type="checkbox" id="o_swap"> Đổi tay trái/phải</label>
# # # # #     <button id="rec" class="rec">Ghi video (.webm)</button>
# # # # #   </div>
# # # # #   <div id="status">Đang tải mô hình...</div>
# # # # # </div>

# # # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
# # # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
# # # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
# # # # # <script>
# # # # # "use strict";
# # # # # const DATA = __DATA_JSON__;
# # # # # const GLB_B64 = "__GLB_B64__";
# # # # # const $ = (id) => document.getElementById(id);

# # # # # function fail(msg) { const s = $("status"); s.textContent = msg; s.className = "err"; }

# # # # # const N = DATA.n, FPS = DATA.fps;
# # # # # const body = DATA.body, lh = DATA.lh, rh = DATA.rh, lv = DATA.lv, rv = DATA.rv;
# # # # # const opts = { mirror: false, flipZ: false, swapHands: false, legs: false,
# # # # #                fingers: true, loop: true, speed: 1 };

# # # # # // ==== RETARGET START ====
# # # # # // Turns MediaPipe 3D points into bone rotations of the Mixamo-style Xbot skeleton.
# # # # # const BODY = ["Hips","Spine1","Spine2","Neck","Head","LeftArm","LeftForeArm","LeftHand",
# # # # #   "RightArm","RightForeArm","RightHand","LeftUpLeg","LeftLeg","LeftFoot","RightUpLeg","RightLeg","RightFoot"];
# # # # # const FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"];
# # # # # // [bone, bone it must point to] - parents first
# # # # # const AIM_PAIRS = [
# # # # #   ["Hips","Spine1"], ["Spine1","Spine2"], ["Spine2","Neck"], ["Neck","Head"],
# # # # #   ["LeftArm","LeftForeArm"], ["LeftForeArm","LeftHand"],
# # # # #   ["RightArm","RightForeArm"], ["RightForeArm","RightHand"],
# # # # #   ["LeftUpLeg","LeftLeg"], ["LeftLeg","LeftFoot"],
# # # # #   ["RightUpLeg","RightLeg"], ["RightLeg","RightFoot"],
# # # # # ];
# # # # # const LEG_BONES = ["LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"];

# # # # # const bones = {};      // clean name -> bone
# # # # # const restQ = {};      // clean name -> rest-pose rotation
# # # # # let rootObj = null;
# # # # # const handState = { Left: { w: 0, last: null }, Right: { w: 0, last: null } };

# # # # # function cleanName(n) { return n.replace(/^mixamorig:?/, ""); }

# # # # # function setupModel(model) {
# # # # #   rootObj = model;
# # # # #   model.traverse((o) => {
# # # # #     if (o.isBone) { const c = cleanName(o.name); bones[c] = o; restQ[c] = o.quaternion.clone(); }
# # # # #   });
# # # # #   let fingerBases = 0;
# # # # #   for (const s of ["Left", "Right"]) for (const f of FINGERS) if (bones[s + "Hand" + f + "1"]) fingerBases++;
# # # # #   return { bones: Object.keys(bones).length, fingerBases };
# # # # # }

# # # # # function resetPose() {
# # # # #   for (const k in bones) bones[k].quaternion.copy(restQ[k]);
# # # # #   if (rootObj) rootObj.updateMatrixWorld(true);
# # # # # }

# # # # # // Rotate a bone by a rotation given in WORLD space.
# # # # # function applyWorldRotation(bone, qWorld) {
# # # # #   if (!bone || !bone.parent) return;
# # # # #   bone.parent.updateWorldMatrix(true, false);
# # # # #   const pq = bone.parent.getWorldQuaternion(new THREE.Quaternion());
# # # # #   const adj = pq.clone().invert().multiply(qWorld).multiply(pq);
# # # # #   bone.quaternion.premultiply(adj);
# # # # #   bone.updateMatrixWorld(true);
# # # # # }

# # # # # // Make the direction  bone -> child  point along `dir` (world space).
# # # # # function aimBone(bone, child, dir) {
# # # # #   if (!bone || !child || dir.lengthSq() < 1e-10) return;
# # # # #   bone.updateWorldMatrix(true, true);
# # # # #   const p = bone.getWorldPosition(new THREE.Vector3());
# # # # #   const c = child.getWorldPosition(new THREE.Vector3());
# # # # #   const cur = c.sub(p);
# # # # #   if (cur.lengthSq() < 1e-12) return;
# # # # #   cur.normalize();
# # # # #   applyWorldRotation(bone, new THREE.Quaternion().setFromUnitVectors(cur, dir.clone().normalize()));
# # # # # }

# # # # # // Twist a bone around `axisDir` so that curSide lines up with tgtSide (palm orientation).
# # # # # function rollBoneAround(bone, axisDir, curSide, tgtSide) {
# # # # #   const a = axisDir.clone().normalize();
# # # # #   const c = curSide.clone().sub(a.clone().multiplyScalar(curSide.dot(a)));
# # # # #   const t = tgtSide.clone().sub(a.clone().multiplyScalar(tgtSide.dot(a)));
# # # # #   if (c.lengthSq() < 1e-10 || t.lengthSq() < 1e-10) return;
# # # # #   c.normalize(); t.normalize();
# # # # #   let angle = Math.acos(THREE.MathUtils.clamp(c.dot(t), -1, 1));
# # # # #   if (new THREE.Vector3().crossVectors(c, t).dot(a) < 0) angle = -angle;
# # # # #   applyWorldRotation(bone, new THREE.Quaternion().setFromAxisAngle(a, angle));
# # # # # }

# # # # # function blendToRest(name, w) {
# # # # #   if (w >= 0.999 || !bones[name]) return;
# # # # #   const q = bones[name].quaternion.clone();
# # # # #   bones[name].quaternion.copy(restQ[name]).slerp(q, w);
# # # # #   bones[name].updateMatrixWorld(true);
# # # # # }

# # # # # function applyBody(P) {
# # # # #   for (const [a, b] of AIM_PAIRS) {
# # # # #     if (!opts.legs && LEG_BONES.includes(a)) continue;
# # # # #     if (!bones[a] || !bones[b] || !P[a] || !P[b]) continue;
# # # # #     aimBone(bones[a], bones[b], P[b].clone().sub(P[a]));
# # # # #   }
# # # # # }

# # # # # // H: {Wrist, Thumb1..Pinky4} -> Vector3 ; w: 0..1 blend weight (0 = rest pose)
# # # # # function applyHand(side, H, w) {
# # # # #   if (!H || w <= 0.001) return;
# # # # #   const wrist = bones[side + "Hand"], mid1 = bones[side + "HandMiddle1"];
# # # # #   const idx1 = bones[side + "HandIndex1"], pky1 = bones[side + "HandPinky1"];
# # # # #   if (wrist && mid1 && H.Wrist && H.Middle1) {
# # # # #     const axis = H.Middle1.clone().sub(H.Wrist);
# # # # #     aimBone(wrist, mid1, axis);
# # # # #     if (idx1 && pky1 && H.Index1 && H.Pinky1) {
# # # # #       const a = idx1.getWorldPosition(new THREE.Vector3());
# # # # #       const b = pky1.getWorldPosition(new THREE.Vector3());
# # # # #       rollBoneAround(wrist, axis, a.sub(b), H.Index1.clone().sub(H.Pinky1));
# # # # #     }
# # # # #     blendToRest(side + "Hand", w);
# # # # #   }
# # # # #   for (const f of FINGERS) {
# # # # #     for (let n = 1; n <= 3; n++) {
# # # # #       const name = side + "Hand" + f + n;
# # # # #       const bone = bones[name], child = bones[side + "Hand" + f + (n + 1)];
# # # # #       const p0 = H[f + n], p1 = H[f + (n + 1)];
# # # # #       if (bone && child && p0 && p1) {
# # # # #         aimBone(bone, child, p1.clone().sub(p0));
# # # # #         blendToRest(name, w);
# # # # #       }
# # # # #     }
# # # # #   }
# # # # # }

# # # # # // MediaPipe camera frame (x right, y down, z away) -> model frame (x right, y up, z towards viewer)
# # # # # function toModel(x, y, z) {
# # # # #   return new THREE.Vector3((opts.mirror ? -1 : 1) * x, -y, -(opts.flipZ ? -1 : 1) * z);
# # # # # }

# # # # # function sampleFrame(f) {
# # # # #   const f0 = Math.max(0, Math.min(N - 1, Math.floor(f)));
# # # # #   const f1 = Math.min(f0 + 1, N - 1);
# # # # #   const a = Math.max(0, Math.min(1, f - f0));
# # # # #   const lerp = (u, v) => u + (v - u) * a;

# # # # #   const P = {};
# # # # #   for (let j = 0; j < BODY.length; j++) {
# # # # #     const o0 = (f0 * BODY.length + j) * 3, o1 = (f1 * BODY.length + j) * 3;
# # # # #     P[BODY[j]] = toModel(lerp(body[o0], body[o1]), lerp(body[o0 + 1], body[o1 + 1]), lerp(body[o0 + 2], body[o1 + 2]));
# # # # #   }

# # # # #   const hands = { Left: null, Right: null };
# # # # #   const srcs = opts.swapHands
# # # # #     ? [["Left", rh, rv], ["Right", lh, lv]]
# # # # #     : [["Left", lh, lv], ["Right", rh, rv]];
# # # # #   for (const [side, arr, val] of srcs) {
# # # # #     if (!(val[f0] && val[f1])) continue;
# # # # #     const pt = (k) => {
# # # # #       const o0 = (f0 * 21 + k) * 3, o1 = (f1 * 21 + k) * 3;
# # # # #       return toModel(lerp(arr[o0], arr[o1]), lerp(arr[o0 + 1], arr[o1 + 1]), lerp(arr[o0 + 2], arr[o1 + 2]));
# # # # #     };
# # # # #     const H = { Wrist: pt(0) };
# # # # #     FINGERS.forEach((fn, fi) => { for (let n = 1; n <= 4; n++) H[fn + n] = pt(1 + 4 * fi + (n - 1)); });
# # # # #     hands[side] = H;
# # # # #   }
# # # # #   return { P, hands };
# # # # # }

# # # # # // Pose the whole avatar for (fractional) frame f. dt = seconds since last call.
# # # # # function applyFrame(f, dt) {
# # # # #   if (!rootObj) return;
# # # # #   const { P, hands } = sampleFrame(f);
# # # # #   resetPose();                      // always start from the rest pose: no drift, no accumulated twist
# # # # #   applyBody(P);
# # # # #   for (const side of ["Left", "Right"]) {
# # # # #     const st = handState[side], H = hands[side];
# # # # #     if (H && opts.fingers) { st.last = H; st.w = Math.min(1, st.w + dt / 0.12); }
# # # # #     else { st.w = Math.max(0, st.w - dt / 0.12); }
# # # # #     if (st.last && st.w > 0) applyHand(side, H && opts.fingers ? H : st.last, st.w);
# # # # #   }
# # # # #   rootObj.updateMatrixWorld(true);
# # # # # }
# # # # # const RETARGET = { bones, restQ, setupModel, applyFrame, sampleFrame, handState, opts, resetPose };
# # # # # // ==== RETARGET END ====

# # # # # (function main() {
# # # # #   if (typeof THREE === "undefined" || !THREE.GLTFLoader || !THREE.OrbitControls) {
# # # # #     fail("Không tải được three.js từ CDN. Hãy kiểm tra kết nối Internet rồi mở lại trang.");
# # # # #     return;
# # # # #   }

# # # # #   // ---------- scene ----------
# # # # #   const stage = $("stage");
# # # # #   const renderer = new THREE.WebGLRenderer({ antialias: true });
# # # # #   renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
# # # # #   renderer.outputEncoding = THREE.sRGBEncoding;
# # # # #   renderer.shadowMap.enabled = true;
# # # # #   stage.appendChild(renderer.domElement);

# # # # #   const scene = new THREE.Scene();
# # # # #   scene.background = new THREE.Color(0x0b1220);
# # # # #   const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
# # # # #   camera.position.set(0, 1.5, 2.7);
# # # # #   const controls = new THREE.OrbitControls(camera, renderer.domElement);
# # # # #   controls.target.set(0, 1.3, 0);
# # # # #   controls.update();

# # # # #   scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 0.9));
# # # # #   const sun = new THREE.DirectionalLight(0xffffff, 0.8);
# # # # #   sun.position.set(2, 4, 3);
# # # # #   sun.castShadow = true;
# # # # #   scene.add(sun);
# # # # #   const ground = new THREE.Mesh(new THREE.CircleGeometry(3, 48),
# # # # #     new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 1 }));
# # # # #   ground.rotation.x = -Math.PI / 2;
# # # # #   ground.receiveShadow = true;
# # # # #   scene.add(ground);
# # # # #   scene.add(new THREE.GridHelper(6, 24, 0x334155, 0x1f2937));

# # # # #   function resize() {
# # # # #     const w = window.innerWidth, h = window.innerHeight;
# # # # #     renderer.setSize(w, h);
# # # # #     camera.aspect = w / h;
# # # # #     camera.updateProjectionMatrix();
# # # # #   }
# # # # #   window.addEventListener("resize", resize);
# # # # #   resize();

# # # # #   // ---------- UI ----------
# # # # #   const seek = $("seek");
# # # # #   seek.max = Math.max(1, N - 1);
# # # # #   const chips = $("chips");
# # # # #   const segEls = DATA.segments.map((s, i) => {
# # # # #     const el = document.createElement("span");
# # # # #     el.className = "chip";
# # # # #     el.textContent = s.gloss;
# # # # #     el.title = s.video;
# # # # #     el.onclick = () => { tFrame = s.s; };
# # # # #     chips.appendChild(el);
# # # # #     return el;
# # # # #   });

# # # # #   let playing = true, tFrame = 0, recording = null;
# # # # #   const setPlayLabel = () => { $("play").textContent = playing ? "Tạm dừng" : "Phát"; };
# # # # #   $("play").onclick = () => { playing = !playing; if (playing && tFrame >= N - 1) tFrame = 0; setPlayLabel(); };
# # # # #   $("restart").onclick = () => { tFrame = 0; playing = true; setPlayLabel(); };
# # # # #   seek.oninput = () => { tFrame = +seek.value; };
# # # # #   $("speed").onchange = (e) => { opts.speed = +e.target.value; };
# # # # #   for (const [id, key] of [["o_loop","loop"],["o_fingers","fingers"],["o_legs","legs"],
# # # # #                            ["o_mirror","mirror"],["o_flipz","flipZ"],["o_swap","swapHands"]]) {
# # # # #     $(id).onchange = (e) => { opts[key] = e.target.checked; };
# # # # #   }
# # # # #   window.addEventListener("keydown", (e) => { if (e.code === "Space") { e.preventDefault(); $("play").click(); } });

# # # # #   $("rec").onclick = () => {
# # # # #     if (!window.MediaRecorder) { alert("Trình duyệt không hỗ trợ ghi video. Hãy dùng Chrome hoặc Edge."); return; }
# # # # #     if (recording) return;
# # # # #     const stream = renderer.domElement.captureStream(30);
# # # # #     const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]
# # # # #       .find((m) => MediaRecorder.isTypeSupported(m));
# # # # #     const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 6000000 });
# # # # #     const chunks = [];
# # # # #     rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
# # # # #     rec.onstop = () => {
# # # # #       const a = document.createElement("a");
# # # # #       a.href = URL.createObjectURL(new Blob(chunks, { type: "video/webm" }));
# # # # #       a.download = "sign_avatar.webm";
# # # # #       a.click();
# # # # #       recording = null;
# # # # #       $("rec").textContent = "Ghi video (.webm)";
# # # # #     };
# # # # #     recording = { rec, prevLoop: opts.loop };
# # # # #     opts.loop = false;
# # # # #     tFrame = 0; playing = true; setPlayLabel();
# # # # #     rec.start();
# # # # #     $("rec").textContent = "Đang ghi...";
# # # # #   };

# # # # #   // ---------- model ----------
# # # # #   let loaded = false;
# # # # #   try {
# # # # #     const bin = atob(GLB_B64);
# # # # #     const buf = new Uint8Array(bin.length);
# # # # #     for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
# # # # #     new THREE.GLTFLoader().parse(buf.buffer, "", (gltf) => {
# # # # #       const model = gltf.scene;
# # # # #       let box = new THREE.Box3().setFromObject(model);
# # # # #       model.scale.setScalar(1.75 / Math.max(0.01, box.max.y - box.min.y));
# # # # #       box = new THREE.Box3().setFromObject(model);
# # # # #       model.position.y -= box.min.y;
# # # # #       model.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
# # # # #       scene.add(model);
# # # # #       const info = setupModel(model);
# # # # #       loaded = true;
# # # # #       $("status").textContent = "Xương: " + info.bones + " | xương ngón tay: " + info.fingerBases +
# # # # #         "/10 | " + N + " khung hình, " + FPS + " fps | các từ: " + DATA.segments.map((s) => s.gloss).join(" → ");
# # # # #       if (info.fingerBases < 10) $("status").textContent += "  (mô hình thiếu xương ngón tay: ngón sẽ không cử động)";
# # # # #     }, (err) => { fail("Không đọc được mô hình Xbot: " + (err && err.message ? err.message : err)); });
# # # # #   } catch (e) { fail("Lỗi nạp mô hình: " + e); }

# # # # #   // ---------- loop ----------
# # # # #   let last = performance.now();
# # # # #   function tick(now) {
# # # # #     const dt = Math.min(0.1, (now - last) / 1000);
# # # # #     last = now;
# # # # #     if (playing) {
# # # # #       tFrame += dt * FPS * opts.speed;
# # # # #       if (tFrame >= N - 1) {
# # # # #         if (recording) {
# # # # #           tFrame = N - 1; playing = false; setPlayLabel();
# # # # #           opts.loop = recording.prevLoop;
# # # # #           const r = recording.rec; setTimeout(() => r.state !== "inactive" && r.stop(), 250);
# # # # #         } else if (opts.loop) tFrame = 0;
# # # # #         else { tFrame = N - 1; playing = false; setPlayLabel(); }
# # # # #       }
# # # # #     }
# # # # #     if (loaded) applyFrame(tFrame, dt);
# # # # #     const fi = Math.floor(tFrame);
# # # # #     const idx = DATA.segments.findIndex((s) => fi >= s.s && fi < s.e);
# # # # #     const cur = idx >= 0 ? idx : DATA.segments.length - 1;
# # # # #     $("caption").textContent = DATA.segments[cur] ? DATA.segments[cur].gloss : "";
# # # # #     segEls.forEach((el, i) => el.classList.toggle("on", i === cur));
# # # # #     seek.value = fi;
# # # # #     $("time").textContent = (tFrame / FPS).toFixed(1) + " / " + (N / FPS).toFixed(1) + " s";
# # # # #     controls.update();
# # # # #     renderer.render(scene, camera);
# # # # #     requestAnimationFrame(tick);
# # # # #   }
# # # # #   requestAnimationFrame(tick);
# # # # # })();
# # # # # </script>
# # # # # </body>
# # # # # </html>
# # # # # '''


# # # # # def write_html(timeline, xbot_path, out_path, title):
# # # # #     glb = Path(xbot_path).read_bytes()
# # # # #     data_json = json.dumps(timeline, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
# # # # #     html = (HTML_TEMPLATE
# # # # #             .replace("__TITLE__", title.replace("<", "&lt;"))
# # # # #             .replace("__DATA_JSON__", data_json)
# # # # #             .replace("__GLB_B64__", base64.b64encode(glb).decode("ascii")))
# # # # #     out = Path(out_path)
# # # # #     out.parent.mkdir(parents=True, exist_ok=True)
# # # # #     out.write_text(html, encoding="utf-8")
# # # # #     return out


# # # # # # =====================================================================
# # # # # # 7. Command line
# # # # # # =====================================================================
# # # # # def build_parser():
# # # # #     p = argparse.ArgumentParser(
# # # # #         description="Chuỗi gloss -> avatar Xbot chuyển động liên tục (file HTML độc lập).")
# # # # #     g = p.add_argument_group("đầu vào")
# # # # #     g.add_argument("--glosses", nargs="+", help='Danh sách gloss, ví dụ: --glosses "bạn" "đi học" "có không"')
# # # # #     g.add_argument("--sentence", help='Các gloss ngăn cách bằng dấu |, ví dụ: "bạn | đi học | có không"')
# # # # #     g.add_argument("--glosses-file", help="File .json (list) hoặc .txt (mỗi dòng 1 gloss)")
# # # # #     g = p.add_argument_group("đường dẫn")
# # # # #     g.add_argument("--labels", help="File ánh xạ VIDEO/LABEL (csv, tsv, txt, xlsx, json)")
# # # # #     g.add_argument("--videos", default=DEFAULT_VIDEOS, help="Thư mục chứa các video của dataset")
# # # # #     g.add_argument("--xbot", default=DEFAULT_XBOT, help="File Xbot.glb")
# # # # #     g.add_argument("--cache", default=DEFAULT_CACHE, help="Thư mục lưu tọa độ đã tính (.npz)")
# # # # #     g.add_argument("--out", default=DEFAULT_OUT, help="File HTML đầu ra")
# # # # #     g = p.add_argument_group("chọn video")
# # # # #     g.add_argument("--region", default="B,T,N", help="Thứ tự ưu tiên giọng vùng: B=Bắc, T=Trung, N=Nam")
# # # # #     g.add_argument("--search", help="Tìm nhãn chứa chuỗi này (không cần dấu) rồi thoát")
# # # # #     g.add_argument("--precompute-all", action="store_true",
# # # # #                    help="Tính trước tọa độ cho mọi gloss (lâu, chạy một lần)")
# # # # #     g = p.add_argument_group("chuyển động")
# # # # #     g.add_argument("--fps", type=float, default=30.0)
# # # # #     g.add_argument("--transition", type=float, default=0.25, help="Giây chuyển tiếp giữa 2 từ")
# # # # #     g.add_argument("--hold", type=float, default=0.2, help="Giây giữ tư thế đầu/cuối")
# # # # #     g.add_argument("--smooth-body", type=float, default=1.5, help="Độ mượt thân (khung hình, 0 = tắt)")
# # # # #     g.add_argument("--smooth-hands", type=float, default=1.0, help="Độ mượt ngón tay (0 = tắt)")
# # # # #     g.add_argument("--hand-gap", type=int, default=6, help="Nội suy khi mất tay tối đa N khung")
# # # # #     g.add_argument("--no-trim", action="store_true", help="Không cắt đoạn tay buông ở đầu/cuối video")
# # # # #     g.add_argument("--rest-threshold", type=float, default=0.10,
# # # # #                    help="Cổ tay phải cao hơn hông bao nhiêu mét để tính là đang ký")
# # # # #     g.add_argument("--complexity", type=int, default=1, choices=[0, 1, 2],
# # # # #                    help="Độ chính xác MediaPipe Pose (2 = chính xác nhất, chậm nhất)")
# # # # #     p.add_argument("--open", action="store_true", help="Mở file HTML sau khi tạo")
# # # # #     return p


# # # # # def get_glosses(args):
# # # # #     if args.glosses:
# # # # #         return [g for g in args.glosses if g.strip()]
# # # # #     if args.sentence:
# # # # #         return [g.strip() for g in args.sentence.split("|") if g.strip()]
# # # # #     if args.glosses_file:
# # # # #         txt = read_text_auto(args.glosses_file)
# # # # #         if args.glosses_file.lower().endswith(".json"):
# # # # #             return [str(g) for g in json.loads(txt)]
# # # # #         return [l.strip() for l in txt.splitlines() if l.strip()]
# # # # #     return []


# # # # # def main(argv=None, detector_factory=None):
# # # # #     args = build_parser().parse_args(argv)
# # # # #     videos_dir = Path(args.videos)

# # # # #     labels = args.labels or find_labels_file(videos_dir)
# # # # #     if not labels or not Path(labels).exists():
# # # # #         print("Không tìm thấy file nhãn. Hãy chỉ rõ bằng --labels \"đường\\dẫn\\file.csv\"")
# # # # #         return 2
# # # # #     records = load_records(labels)
# # # # #     index = GlossIndex(records, args.region.split(","))
# # # # #     print(f"Đã đọc {len(records)} video / {len(index.by_key)} khóa tra cứu từ: {labels}")

# # # # #     if args.search:
# # # # #         hits = index.search(args.search)
# # # # #         print(f'\nCác nhãn chứa "{args.search}" ({len(hits)} kết quả đầu):')
# # # # #         for r in hits:
# # # # #             print(f"  {r['video']:<14} {r['label']}")
# # # # #         return 0

# # # # #     if detector_factory is None:
# # # # #         detector_factory = lambda: MediaPipeDetector(args.complexity)

# # # # #     if args.precompute_all:
# # # # #         picks = {}
# # # # #         for rec in index.recs:
# # # # #             key = norm(rec["label"])
# # # # #             if key not in picks:
# # # # #                 picks[key] = index.choose(index.lookup(rec["label"]))[0]
# # # # #         todo = sorted(picks.values(), key=lambda r: natural_key(r["stem"]))
# # # # #         print(f"Tính trước {len(todo)} video (mỗi gloss một video)...")
# # # # #         for i, rec in enumerate(todo, 1):
# # # # #             vp = videos_dir / rec["video"]
# # # # #             try:
# # # # #                 _, hit = get_clip_data(vp, args.cache, detector_factory)
# # # # #                 print(f"[{i}/{len(todo)}] {rec['video']} {'(đã có)' if hit else 'xong'}")
# # # # #             except Exception as e:
# # # # #                 print(f"[{i}/{len(todo)}] {rec['video']} LỖI: {e}")
# # # # #         return 0

# # # # #     glosses = get_glosses(args)
# # # # #     if not glosses:
# # # # #         raw = input('Nhập các gloss, ngăn cách bằng dấu | (ví dụ: bạn | đi học | có không): ')
# # # # #         glosses = [g.strip() for g in raw.split("|") if g.strip()]
# # # # #     if not glosses:
# # # # #         print("Chưa có gloss nào.")
# # # # #         return 2

# # # # #     # ---- gloss -> video ----
# # # # #     picks, problems = [], []
# # # # #     for g in glosses:
# # # # #         found, missing = index.resolve_one(g)
# # # # #         picks += found
# # # # #         for w in missing:
# # # # #             sug = index.suggest(w)
# # # # #             problems.append(f'Không có gloss "{w}"' + (f" (gần giống: {', '.join(sug)})" if sug else ""))
# # # # #     print("\nChuỗi gloss -> video:")
# # # # #     for g, rec, note in picks:
# # # # #         print(f"  {g:<18} -> {rec['video']:<14} [{rec['label']}]" + (f"  ({note})" if note else ""))
# # # # #     for p in problems:
# # # # #         print("  CẢNH BÁO:", p)
# # # # #     if not picks:
# # # # #         return 1

# # # # #     # ---- landmarks (cached) ----
# # # # #     clips = []
# # # # #     for i, (g, rec, _) in enumerate(picks, 1):
# # # # #         vp = videos_dir / rec["video"]
# # # # #         cache_file = Path(args.cache) / (rec["stem"] + ".npz")
# # # # #         if not vp.exists() and not cache_file.exists():
# # # # #             print(f"  CẢNH BÁO: không thấy video {vp}")
# # # # #             continue
# # # # #         try:
# # # # #             raw, hit = get_clip_data(vp, args.cache, detector_factory)
# # # # #         except Exception as e:
# # # # #             print(f"  CẢNH BÁO: lỗi với {rec['video']}: {e}")
# # # # #             continue
# # # # #         clip, ok = process_clip(raw, args.fps, args)
# # # # #         if clip is None:
# # # # #             print(f"  CẢNH BÁO: {rec['video']} chỉ nhận diện được {ok:.0%} khung hình, bỏ qua")
# # # # #             continue
# # # # #         hands_ok = [float((~np.isnan(clip[k].reshape(len(clip[k]), -1)).any(axis=1)).mean())
# # # # #                     for k in ("lh", "rh")]
# # # # #         print(f"  [{i}/{len(picks)}] {rec['video']}: {len(clip['body'])} khung ({len(clip['body'])/args.fps:.1f}s), "
# # # # #               f"có tay trái {hands_ok[0]:.0%} / tay phải {hands_ok[1]:.0%}" + ("" if hit else "  (vừa tính xong, đã lưu cache)"))
# # # # #         clip.update({"gloss": g, "video": rec["video"]})
# # # # #         clips.append(clip)
# # # # #     if not clips:
# # # # #         print("Không có video nào dùng được.")
# # # # #         return 1

# # # # #     # ---- one continuous timeline -> html ----
# # # # #     timeline = assemble(clips, args.fps, args.transition, args.hold)
# # # # #     if not Path(args.xbot).exists():
# # # # #         print(f"Không thấy file Xbot: {args.xbot}  (dùng --xbot để chỉ đường dẫn)")
# # # # #         return 2
# # # # #     out = write_html(timeline, args.xbot, args.out, "Avatar: " + " | ".join(c["gloss"] for c in clips))
# # # # #     print(f"\nXong: {timeline['n']} khung hình = {timeline['n']/args.fps:.1f} giây")
# # # # #     print(f"Mở file này (bấm đúp): {out.resolve()}")
# # # # #     if args.open:
# # # # #         webbrowser.open(out.resolve().as_uri())
# # # # #     return 0


# # # # # if __name__ == "__main__":
# # # # #     sys.exit(main())

























# # # # #!/usr/bin/env python3
# # # # # -*- coding: utf-8 -*-
# # # # """
# # # # sign_to_avatar.py
# # # # =================
# # # # Gloss list  ->  videos of the dataset  ->  3D landmarks (cached .npz)
# # # #             ->  ONE continuous animation of the Xbot avatar (standalone .html).

# # # # Example:
# # # #     python sign_to_avatar.py --glosses "bạn" "đi học" "có không"
# # # #     python sign_to_avatar.py --sentence "bạn | đi học | có không" --open
# # # #     python sign_to_avatar.py --search "địa chỉ"

# # # # The output .html is a single file: double-click it, no server / localhost needed.
# # # # (It only needs Internet once per open, to load three.js from a CDN.)
# # # # """
# # # # import argparse
# # # # import base64
# # # # import csv
# # # # import difflib
# # # # import io
# # # # import json
# # # # import os
# # # # import re
# # # # import sys
# # # # import unicodedata
# # # # import webbrowser
# # # # from pathlib import Path

# # # # import numpy as np

# # # # # =====================================================================
# # # # # DEFAULTS (edit these once, then you never need to type the paths)
# # # # # =====================================================================
# # # # DEFAULT_VIDEOS = r"C:\Users\ADMIN\qh\vsl-vietnamese-sign-languages\versions\5\Dataset\Videos"
# # # # DEFAULT_XBOT = os.path.join("frontend_dis", "models", "Xbot.glb")
# # # # DEFAULT_CACHE = "landmark_cache"
# # # # DEFAULT_OUT = os.path.join("output", "sentence.html")

# # # # CACHE_VERSION = 1
# # # # VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")

# # # # BODY_NAMES = [
# # # #     "Hips", "Spine1", "Spine2", "Neck", "Head",
# # # #     "LeftArm", "LeftForeArm", "LeftHand",
# # # #     "RightArm", "RightForeArm", "RightHand",
# # # #     "LeftUpLeg", "LeftLeg", "LeftFoot",
# # # #     "RightUpLeg", "RightLeg", "RightFoot",
# # # # ]

# # # # try:  # make Vietnamese text safe to print on any console
# # # #     sys.stdout.reconfigure(errors="replace")
# # # #     sys.stderr.reconfigure(errors="replace")
# # # # except Exception:
# # # #     pass


# # # # # =====================================================================
# # # # # 1. Text helpers
# # # # # =====================================================================
# # # # def norm(s):
# # # #     """NFC + lower-case + collapsed spaces."""
# # # #     return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s)).strip().lower())


# # # # def strip_accents(s):
# # # #     s = norm(s).replace("đ", "d")
# # # #     s = unicodedata.normalize("NFD", s)
# # # #     return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# # # # def without_parens(s):
# # # #     return norm(re.sub(r"\([^)]*\)", " ", str(s)))


# # # # def natural_key(s):
# # # #     return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


# # # # VIDEO_RE = re.compile(r"^(?P<base>.*\d)(?P<reg>[NTBntb])?$")


# # # # def parse_video(name):
# # # #     """'D0001N.mp4' -> ('D0001', 'N');  'D0002.mp4' -> ('D0002', '')."""
# # # #     stem = Path(str(name).strip()).stem
# # # #     m = VIDEO_RE.match(stem)
# # # #     if m:
# # # #         return m.group("base"), (m.group("reg") or "").upper()
# # # #     return stem, ""


# # # # def label_keys(label):
# # # #     """All the lookup keys under which a dataset label can be found."""
# # # #     plain = without_parens(label)
# # # #     parts = {norm(label), plain}
# # # #     for p in re.split(r"\s*[;/,]\s*", plain):
# # # #         if p.strip():
# # # #             parts.add(norm(p))
# # # #     keys = set()
# # # #     for p in parts:
# # # #         if p:
# # # #             keys.add(p)
# # # #             keys.add(strip_accents(p))
# # # #     return keys


# # # # # =====================================================================
# # # # # 2. Reading the label file (csv / tsv / txt / xlsx / json)
# # # # # =====================================================================
# # # # def read_text_auto(path):
# # # #     raw = Path(path).read_bytes()
# # # #     if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:200]:
# # # #         return raw.decode("utf-16", errors="replace")
# # # #     try:
# # # #         return raw.decode("utf-8-sig")
# # # #     except UnicodeDecodeError:
# # # #         return raw.decode("cp1258", errors="replace")


# # # # def _pick_columns(header):
# # # #     h = [norm(c) for c in header]
# # # #     vi = next((i for i, c in enumerate(h) if c in ("video", "file", "filename", "name")), None)
# # # #     li = next((i for i, c in enumerate(h) if c in ("label", "gloss", "nhan", "nhãn", "text")), None)
# # # #     return vi, li


# # # # def load_records(path):
# # # #     """Return [(video_name, label), ...] from any supported file type."""
# # # #     path = str(path)
# # # #     ext = Path(path).suffix.lower()

# # # #     if ext == ".json":
# # # #         data = json.loads(read_text_auto(path))
# # # #         recs = []
# # # #         if isinstance(data, dict):
# # # #             for gloss, vids in data.items():
# # # #                 if isinstance(vids, (str, dict)):
# # # #                     vids = [vids]
# # # #                 for v in vids:
# # # #                     recs.append((v["video"] if isinstance(v, dict) else v, gloss))
# # # #         else:
# # # #             for item in data:
# # # #                 if isinstance(item, dict):
# # # #                     low = {norm(k): v for k, v in item.items()}
# # # #                     recs.append((low.get("video") or low.get("file"),
# # # #                                  low.get("label") or low.get("gloss")))
# # # #                 else:
# # # #                     recs.append((item[0], item[1]))
# # # #         return [(str(v), str(l)) for v, l in recs if v and l]

# # # #     if ext in (".xlsx", ".xls", ".xlsm"):
# # # #         import pandas as pd  # needs openpyxl for .xlsx
# # # #         df = pd.read_excel(path, dtype=str).fillna("")
# # # #         rows = [list(df.columns)] + df.values.tolist()
# # # #     else:
# # # #         text = read_text_auto(path)
# # # #         first = text.splitlines()[0] if text else ""
# # # #         delim = max(["\t", ",", ";"], key=first.count)
# # # #         rows = list(csv.reader(io.StringIO(text), delimiter=delim))

# # # #     rows = [r for r in rows if r and any(str(c).strip() for c in r)]
# # # #     if not rows:
# # # #         return []
# # # #     vi, li = _pick_columns(rows[0])
# # # #     start = 1
# # # #     if vi is None or li is None:  # no header: first two columns
# # # #         vi, li = 0, 1
# # # #         start = 0 if Path(str(rows[0][0])).suffix.lower() in VIDEO_EXTS else 1
# # # #     out = []
# # # #     for r in rows[start:]:
# # # #         if len(r) > max(vi, li) and str(r[vi]).strip() and str(r[li]).strip():
# # # #             out.append((str(r[vi]).strip(), str(r[li]).strip()))
# # # #     return out


# # # # def find_labels_file(videos_dir):
# # # #     vd = Path(videos_dir)
# # # #     exts = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json")
# # # #     cands = []
# # # #     for d in (vd, vd.parent, vd.parent.parent):
# # # #         if d.is_dir():
# # # #             cands += [p for p in d.iterdir() if p.suffix.lower() in exts]
# # # #     hits = [p for p in cands if "label" in p.name.lower()]
# # # #     if len(hits) >= 1:
# # # #         return str(sorted(hits, key=lambda p: len(str(p)))[0])
# # # #     return None


# # # # # =====================================================================
# # # # # 3. Gloss index: label -> video
# # # # # =====================================================================
# # # # class GlossIndex:
# # # #     def __init__(self, records, region_pref=("B", "T", "N")):
# # # #         self.region_pref = [r.upper() for r in region_pref]
# # # #         self.recs = []
# # # #         self.by_key = {}
# # # #         self.by_stem = {}
# # # #         for video, label in records:
# # # #             base, reg = parse_video(video)
# # # #             rec = {"video": Path(video).name, "stem": Path(video).stem,
# # # #                    "base": base, "region": reg, "label": label}
# # # #             self.recs.append(rec)
# # # #             self.by_stem[norm(rec["stem"])] = rec
# # # #             for k in label_keys(label):
# # # #                 self.by_key.setdefault(k, []).append(rec)

# # # #     def lookup(self, text):
# # # #         for v in (norm(text), without_parens(text),
# # # #                   strip_accents(text), strip_accents(without_parens(text))):
# # # #             if v and v in self.by_key:
# # # #                 return self.by_key[v]
# # # #         return []

# # # #     def choose(self, recs):
# # # #         """One video for a gloss: first sign (lowest id), preferred region."""
# # # #         groups = {}
# # # #         for r in recs:
# # # #             groups.setdefault(r["base"], []).append(r)
# # # #         bases = sorted(groups, key=natural_key)
# # # #         group = groups[bases[0]]
# # # #         group.sort(key=lambda r: (self.region_pref.index(r["region"])
# # # #                                   if r["region"] in self.region_pref else 99,
# # # #                                   natural_key(r["stem"])))
# # # #         return group[0], len(bases) - 1

# # # #     def resolve_one(self, gloss):
# # # #         """Return (list of (gloss_text, rec, note), list of missing words)."""
# # # #         g = str(gloss).strip()
# # # #         if not g:
# # # #             return [], []
# # # #         # a video id typed directly, e.g. "D0001T"
# # # #         rec = self.by_stem.get(norm(Path(g).stem))
# # # #         if rec is not None and re.fullmatch(r"[dD]\d+[NTBntb]?(\.\w+)?", g):
# # # #             return [(g, rec, "")], []

# # # #         recs = self.lookup(g)
# # # #         if recs:
# # # #             rec, extra = self.choose(recs)
# # # #             note = f"còn {extra} cách ký khác" if extra > 0 else ""
# # # #             return [(g, rec, note)], []

# # # #         # not a known gloss: split into the longest known pieces
# # # #         words = norm(g).split()
# # # #         found, missing, i = [], [], 0
# # # #         while i < len(words):
# # # #             for j in range(len(words), i, -1):
# # # #                 phrase = " ".join(words[i:j])
# # # #                 recs = self.lookup(phrase)
# # # #                 if recs:
# # # #                     rec, extra = self.choose(recs)
# # # #                     found.append((phrase, rec, f'tách từ "{g}"'))
# # # #                     i = j
# # # #                     break
# # # #             else:
# # # #                 missing.append(words[i])
# # # #                 i += 1
# # # #         if not found:
# # # #             return [], [g]
# # # #         return found, missing

# # # #     def suggest(self, text, n=4):
# # # #         pool = {}
# # # #         for k, recs in self.by_key.items():
# # # #             if strip_accents(k) == k:
# # # #                 pool[k] = recs[0]["label"]
# # # #         close = difflib.get_close_matches(strip_accents(text), list(pool), n=n, cutoff=0.6)
# # # #         return [pool[c] for c in close]

# # # #     def search(self, text, limit=30):
# # # #         t = strip_accents(text)
# # # #         hits = [r for r in self.recs if t in strip_accents(r["label"])]
# # # #         return sorted(hits, key=lambda r: natural_key(r["stem"]))[:limit]


# # # # # =====================================================================
# # # # # 4. Landmark extraction (MediaPipe) + cache
# # # # # =====================================================================
# # # # def assign_hands(hands, left_wrist, right_wrist):
# # # #     """
# # # #     hands: [(image_wrist_xy, world_21x3, label)], wrists in normalised image coords.
# # # #     Decide which detected hand is the person's LEFT / RIGHT by comparing with the
# # # #     body-pose wrists (more reliable than the handedness label for un-mirrored video).
# # # #     """
# # # #     res = {"L": None, "R": None}
# # # #     if not hands:
# # # #         return res

# # # #     def d(a, b):
# # # #         return float(np.hypot(a[0] - b[0], a[1] - b[1]))

# # # #     if left_wrist is not None and right_wrist is not None:
# # # #         if len(hands) == 1:
# # # #             h = hands[0]
# # # #             res["L" if d(h[0], left_wrist) <= d(h[0], right_wrist) else "R"] = h[1]
# # # #         else:
# # # #             h0, h1 = hands[0], hands[1]
# # # #             a = d(h0[0], left_wrist) + d(h1[0], right_wrist)
# # # #             b = d(h0[0], right_wrist) + d(h1[0], left_wrist)
# # # #             if a <= b:
# # # #                 res["L"], res["R"] = h0[1], h1[1]
# # # #             else:
# # # #                 res["L"], res["R"] = h1[1], h0[1]
# # # #     else:  # no body wrists: use the label (MediaPipe assumes a mirrored image -> swap)
# # # #         for h in hands:
# # # #             res["R" if h[2] == "Left" else "L"] = h[1]
# # # #     return res


# # # # class MediaPipeDetector:
# # # #     """Pose (33 world landmarks) + Hands (21 world landmarks each), one video at a time."""

# # # #     def __init__(self, complexity=1):
# # # #         import mediapipe as mp
# # # #         self.pose = mp.solutions.pose.Pose(
# # # #             static_image_mode=False, model_complexity=complexity, smooth_landmarks=True,
# # # #             min_detection_confidence=0.5, min_tracking_confidence=0.5)
# # # #         self.hands = mp.solutions.hands.Hands(
# # # #             static_image_mode=False, max_num_hands=2, model_complexity=1,
# # # #             min_detection_confidence=0.5, min_tracking_confidence=0.5)

# # # #     def __enter__(self):
# # # #         return self

# # # #     def __exit__(self, *a):
# # # #         self.pose.close()
# # # #         self.hands.close()
# # # #         return False

# # # #     def process(self, rgb):
# # # #         pr = self.pose.process(rgb)
# # # #         hr = self.hands.process(rgb)
# # # #         pose_world = left_w = right_w = None
# # # #         if pr.pose_world_landmarks:
# # # #             pose_world = np.array([[l.x, l.y, l.z] for l in pr.pose_world_landmarks.landmark],
# # # #                                   dtype=np.float32)
# # # #         if pr.pose_landmarks:
# # # #             lm = pr.pose_landmarks.landmark
# # # #             left_w, right_w = (lm[15].x, lm[15].y), (lm[16].x, lm[16].y)
# # # #         hands = []
# # # #         if hr.multi_hand_world_landmarks and hr.multi_hand_landmarks:
# # # #             for wl, il, hd in zip(hr.multi_hand_world_landmarks,
# # # #                                   hr.multi_hand_landmarks, hr.multi_handedness):
# # # #                 world = np.array([[l.x, l.y, l.z] for l in wl.landmark], dtype=np.float32)
# # # #                 hands.append(((il.landmark[0].x, il.landmark[0].y), world,
# # # #                               hd.classification[0].label))
# # # #         return {"pose": pose_world, "left_wrist": left_w, "right_wrist": right_w, "hands": hands}


# # # # def extract_video(video_path, detector_factory, target_width=640):
# # # #     """Run the detector on every frame. Returns dict of arrays (NaN = not detected)."""
# # # #     import cv2
# # # #     cap = cv2.VideoCapture(str(video_path))
# # # #     if not cap.isOpened():
# # # #         raise IOError(f"Không mở được video: {video_path}")
# # # #     fps = cap.get(cv2.CAP_PROP_FPS)
# # # #     if not fps or fps != fps or fps <= 1:
# # # #         fps = 30.0
# # # #     pose_l, lh_l, rh_l = [], [], []
# # # #     nan_pose = np.full((33, 3), np.nan, np.float32)
# # # #     nan_hand = np.full((21, 3), np.nan, np.float32)
# # # #     with detector_factory() as det:
# # # #         while True:
# # # #             ok, frame = cap.read()
# # # #             if not ok:
# # # #                 break
# # # #             h, w = frame.shape[:2]
# # # #             if w != target_width and w > 0:
# # # #                 frame = cv2.resize(frame, (target_width, int(h * target_width / w)))
# # # #             rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
# # # #             r = det.process(rgb)
# # # #             pose_l.append(r["pose"] if r["pose"] is not None else nan_pose)
# # # #             a = assign_hands(r["hands"], r["left_wrist"], r["right_wrist"])
# # # #             lh_l.append(a["L"] if a["L"] is not None else nan_hand)
# # # #             rh_l.append(a["R"] if a["R"] is not None else nan_hand)
# # # #     cap.release()
# # # #     if not pose_l:
# # # #         raise IOError(f"Video rỗng: {video_path}")
# # # #     return {"pose": np.stack(pose_l).astype(np.float32),
# # # #             "lhand": np.stack(lh_l).astype(np.float32),
# # # #             "rhand": np.stack(rh_l).astype(np.float32),
# # # #             "fps": float(fps)}


# # # # def get_clip_data(video_path, cache_dir, detector_factory):
# # # #     cache_path = Path(cache_dir) / (Path(video_path).stem + ".npz")
# # # #     if cache_path.exists():
# # # #         try:
# # # #             d = np.load(cache_path)
# # # #             if int(d["version"]) == CACHE_VERSION:
# # # #                 data = {k: d[k] for k in ("pose", "lhand", "rhand")}
# # # #                 data["fps"] = float(d["fps"])
# # # #                 return data, True
# # # #         except Exception:
# # # #             pass
# # # #     data = extract_video(video_path, detector_factory)
# # # #     cache_path.parent.mkdir(parents=True, exist_ok=True)
# # # #     np.savez_compressed(cache_path, pose=data["pose"], lhand=data["lhand"],
# # # #                         rhand=data["rhand"], fps=data["fps"], version=CACHE_VERSION)
# # # #     return data, False


# # # # # =====================================================================
# # # # # 5. Clean-up: resample, fill gaps, smooth, trim, join
# # # # # =====================================================================
# # # # def resample(arr, src_fps, dst_fps):
# # # #     T = len(arr)
# # # #     if T < 2 or abs(src_fps - dst_fps) < 1e-3:
# # # #         return arr
# # # #     new_T = max(2, int(round((T - 1) * dst_fps / src_fps)) + 1)
# # # #     t = np.linspace(0, T - 1, new_T)
# # # #     i0 = np.floor(t).astype(int)
# # # #     i1 = np.minimum(i0 + 1, T - 1)
# # # #     a = (t - i0).reshape((-1,) + (1,) * (arr.ndim - 1))
# # # #     return arr[i0] * (1 - a) + arr[i1] * a   # NaN stays NaN if either neighbour is missing


# # # # def fill_gaps(arr, max_gap, hold_edges):
# # # #     T = len(arr)
# # # #     flat = arr.reshape(T, -1).astype(np.float64)
# # # #     valid = ~np.isnan(flat).any(axis=1)
# # # #     idx = np.where(valid)[0]
# # # #     if len(idx) == 0:
# # # #         return arr
# # # #     out = flat.copy()
# # # #     for a, b in zip(idx[:-1], idx[1:]):
# # # #         gap = b - a - 1
# # # #         if 0 < gap <= max_gap:
# # # #             for k in range(1, gap + 1):
# # # #                 w = k / (gap + 1)
# # # #                 out[a + k] = flat[a] * (1 - w) + flat[b] * w
# # # #     if hold_edges:
# # # #         out[:idx[0]] = flat[idx[0]]
# # # #         out[idx[-1] + 1:] = flat[idx[-1]]
# # # #     return out.reshape(arr.shape).astype(np.float32)


# # # # def hold_last_valid(arr):
# # # #     """Replace remaining NaN frames by the previous (or next) valid frame."""
# # # #     T = len(arr)
# # # #     flat = arr.reshape(T, -1).copy()
# # # #     valid = ~np.isnan(flat).any(axis=1)
# # # #     if not valid.any():
# # # #         return arr
# # # #     last = None
# # # #     for i in range(T):
# # # #         if valid[i]:
# # # #             last = flat[i].copy()
# # # #         elif last is not None:
# # # #             flat[i] = last
# # # #     first = np.where(valid)[0][0]
# # # #     flat[:first] = flat[first]
# # # #     return flat.reshape(arr.shape)


# # # # def smooth_nan(arr, sigma):
# # # #     """Gaussian smoothing along time; invalid (NaN) frames stay invalid."""
# # # #     T = len(arr)
# # # #     if sigma <= 0 or T < 2:
# # # #         return arr
# # # #     flat = arr.reshape(T, -1).astype(np.float64)
# # # #     valid = ~np.isnan(flat).any(axis=1)
# # # #     if not valid.any():
# # # #         return arr
# # # #     i = np.arange(T)
# # # #     W = np.exp(-0.5 * ((i[:, None] - i[None, :]) / sigma) ** 2) * valid[None, :]
# # # #     num = W @ np.where(valid[:, None], flat, 0.0)
# # # #     den = np.maximum(W.sum(axis=1, keepdims=True), 1e-9)
# # # #     out = num / den
# # # #     out[~valid] = np.nan
# # # #     return out.reshape(arr.shape).astype(np.float32)


# # # # def body_keypoints(pose):
# # # #     """(T,33,3) MediaPipe pose -> (T,17,3) avatar keypoints (order = BODY_NAMES)."""
# # # #     hips = (pose[:, 23] + pose[:, 24]) / 2
# # # #     neck = (pose[:, 11] + pose[:, 12]) / 2
# # # #     head = (pose[:, 7] + pose[:, 8]) / 2
# # # #     spine1 = hips + (neck - hips) / 3
# # # #     spine2 = hips + (neck - hips) * 2 / 3
# # # #     kp = [hips, spine1, spine2, neck, head,
# # # #           pose[:, 11], pose[:, 13], pose[:, 15],
# # # #           pose[:, 12], pose[:, 14], pose[:, 16],
# # # #           pose[:, 23], pose[:, 25], pose[:, 27],
# # # #           pose[:, 24], pose[:, 26], pose[:, 28]]
# # # #     return np.stack(kp, axis=1).astype(np.float32)


# # # # def active_range(pose, threshold, pad):
# # # #     """Frames where at least one wrist is clearly above the hips (= signing)."""
# # # #     T = len(pose)
# # # #     hips_y = (pose[:, 23, 1] + pose[:, 24, 1]) / 2
# # # #     wrist_y = np.minimum(pose[:, 15, 1], pose[:, 16, 1])   # MediaPipe y points DOWN
# # # #     idx = np.where(wrist_y < hips_y - threshold)[0]
# # # #     if len(idx) == 0:
# # # #         return 0, T
# # # #     return max(0, int(idx[0]) - pad), min(T, int(idx[-1]) + pad + 1)


# # # # def process_clip(raw, fps, args):
# # # #     pose = resample(raw["pose"], raw["fps"], fps)
# # # #     lh = resample(raw["lhand"], raw["fps"], fps)
# # # #     rh = resample(raw["rhand"], raw["fps"], fps)

# # # #     ok_ratio = float((~np.isnan(pose.reshape(len(pose), -1)).any(axis=1)).mean())
# # # #     if ok_ratio < 0.3:
# # # #         return None, ok_ratio

# # # #     pose = fill_gaps(pose, max_gap=int(fps * 0.6), hold_edges=True)
# # # #     pose = hold_last_valid(pose)
# # # #     pose = smooth_nan(pose, args.smooth_body)
# # # #     lh = smooth_nan(fill_gaps(lh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)
# # # #     rh = smooth_nan(fill_gaps(rh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)

# # # #     if not args.no_trim:
# # # #         a, b = active_range(pose, args.rest_threshold, int(round(fps * 0.12)))
# # # #         pose, lh, rh = pose[a:b], lh[a:b], rh[a:b]
# # # #     return {"body": body_keypoints(pose), "lh": lh, "rh": rh}, ok_ratio


# # # # def _ease(w):
# # # #     return 0.5 - 0.5 * np.cos(np.pi * w)


# # # # def assemble(clips, fps, transition_s, hold_s):
# # # #     """clips: [{gloss, video, body, lh, rh}] -> one timeline."""
# # # #     ntr = max(0, int(round(transition_s * fps)))
# # # #     hold = max(0, int(round(hold_s * fps)))
# # # #     B, LH, RH, segs = [], [], [], []
# # # #     cursor = 0

# # # #     def add(body, lh, rh):
# # # #         nonlocal cursor
# # # #         B.append(body)
# # # #         LH.append(lh)
# # # #         RH.append(rh)
# # # #         cursor += len(body)

# # # #     for i, c in enumerate(clips):
# # # #         seg_start = cursor
# # # #         if i == 0 and hold:
# # # #             add(np.repeat(c["body"][:1], hold, 0), np.repeat(c["lh"][:1], hold, 0),
# # # #                 np.repeat(c["rh"][:1], hold, 0))
# # # #         if i > 0 and ntr:
# # # #             p = clips[i - 1]
# # # #             w = _ease(np.arange(1, ntr + 1) / (ntr + 1)).reshape(-1, 1, 1)
# # # #             body = p["body"][-1][None] * (1 - w) + c["body"][0][None] * w
# # # #             lh = p["lh"][-1][None] * (1 - w) + c["lh"][0][None] * w     # NaN if either is missing
# # # #             rh = p["rh"][-1][None] * (1 - w) + c["rh"][0][None] * w
# # # #             add(body, lh, rh)
# # # #         add(c["body"], c["lh"], c["rh"])
# # # #         if i == len(clips) - 1 and hold:
# # # #             add(np.repeat(c["body"][-1:], hold, 0), np.repeat(c["lh"][-1:], hold, 0),
# # # #                 np.repeat(c["rh"][-1:], hold, 0))
# # # #         segs.append({"s": seg_start, "e": cursor, "gloss": c["gloss"], "video": c["video"]})

# # # #     body = np.concatenate(B).astype(np.float64)
# # # #     lh = np.concatenate(LH).astype(np.float64)
# # # #     rh = np.concatenate(RH).astype(np.float64)
# # # #     lv = (~np.isnan(lh.reshape(len(lh), -1)).any(axis=1)).astype(int)
# # # #     rv = (~np.isnan(rh.reshape(len(rh), -1)).any(axis=1)).astype(int)
# # # #     lh = np.nan_to_num(lh, nan=0.0)
# # # #     rh = np.nan_to_num(rh, nan=0.0)
# # # #     return {"fps": fps, "n": int(len(body)),
# # # #             "body": np.round(body, 4).ravel().tolist(),
# # # #             "lh": np.round(lh, 4).ravel().tolist(),
# # # #             "rh": np.round(rh, 4).ravel().tolist(),
# # # #             "lv": lv.tolist(), "rv": rv.tolist(), "segments": segs}


# # # # # =====================================================================
# # # # # 6. The standalone player (HTML + JavaScript, three.js r128 from a CDN)
# # # # # =====================================================================
# # # # HTML_TEMPLATE = r'''<!DOCTYPE html>
# # # # <html lang="vi">
# # # # <head>
# # # # <meta charset="utf-8">
# # # # <meta name="viewport" content="width=device-width, initial-scale=1">
# # # # <title>__TITLE__</title>
# # # # <style>
# # # #   :root { color-scheme: dark; }
# # # #   html, body { margin: 0; height: 100%; overflow: hidden; background: #0b1220; color: #e5e7eb;
# # # #                font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
# # # #   #stage { position: fixed; inset: 0; }
# # # #   #stage canvas { display: block; }
# # # #   #caption { position: fixed; top: 18px; left: 0; right: 0; text-align: center; pointer-events: none;
# # # #              font-size: 38px; font-weight: 700; text-shadow: 0 2px 12px #000; min-height: 46px; }
# # # #   #panel { position: fixed; left: 12px; right: 12px; bottom: 12px; padding: 10px 14px;
# # # #            background: rgba(15, 23, 42, .90); border: 1px solid #334155; border-radius: 12px; }
# # # #   .row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 5px 0; }
# # # #   button, select { background: #1e293b; color: #e5e7eb; border: 1px solid #475569; border-radius: 8px;
# # # #                    padding: 6px 12px; font-size: 14px; cursor: pointer; }
# # # #   button:hover { background: #334155; }
# # # #   button.rec { border-color: #ef4444; }
# # # #   input[type=range] { flex: 1; min-width: 160px; }
# # # #   label { font-size: 13px; color: #cbd5e1; display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
# # # #   .chip { padding: 3px 10px; border-radius: 999px; border: 1px solid #475569; font-size: 13px; cursor: pointer; }
# # # #   .chip.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
# # # #   #status { font-size: 12px; color: #94a3b8; }
# # # #   #status.err { color: #fca5a5; font-size: 14px; }
# # # # </style>
# # # # </head>
# # # # <body>
# # # # <div id="stage"></div>
# # # # <div id="caption"></div>
# # # # <div id="panel">
# # # #   <div class="row">
# # # #     <button id="play">Tạm dừng</button>
# # # #     <button id="restart">Phát lại</button>
# # # #     <input type="range" id="seek" min="0" max="1" step="1" value="0">
# # # #     <span id="time">0.0 / 0.0 s</span>
# # # #     <select id="speed" title="Tốc độ">
# # # #       <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
# # # #       <option value="1" selected>1x</option><option value="1.5">1.5x</option>
# # # #     </select>
# # # #     <select id="view" title="Khung nhìn">
# # # #       <option value="upper" selected>Thân trên</option>
# # # #       <option value="hands">Cận tay</option>
# # # #       <option value="full">Toàn thân</option>
# # # #     </select>
# # # #   </div>
# # # #   <div class="row" id="chips"></div>
# # # #   <div class="row">
# # # #     <label><input type="checkbox" id="o_loop" checked> Lặp lại</label>
# # # #     <label><input type="checkbox" id="o_fingers" checked> Ngón tay</label>
# # # #     <label><input type="checkbox" id="o_legs"> Chân</label>
# # # #     <label><input type="checkbox" id="o_mirror"> Lật trái/phải</label>
# # # #     <label><input type="checkbox" id="o_flipz"> Đảo chiều sâu</label>
# # # #     <label><input type="checkbox" id="o_swap"> Đổi tay trái/phải</label>
# # # #     <button id="rec" class="rec">Ghi video (.webm)</button>
# # # #   </div>
# # # #   <div id="status">Đang tải mô hình...</div>
# # # # </div>

# # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
# # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
# # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
# # # # <script>
# # # # "use strict";
# # # # const DATA = __DATA_JSON__;
# # # # const GLB_B64 = "__GLB_B64__";
# # # # const $ = (id) => document.getElementById(id);

# # # # function fail(msg) { const s = $("status"); s.textContent = msg; s.className = "err"; }

# # # # const N = DATA.n, FPS = DATA.fps;
# # # # const body = DATA.body, lh = DATA.lh, rh = DATA.rh, lv = DATA.lv, rv = DATA.rv;
# # # # const opts = { mirror: false, flipZ: false, swapHands: false, legs: false,
# # # #                fingers: true, loop: true, speed: 1 };

# # # # // ==== RETARGET START ====
# # # # // Turns MediaPipe 3D points into bone rotations of the Mixamo-style Xbot skeleton.
# # # # const BODY = ["Hips","Spine1","Spine2","Neck","Head","LeftArm","LeftForeArm","LeftHand",
# # # #   "RightArm","RightForeArm","RightHand","LeftUpLeg","LeftLeg","LeftFoot","RightUpLeg","RightLeg","RightFoot"];
# # # # const FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"];
# # # # // [bone, bone it must point to] - parents first
# # # # const AIM_PAIRS = [
# # # #   ["Hips","Spine1"], ["Spine1","Spine2"], ["Spine2","Neck"], ["Neck","Head"],
# # # #   ["LeftArm","LeftForeArm"], ["LeftForeArm","LeftHand"],
# # # #   ["RightArm","RightForeArm"], ["RightForeArm","RightHand"],
# # # #   ["LeftUpLeg","LeftLeg"], ["LeftLeg","LeftFoot"],
# # # #   ["RightUpLeg","RightLeg"], ["RightLeg","RightFoot"],
# # # # ];
# # # # const LEG_BONES = ["LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"];

# # # # const bones = {};      // clean name -> bone
# # # # const restQ = {};      // clean name -> rest-pose rotation
# # # # let rootObj = null;
# # # # const handState = { Left: { w: 0, last: null }, Right: { w: 0, last: null } };

# # # # function cleanName(n) { return n.replace(/^mixamorig:?/, ""); }

# # # # function setupModel(model) {
# # # #   rootObj = model;
# # # #   model.traverse((o) => {
# # # #     if (o.isBone) { const c = cleanName(o.name); bones[c] = o; restQ[c] = o.quaternion.clone(); }
# # # #   });
# # # #   let fingerBases = 0;
# # # #   for (const s of ["Left", "Right"]) for (const f of FINGERS) if (bones[s + "Hand" + f + "1"]) fingerBases++;
# # # #   return { bones: Object.keys(bones).length, fingerBases };
# # # # }

# # # # function resetPose() {
# # # #   for (const k in bones) bones[k].quaternion.copy(restQ[k]);
# # # #   if (rootObj) rootObj.updateMatrixWorld(true);
# # # # }

# # # # // Rotate a bone by a rotation given in WORLD space.
# # # # function applyWorldRotation(bone, qWorld) {
# # # #   if (!bone || !bone.parent) return;
# # # #   bone.parent.updateWorldMatrix(true, false);
# # # #   const pq = bone.parent.getWorldQuaternion(new THREE.Quaternion());
# # # #   const adj = pq.clone().invert().multiply(qWorld).multiply(pq);
# # # #   bone.quaternion.premultiply(adj);
# # # #   bone.updateMatrixWorld(true);
# # # # }

# # # # // Make the direction  bone -> child  point along `dir` (world space).
# # # # function aimBone(bone, child, dir) {
# # # #   if (!bone || !child || dir.lengthSq() < 1e-10) return;
# # # #   bone.updateWorldMatrix(true, true);
# # # #   const p = bone.getWorldPosition(new THREE.Vector3());
# # # #   const c = child.getWorldPosition(new THREE.Vector3());
# # # #   const cur = c.sub(p);
# # # #   if (cur.lengthSq() < 1e-12) return;
# # # #   cur.normalize();
# # # #   applyWorldRotation(bone, new THREE.Quaternion().setFromUnitVectors(cur, dir.clone().normalize()));
# # # # }

# # # # // Twist a bone around `axisDir` so that curSide lines up with tgtSide (palm orientation).
# # # # function rollBoneAround(bone, axisDir, curSide, tgtSide) {
# # # #   const a = axisDir.clone().normalize();
# # # #   const c = curSide.clone().sub(a.clone().multiplyScalar(curSide.dot(a)));
# # # #   const t = tgtSide.clone().sub(a.clone().multiplyScalar(tgtSide.dot(a)));
# # # #   if (c.lengthSq() < 1e-10 || t.lengthSq() < 1e-10) return;
# # # #   c.normalize(); t.normalize();
# # # #   let angle = Math.acos(THREE.MathUtils.clamp(c.dot(t), -1, 1));
# # # #   if (new THREE.Vector3().crossVectors(c, t).dot(a) < 0) angle = -angle;
# # # #   applyWorldRotation(bone, new THREE.Quaternion().setFromAxisAngle(a, angle));
# # # # }

# # # # function blendToRest(name, w) {
# # # #   if (w >= 0.999 || !bones[name]) return;
# # # #   const q = bones[name].quaternion.clone();
# # # #   bones[name].quaternion.copy(restQ[name]).slerp(q, w);
# # # #   bones[name].updateMatrixWorld(true);
# # # # }

# # # # function applyBody(P) {
# # # #   for (const [a, b] of AIM_PAIRS) {
# # # #     if (!opts.legs && LEG_BONES.includes(a)) continue;
# # # #     if (!bones[a] || !bones[b] || !P[a] || !P[b]) continue;
# # # #     aimBone(bones[a], bones[b], P[b].clone().sub(P[a]));
# # # #   }
# # # # }

# # # # // H: {Wrist, Thumb1..Pinky4} -> Vector3 ; w: 0..1 blend weight (0 = rest pose)
# # # # function applyHand(side, H, w) {
# # # #   if (!H || w <= 0.001) return;
# # # #   const wrist = bones[side + "Hand"], mid1 = bones[side + "HandMiddle1"];
# # # #   const idx1 = bones[side + "HandIndex1"], pky1 = bones[side + "HandPinky1"];
# # # #   if (wrist && mid1 && H.Wrist && H.Middle1) {
# # # #     const axis = H.Middle1.clone().sub(H.Wrist);
# # # #     aimBone(wrist, mid1, axis);
# # # #     if (idx1 && pky1 && H.Index1 && H.Pinky1) {
# # # #       const a = idx1.getWorldPosition(new THREE.Vector3());
# # # #       const b = pky1.getWorldPosition(new THREE.Vector3());
# # # #       rollBoneAround(wrist, axis, a.sub(b), H.Index1.clone().sub(H.Pinky1));
# # # #     }
# # # #     blendToRest(side + "Hand", w);
# # # #   }
# # # #   for (const f of FINGERS) {
# # # #     for (let n = 1; n <= 3; n++) {
# # # #       const name = side + "Hand" + f + n;
# # # #       const bone = bones[name], child = bones[side + "Hand" + f + (n + 1)];
# # # #       const p0 = H[f + n], p1 = H[f + (n + 1)];
# # # #       if (bone && child && p0 && p1) {
# # # #         aimBone(bone, child, p1.clone().sub(p0));
# # # #         blendToRest(name, w);
# # # #       }
# # # #     }
# # # #   }
# # # # }

# # # # // MediaPipe camera frame (x right, y down, z away) -> model frame (x right, y up, z towards viewer)
# # # # function toModel(x, y, z) {
# # # #   return new THREE.Vector3((opts.mirror ? -1 : 1) * x, -y, -(opts.flipZ ? -1 : 1) * z);
# # # # }

# # # # function sampleFrame(f) {
# # # #   const f0 = Math.max(0, Math.min(N - 1, Math.floor(f)));
# # # #   const f1 = Math.min(f0 + 1, N - 1);
# # # #   const a = Math.max(0, Math.min(1, f - f0));
# # # #   const lerp = (u, v) => u + (v - u) * a;

# # # #   const P = {};
# # # #   for (let j = 0; j < BODY.length; j++) {
# # # #     const o0 = (f0 * BODY.length + j) * 3, o1 = (f1 * BODY.length + j) * 3;
# # # #     P[BODY[j]] = toModel(lerp(body[o0], body[o1]), lerp(body[o0 + 1], body[o1 + 1]), lerp(body[o0 + 2], body[o1 + 2]));
# # # #   }

# # # #   const hands = { Left: null, Right: null };
# # # #   const srcs = opts.swapHands
# # # #     ? [["Left", rh, rv], ["Right", lh, lv]]
# # # #     : [["Left", lh, lv], ["Right", rh, rv]];
# # # #   for (const [side, arr, val] of srcs) {
# # # #     if (!(val[f0] && val[f1])) continue;
# # # #     const pt = (k) => {
# # # #       const o0 = (f0 * 21 + k) * 3, o1 = (f1 * 21 + k) * 3;
# # # #       return toModel(lerp(arr[o0], arr[o1]), lerp(arr[o0 + 1], arr[o1 + 1]), lerp(arr[o0 + 2], arr[o1 + 2]));
# # # #     };
# # # #     const H = { Wrist: pt(0) };
# # # #     FINGERS.forEach((fn, fi) => { for (let n = 1; n <= 4; n++) H[fn + n] = pt(1 + 4 * fi + (n - 1)); });
# # # #     hands[side] = H;
# # # #   }
# # # #   return { P, hands };
# # # # }

# # # # // Pose the whole avatar for (fractional) frame f. dt = seconds since last call.
# # # # function applyFrame(f, dt) {
# # # #   if (!rootObj) return;
# # # #   const { P, hands } = sampleFrame(f);
# # # #   resetPose();                      // always start from the rest pose: no drift, no accumulated twist
# # # #   applyBody(P);
# # # #   for (const side of ["Left", "Right"]) {
# # # #     const st = handState[side], H = hands[side];
# # # #     if (H && opts.fingers) { st.last = H; st.w = Math.min(1, st.w + dt / 0.12); }
# # # #     else { st.w = Math.max(0, st.w - dt / 0.12); }
# # # #     if (st.last && st.w > 0) applyHand(side, H && opts.fingers ? H : st.last, st.w);
# # # #   }
# # # #   rootObj.updateMatrixWorld(true);
# # # # }
# # # # // ---- size and camera: measured from the SKELETON (the mesh bounding box is unreliable for skinned models) ----
# # # # function computeFit() {
# # # #   rootObj.updateMatrixWorld(true);
# # # #   let minY = Infinity, maxY = -Infinity;
# # # #   for (const k in bones) {
# # # #     const y = bones[k].getWorldPosition(new THREE.Vector3()).y;
# # # #     if (y < minY) minY = y;
# # # #     if (y > maxY) maxY = y;
# # # #   }
# # # #   const hips = bones.Hips ? bones.Hips.getWorldPosition(new THREE.Vector3()) : null;
# # # #   const head = bones.Head ? bones.Head.getWorldPosition(new THREE.Vector3()) : null;
# # # #   return { hips, footY: minY, topY: maxY,
# # # #            hipsY: hips ? hips.y : (minY + maxY) / 2, headY: head ? head.y : maxY };
# # # # }

# # # # // view: "upper" | "hands" | "full".  H = window height (px), panelH / captionH = UI that covers the scene (px)
# # # # function computeView(fit, view, aspect, fovDeg, H, panelH, captionH) {
# # # #   const bodyH = fit.headY - fit.hipsY;
# # # #   let lo, hi, halfW;
# # # #   if (view === "full") { lo = fit.footY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
# # # #   else if (view === "hands") { lo = fit.hipsY + 0.45 * bodyH; hi = fit.headY + 0.25; halfW = 0.60; }
# # # #   else { lo = fit.hipsY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
# # # #   const avail = Math.max(0.3, (H - panelH - captionH) / H);      // share of the screen that is free
# # # #   const t = Math.tan(fovDeg * Math.PI / 360);
# # # #   const dV = ((hi - lo) / avail) / (2 * t);
# # # #   const dH = halfW / (t * aspect);
# # # #   const d = Math.max(dV, dH) * 1.05;
# # # #   const visH = 2 * d * t;
# # # #   const centerY = (lo + hi) / 2;
# # # #   const ty = centerY + ((captionH - panelH) / 2) * (visH / H);   // put the avatar in the free part of the screen
# # # #   return { target: [0, ty, 0], position: [0, ty, d] };
# # # # }

# # # # const RETARGET = { bones, restQ, setupModel, applyFrame, sampleFrame, handState, opts, resetPose, computeFit, computeView };
# # # # // ==== RETARGET END ====

# # # # (function main() {
# # # #   if (typeof THREE === "undefined" || !THREE.GLTFLoader || !THREE.OrbitControls) {
# # # #     fail("Không tải được three.js từ CDN. Hãy kiểm tra kết nối Internet rồi mở lại trang.");
# # # #     return;
# # # #   }

# # # #   // ---------- scene ----------
# # # #   const stage = $("stage");
# # # #   const renderer = new THREE.WebGLRenderer({ antialias: true });
# # # #   renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
# # # #   renderer.outputEncoding = THREE.sRGBEncoding;
# # # #   renderer.shadowMap.enabled = true;
# # # #   stage.appendChild(renderer.domElement);

# # # #   const scene = new THREE.Scene();
# # # #   scene.background = new THREE.Color(0x0b1220);
# # # #   const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
# # # #   camera.position.set(0, 1.0, 2.6);
# # # #   const controls = new THREE.OrbitControls(camera, renderer.domElement);
# # # #   controls.target.set(0, 0.9, 0);
# # # #   controls.minDistance = 0.5;
# # # #   controls.maxDistance = 10;
# # # #   controls.update();
# # # #   let fit = null;                      // skeleton measurements, filled in when the model is loaded

# # # #   function applyView() {
# # # #     if (!fit) return;
# # # #     const v = computeView(fit, $("view").value, camera.aspect, camera.fov,
# # # #                           window.innerHeight, $("panel").offsetHeight + 12, 70);
# # # #     camera.position.set(v.position[0], v.position[1], v.position[2]);
# # # #     controls.target.set(v.target[0], v.target[1], v.target[2]);
# # # #     controls.update();
# # # #   }

# # # #   scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 0.9));
# # # #   const sun = new THREE.DirectionalLight(0xffffff, 0.8);
# # # #   sun.position.set(2, 4, 3);
# # # #   sun.castShadow = true;
# # # #   scene.add(sun);
# # # #   const ground = new THREE.Mesh(new THREE.CircleGeometry(3, 48),
# # # #     new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 1 }));
# # # #   ground.rotation.x = -Math.PI / 2;
# # # #   ground.receiveShadow = true;
# # # #   scene.add(ground);
# # # #   scene.add(new THREE.GridHelper(6, 24, 0x334155, 0x1f2937));

# # # #   function resize() {
# # # #     const w = window.innerWidth, h = window.innerHeight;
# # # #     renderer.setSize(w, h);
# # # #     camera.aspect = w / h;
# # # #     camera.updateProjectionMatrix();
# # # #     applyView();
# # # #   }
# # # #   window.addEventListener("resize", resize);
# # # #   resize();

# # # #   // ---------- UI ----------
# # # #   const seek = $("seek");
# # # #   seek.max = Math.max(1, N - 1);
# # # #   const chips = $("chips");
# # # #   const segEls = DATA.segments.map((s, i) => {
# # # #     const el = document.createElement("span");
# # # #     el.className = "chip";
# # # #     el.textContent = s.gloss;
# # # #     el.title = s.video;
# # # #     el.onclick = () => { tFrame = s.s; };
# # # #     chips.appendChild(el);
# # # #     return el;
# # # #   });

# # # #   let playing = true, tFrame = 0, recording = null;
# # # #   const setPlayLabel = () => { $("play").textContent = playing ? "Tạm dừng" : "Phát"; };
# # # #   $("play").onclick = () => { playing = !playing; if (playing && tFrame >= N - 1) tFrame = 0; setPlayLabel(); };
# # # #   $("restart").onclick = () => { tFrame = 0; playing = true; setPlayLabel(); };
# # # #   seek.oninput = () => { tFrame = +seek.value; };
# # # #   $("speed").onchange = (e) => { opts.speed = +e.target.value; };
# # # #   $("view").onchange = applyView;
# # # #   for (const [id, key] of [["o_loop","loop"],["o_fingers","fingers"],["o_legs","legs"],
# # # #                            ["o_mirror","mirror"],["o_flipz","flipZ"],["o_swap","swapHands"]]) {
# # # #     $(id).onchange = (e) => { opts[key] = e.target.checked; };
# # # #   }
# # # #   window.addEventListener("keydown", (e) => { if (e.code === "Space") { e.preventDefault(); $("play").click(); } });

# # # #   $("rec").onclick = () => {
# # # #     if (!window.MediaRecorder) { alert("Trình duyệt không hỗ trợ ghi video. Hãy dùng Chrome hoặc Edge."); return; }
# # # #     if (recording) return;
# # # #     const stream = renderer.domElement.captureStream(30);
# # # #     const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]
# # # #       .find((m) => MediaRecorder.isTypeSupported(m));
# # # #     const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 6000000 });
# # # #     const chunks = [];
# # # #     rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
# # # #     rec.onstop = () => {
# # # #       const a = document.createElement("a");
# # # #       a.href = URL.createObjectURL(new Blob(chunks, { type: "video/webm" }));
# # # #       a.download = "sign_avatar.webm";
# # # #       a.click();
# # # #       recording = null;
# # # #       $("rec").textContent = "Ghi video (.webm)";
# # # #     };
# # # #     recording = { rec, prevLoop: opts.loop };
# # # #     opts.loop = false;
# # # #     tFrame = 0; playing = true; setPlayLabel();
# # # #     rec.start();
# # # #     $("rec").textContent = "Đang ghi...";
# # # #   };

# # # #   // ---------- model ----------
# # # #   let loaded = false;
# # # #   try {
# # # #     const bin = atob(GLB_B64);
# # # #     const buf = new Uint8Array(bin.length);
# # # #     for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
# # # #     new THREE.GLTFLoader().parse(buf.buffer, "", (gltf) => {
# # # #       const model = gltf.scene;
# # # #       model.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
# # # #       scene.add(model);
# # # #       const info = setupModel(model);
# # # #       // size the avatar from its skeleton: feet -> head bone = 1.55 m (about a 1.75 m person)
# # # #       let ft = computeFit();
# # # #       model.scale.multiplyScalar(1.55 / Math.max(1e-6, ft.headY - ft.footY));
# # # #       ft = computeFit();
# # # #       model.position.y -= ft.footY;
# # # #       if (ft.hips) { model.position.x -= ft.hips.x; model.position.z -= ft.hips.z; }
# # # #       fit = computeFit();
# # # #       applyView();
# # # #       loaded = true;
# # # #       $("status").textContent = "Xương: " + info.bones + " | xương ngón tay: " + info.fingerBases +
# # # #         "/10 | " + N + " khung hình, " + FPS + " fps | các từ: " + DATA.segments.map((s) => s.gloss).join(" → ");
# # # #       if (info.fingerBases < 10) $("status").textContent += "  (mô hình thiếu xương ngón tay: ngón sẽ không cử động)";
# # # #     }, (err) => { fail("Không đọc được mô hình Xbot: " + (err && err.message ? err.message : err)); });
# # # #   } catch (e) { fail("Lỗi nạp mô hình: " + e); }

# # # #   // ---------- loop ----------
# # # #   let last = performance.now();
# # # #   function tick(now) {
# # # #     const dt = Math.min(0.1, (now - last) / 1000);
# # # #     last = now;
# # # #     if (playing) {
# # # #       tFrame += dt * FPS * opts.speed;
# # # #       if (tFrame >= N - 1) {
# # # #         if (recording) {
# # # #           tFrame = N - 1; playing = false; setPlayLabel();
# # # #           opts.loop = recording.prevLoop;
# # # #           const r = recording.rec; setTimeout(() => r.state !== "inactive" && r.stop(), 250);
# # # #         } else if (opts.loop) tFrame = 0;
# # # #         else { tFrame = N - 1; playing = false; setPlayLabel(); }
# # # #       }
# # # #     }
# # # #     if (loaded) applyFrame(tFrame, dt);
# # # #     const fi = Math.floor(tFrame);
# # # #     const idx = DATA.segments.findIndex((s) => fi >= s.s && fi < s.e);
# # # #     const cur = idx >= 0 ? idx : DATA.segments.length - 1;
# # # #     $("caption").textContent = DATA.segments[cur] ? DATA.segments[cur].gloss : "";
# # # #     segEls.forEach((el, i) => el.classList.toggle("on", i === cur));
# # # #     seek.value = fi;
# # # #     $("time").textContent = (tFrame / FPS).toFixed(1) + " / " + (N / FPS).toFixed(1) + " s";
# # # #     controls.update();
# # # #     renderer.render(scene, camera);
# # # #     requestAnimationFrame(tick);
# # # #   }
# # # #   requestAnimationFrame(tick);
# # # # })();
# # # # </script>
# # # # </body>
# # # # </html>
# # # # '''


# # # # def write_html(timeline, xbot_path, out_path, title):
# # # #     glb = Path(xbot_path).read_bytes()
# # # #     data_json = json.dumps(timeline, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
# # # #     html = (HTML_TEMPLATE
# # # #             .replace("__TITLE__", title.replace("<", "&lt;"))
# # # #             .replace("__DATA_JSON__", data_json)
# # # #             .replace("__GLB_B64__", base64.b64encode(glb).decode("ascii")))
# # # #     out = Path(out_path)
# # # #     out.parent.mkdir(parents=True, exist_ok=True)
# # # #     out.write_text(html, encoding="utf-8")
# # # #     return out


# # # # # =====================================================================
# # # # # 6b. Trang web cho sign_app.py (localhost): gõ từ -> Xbot ký ngay
# # # # #     Dùng lại khối RETARGET của HTML_TEMPLATE; dữ liệu lấy từ /api/sentence,
# # # # #     mô hình lấy từ /xbot.glb, danh sách từ lấy từ /api/glosses.
# # # # # =====================================================================
# # # # APP_TEMPLATE = r'''<!DOCTYPE html>
# # # # <html lang="vi">
# # # # <head>
# # # # <meta charset="utf-8">
# # # # <meta name="viewport" content="width=device-width, initial-scale=1">
# # # # <title>Xbot - Ngôn ngữ ký hiệu</title>
# # # # <style>
# # # #   :root { color-scheme: dark; }
# # # #   html, body { margin: 0; height: 100%; overflow: hidden; background: #0b1220; color: #e5e7eb;
# # # #                font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
# # # #   #stage { position: fixed; inset: 0; }
# # # #   #stage canvas { display: block; }
# # # #   #top { position: fixed; top: 12px; left: 12px; right: 12px; padding: 10px 14px; z-index: 5;
# # # #          background: rgba(15, 23, 42, .90); border: 1px solid #334155; border-radius: 12px; }
# # # #   #top .row { margin: 0; }
# # # #   #text { flex: 1; min-width: 200px; background: #0f172a; color: #e5e7eb; border: 1px solid #475569;
# # # #           border-radius: 8px; padding: 8px 12px; font-size: 16px; outline: none; }
# # # #   #text:focus { border-color: #3b82f6; }
# # # #   #sug { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
# # # #   #sug:empty { display: none; }
# # # #   #warn { font-size: 12px; color: #fcd34d; margin-top: 6px; max-height: 64px; overflow: auto; }
# # # #   #warn:empty { display: none; }
# # # #   #caption { position: fixed; top: 96px; left: 0; right: 0; text-align: center; pointer-events: none;
# # # #              font-size: 38px; font-weight: 700; text-shadow: 0 2px 12px #000; min-height: 46px; }
# # # #   #panel { position: fixed; left: 12px; right: 12px; bottom: 12px; padding: 10px 14px;
# # # #            background: rgba(15, 23, 42, .90); border: 1px solid #334155; border-radius: 12px; }
# # # #   .row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 5px 0; }
# # # #   button, select { background: #1e293b; color: #e5e7eb; border: 1px solid #475569; border-radius: 8px;
# # # #                    padding: 6px 12px; font-size: 14px; cursor: pointer; }
# # # #   button:hover { background: #334155; }
# # # #   button.go { background: #2563eb; border-color: #2563eb; color: #fff; font-weight: 600; }
# # # #   button.rec { border-color: #ef4444; }
# # # #   input[type=range] { flex: 1; min-width: 160px; }
# # # #   label { font-size: 13px; color: #cbd5e1; display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
# # # #   .chip { padding: 3px 10px; border-radius: 999px; border: 1px solid #475569; font-size: 13px; cursor: pointer; }
# # # #   .chip.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
# # # #   #status { font-size: 12px; color: #94a3b8; }
# # # #   #status.err { color: #fca5a5; font-size: 14px; }
# # # # </style>
# # # # </head>
# # # # <body>
# # # # <div id="stage"></div>
# # # # <div id="top">
# # # #   <div class="row">
# # # #     <input id="text" type="text" autocomplete="off" spellcheck="false"
# # # #            placeholder="Gõ các từ, cách nhau bằng dấu phẩy, rồi nhấn Enter. Ví dụ: bạn, đi học, có không">
# # # #     <button id="go" class="go">Chạy</button>
# # # #   </div>
# # # #   <div id="sug"></div>
# # # #   <div id="warn"></div>
# # # # </div>
# # # # <div id="caption"></div>
# # # # <div id="panel">
# # # #   <div class="row">
# # # #     <button id="play">Tạm dừng</button>
# # # #     <button id="restart">Phát lại</button>
# # # #     <input type="range" id="seek" min="0" max="1" step="1" value="0">
# # # #     <span id="time">0.0 / 0.0 s</span>
# # # #     <select id="speed" title="Tốc độ">
# # # #       <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
# # # #       <option value="1" selected>1x</option><option value="1.5">1.5x</option>
# # # #     </select>
# # # #     <select id="view" title="Khung nhìn">
# # # #       <option value="upper" selected>Thân trên</option>
# # # #       <option value="hands">Cận tay</option>
# # # #       <option value="full">Toàn thân</option>
# # # #     </select>
# # # #   </div>
# # # #   <div class="row" id="chips"></div>
# # # #   <div class="row">
# # # #     <label><input type="checkbox" id="o_loop"> Lặp lại</label>
# # # #     <label><input type="checkbox" id="o_fingers" checked> Ngón tay</label>
# # # #     <label><input type="checkbox" id="o_legs"> Chân</label>
# # # #     <label><input type="checkbox" id="o_mirror"> Lật trái/phải</label>
# # # #     <label><input type="checkbox" id="o_flipz"> Đảo chiều sâu</label>
# # # #     <label><input type="checkbox" id="o_swap"> Đổi tay trái/phải</label>
# # # #     <button id="rec" class="rec">Ghi video (.webm)</button>
# # # #   </div>
# # # #   <div id="status">Đang tải mô hình...</div>
# # # # </div>

# # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
# # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
# # # # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
# # # # <script>
# # # # "use strict";
# # # # const $ = (id) => document.getElementById(id);
# # # # function setStatus(msg) { const s = $("status"); s.textContent = msg; s.className = ""; }
# # # # function fail(msg) { const s = $("status"); s.textContent = msg; s.className = "err"; }

# # # # // dữ liệu của câu hiện tại (được thay mỗi lần gõ từ)
# # # # let N = 1, FPS = 30, body = [], lh = [], rh = [], lv = [], rv = [], segs = [], hasData = false;
# # # # const opts = { mirror: false, flipZ: false, swapHands: false, legs: false,
# # # #                fingers: true, loop: false, speed: 1 };

# # # # __RETARGET__

# # # # (function main() {
# # # #   if (typeof THREE === "undefined" || !THREE.GLTFLoader || !THREE.OrbitControls) {
# # # #     fail("Không tải được three.js từ CDN. Hãy kiểm tra kết nối Internet rồi mở lại trang.");
# # # #     return;
# # # #   }

# # # #   // ---------- scene ----------
# # # #   const stage = $("stage");
# # # #   const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: false });
# # # #   renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
# # # #   renderer.outputEncoding = THREE.sRGBEncoding;
# # # #   renderer.shadowMap.enabled = true;
# # # #   stage.appendChild(renderer.domElement);

# # # #   const scene = new THREE.Scene();
# # # #   scene.background = new THREE.Color(0x0b1220);
# # # #   const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
# # # #   camera.position.set(0, 1.0, 2.6);
# # # #   const controls = new THREE.OrbitControls(camera, renderer.domElement);
# # # #   controls.target.set(0, 0.9, 0);
# # # #   controls.minDistance = 0.5;
# # # #   controls.maxDistance = 10;
# # # #   controls.update();
# # # #   let fit = null;

# # # #   function applyView() {
# # # #     if (!fit) return;
# # # #     const v = computeView(fit, $("view").value, camera.aspect, camera.fov,
# # # #                           window.innerHeight, $("panel").offsetHeight + 12, 150);
# # # #     camera.position.set(v.position[0], v.position[1], v.position[2]);
# # # #     controls.target.set(v.target[0], v.target[1], v.target[2]);
# # # #     controls.update();
# # # #   }

# # # #   scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 0.9));
# # # #   const sun = new THREE.DirectionalLight(0xffffff, 0.8);
# # # #   sun.position.set(2, 4, 3);
# # # #   sun.castShadow = true;
# # # #   scene.add(sun);
# # # #   const ground = new THREE.Mesh(new THREE.CircleGeometry(3, 48),
# # # #     new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 1 }));
# # # #   ground.rotation.x = -Math.PI / 2;
# # # #   ground.receiveShadow = true;
# # # #   scene.add(ground);
# # # #   scene.add(new THREE.GridHelper(6, 24, 0x334155, 0x1f2937));

# # # #   function resize() {
# # # #     const w = window.innerWidth, h = window.innerHeight;
# # # #     renderer.setSize(w, h);
# # # #     camera.aspect = w / h;
# # # #     camera.updateProjectionMatrix();
# # # #     applyView();
# # # #   }
# # # #   window.addEventListener("resize", resize);
# # # #   resize();

# # # #   // ---------- UI ----------
# # # #   const seek = $("seek"), chips = $("chips"), input = $("text");
# # # #   let playing = false, tFrame = 0, recording = null, loaded = false, segEls = [];
# # # #   const setPlayLabel = () => { $("play").textContent = playing ? "Tạm dừng" : "Phát"; };
# # # #   $("play").onclick = () => { if (!hasData) return; playing = !playing; if (playing && tFrame >= N - 1) tFrame = 0; setPlayLabel(); };
# # # #   $("restart").onclick = () => { if (!hasData) return; tFrame = 0; playing = true; setPlayLabel(); };
# # # #   seek.oninput = () => { tFrame = +seek.value; };
# # # #   $("speed").onchange = (e) => { opts.speed = +e.target.value; };
# # # #   $("view").onchange = applyView;
# # # #   for (const [id, key] of [["o_loop","loop"],["o_fingers","fingers"],["o_legs","legs"],
# # # #                            ["o_mirror","mirror"],["o_flipz","flipZ"],["o_swap","swapHands"]]) {
# # # #     $(id).onchange = (e) => { opts[key] = e.target.checked; };
# # # #   }
# # # #   window.addEventListener("keydown", (e) => {
# # # #     if (e.code === "Space" && e.target.tagName !== "INPUT") { e.preventDefault(); $("play").click(); }
# # # #   });

# # # #   $("rec").onclick = () => {
# # # #     if (!hasData) { alert("Hãy gõ từ và nhấn Ký trước khi ghi video."); return; }
# # # #     if (!window.MediaRecorder) { alert("Trình duyệt không hỗ trợ ghi video. Hãy dùng Chrome hoặc Edge."); return; }
# # # #     if (recording) return;
# # # #     const stream = renderer.domElement.captureStream(30);
# # # #     const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]
# # # #       .find((m) => MediaRecorder.isTypeSupported(m));
# # # #     const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 6000000 });
# # # #     const chunks = [];
# # # #     rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
# # # #     rec.onstop = () => {
# # # #       const a = document.createElement("a");
# # # #       a.href = URL.createObjectURL(new Blob(chunks, { type: "video/webm" }));
# # # #       a.download = "sign_avatar.webm";
# # # #       a.click();
# # # #       recording = null;
# # # #       $("rec").textContent = "Ghi video (.webm)";
# # # #     };
# # # #     recording = { rec, prevLoop: opts.loop };
# # # #     opts.loop = false;
# # # #     tFrame = 0; playing = true; setPlayLabel();
# # # #     rec.start();
# # # #     $("rec").textContent = "Đang ghi...";
# # # #   };

# # # #   // ---------- nạp câu mới ----------
# # # #   function setTimeline(tl) {
# # # #     N = tl.n; FPS = tl.fps; body = tl.body; lh = tl.lh; rh = tl.rh; lv = tl.lv; rv = tl.rv;
# # # #     segs = tl.segments; hasData = N > 0;
# # # #     for (const s of ["Left", "Right"]) { handState[s].w = 0; handState[s].last = null; }
# # # #     seek.max = Math.max(1, N - 1);
# # # #     chips.innerHTML = "";
# # # #     segEls = segs.map((s) => {
# # # #       const el = document.createElement("span");
# # # #       el.className = "chip";
# # # #       el.textContent = s.gloss;
# # # #       el.title = s.video;
# # # #       el.onclick = () => { tFrame = s.s; };
# # # #       chips.appendChild(el);
# # # #       return el;
# # # #     });
# # # #     tFrame = 0; playing = true; setPlayLabel();
# # # #   }

# # # #   function showWarn(list) {
# # # #     $("warn").textContent = (list || []).join("  |  ");
# # # #   }

# # # #   let busy = false;
# # # #   async function submit() {
# # # #     const text = input.value.trim();
# # # #     if (!text || busy) return;
# # # #     busy = true;
# # # #     setStatus("Đang xử lý...");
# # # #     try {
# # # #       const r = await fetch("/api/sentence", {
# # # #         method: "POST", headers: { "Content-Type": "application/json" },
# # # #         body: JSON.stringify({ text }),
# # # #       });
# # # #       const res = await r.json();
# # # #       showWarn(res.warnings);
# # # #       if (!res.ok) { fail("Không ký được: " + (res.error || "lỗi không rõ")); return; }
# # # #       setTimeline(res.timeline);
# # # #       setStatus(N + " khung hình, " + FPS + " fps | các từ: " + res.picks.map((p) => p.gloss).join(" → "));
# # # #     } catch (e) {
# # # #       fail("Không gọi được máy chủ: " + e);
# # # #     } finally { busy = false; }
# # # #   }
# # # #   $("go").onclick = submit;
# # # #   input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("sug").innerHTML = ""; submit(); } });

# # # #   // ---------- gợi ý từ ----------
# # # #   let GLOSSES = [], FOLDED = [];
# # # #   const fold = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "d").toLowerCase();
# # # #   fetch("/api/glosses").then((r) => r.json()).then((list) => {
# # # #     GLOSSES = list; FOLDED = list.map(fold);
# # # #   }).catch(() => {});
# # # #   input.addEventListener("input", () => {
# # # #     const box = $("sug");
# # # #     box.innerHTML = "";
# # # #     const part = input.value.split(/[,;|]/).pop().trim();
# # # #     if (!part || !GLOSSES.length) return;
# # # #     const q = fold(part);
# # # #     const hits = [];
# # # #     for (let i = 0; i < GLOSSES.length && hits.length < 10; i++) if (FOLDED[i].includes(q)) hits.push(GLOSSES[i]);
# # # #     for (const g of hits) {
# # # #       const el = document.createElement("span");
# # # #       el.className = "chip";
# # # #       el.textContent = g;
# # # #       el.onclick = () => {
# # # #         const cut = Math.max(input.value.lastIndexOf(","), input.value.lastIndexOf(";"), input.value.lastIndexOf("|"));
# # # #         input.value = (cut >= 0 ? input.value.slice(0, cut + 1) + " " : "") + g;
# # # #         box.innerHTML = "";
# # # #         input.focus();
# # # #       };
# # # #       box.appendChild(el);
# # # #     }
# # # #   });

# # # #   // ---------- model ----------
# # # #   new THREE.GLTFLoader().load("/xbot.glb", (gltf) => {
# # # #     const model = gltf.scene;
# # # #     model.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
# # # #     scene.add(model);
# # # #     const info = setupModel(model);
# # # #     let ft = computeFit();
# # # #     model.scale.multiplyScalar(1.55 / Math.max(1e-6, ft.headY - ft.footY));
# # # #     ft = computeFit();
# # # #     model.position.y -= ft.footY;
# # # #     if (ft.hips) { model.position.x -= ft.hips.x; model.position.z -= ft.hips.z; }
# # # #     fit = computeFit();
# # # #     applyView();
# # # #     loaded = true;
# # # #     if (!hasData) setStatus("Xương: " + info.bones + " | xương ngón tay: " + info.fingerBases + "/10 | Sẵn sàng - hãy gõ từ rồi nhấn Enter.");
# # # #     if (info.fingerBases < 10) $("status").textContent += "  (mô hình thiếu xương ngón tay: ngón sẽ không cử động)";
# # # #   }, undefined, (err) => { fail("Không đọc được mô hình Xbot: " + (err && err.message ? err.message : err)); });

# # # #   input.focus();

# # # #   // ---------- loop ----------
# # # #   let last = performance.now();
# # # #   function tick(now) {
# # # #     const dt = Math.min(0.1, (now - last) / 1000);
# # # #     last = now;
# # # #     if (hasData && playing) {
# # # #       tFrame += dt * FPS * opts.speed;
# # # #       if (tFrame >= N - 1) {
# # # #         if (recording) {
# # # #           tFrame = N - 1; playing = false; setPlayLabel();
# # # #           opts.loop = recording.prevLoop;
# # # #           const r = recording.rec; setTimeout(() => r.state !== "inactive" && r.stop(), 250);
# # # #         } else if (opts.loop) tFrame = 0;
# # # #         else { tFrame = N - 1; playing = false; setPlayLabel(); }
# # # #       }
# # # #     }
# # # #     if (loaded && hasData) {
# # # #       applyFrame(tFrame, dt);
# # # #       const fi = Math.floor(tFrame);
# # # #       const idx = segs.findIndex((s) => fi >= s.s && fi < s.e);
# # # #       const cur = idx >= 0 ? idx : segs.length - 1;
# # # #       $("caption").textContent = segs[cur] ? segs[cur].gloss : "";
# # # #       segEls.forEach((el, i) => el.classList.toggle("on", i === cur));
# # # #       seek.value = fi;
# # # #       $("time").textContent = (tFrame / FPS).toFixed(1) + " / " + (N / FPS).toFixed(1) + " s";
# # # #     }
# # # #     controls.update();
# # # #     renderer.render(scene, camera);
# # # #     requestAnimationFrame(tick);
# # # #   }
# # # #   requestAnimationFrame(tick);
# # # # })();
# # # # </script>
# # # # </body>
# # # # </html>
# # # # '''


# # # # def render_app_page():
# # # #     """Trang cho sign_app.py (bytes). Dùng lại khối RETARGET của HTML_TEMPLATE để không phải sửa hai nơi."""
# # # #     start = HTML_TEMPLATE.index("// ==== RETARGET START ====")
# # # #     end_mark = "// ==== RETARGET END ===="
# # # #     end = HTML_TEMPLATE.index(end_mark) + len(end_mark)
# # # #     return APP_TEMPLATE.replace("__RETARGET__", HTML_TEMPLATE[start:end]).encode("utf-8")


# # # # # =====================================================================
# # # # # 7. Command line
# # # # # =====================================================================
# # # # def build_parser():
# # # #     p = argparse.ArgumentParser(
# # # #         description="Chuỗi gloss -> avatar Xbot chuyển động liên tục (file HTML độc lập).")
# # # #     g = p.add_argument_group("đầu vào")
# # # #     g.add_argument("--glosses", nargs="+", help='Danh sách gloss, ví dụ: --glosses "bạn" "đi học" "có không"')
# # # #     g.add_argument("--sentence", help='Các gloss ngăn cách bằng dấu |, ví dụ: "bạn | đi học | có không"')
# # # #     g.add_argument("--glosses-file", help="File .json (list) hoặc .txt (mỗi dòng 1 gloss)")
# # # #     g = p.add_argument_group("đường dẫn")
# # # #     g.add_argument("--labels", help="File ánh xạ VIDEO/LABEL (csv, tsv, txt, xlsx, json)")
# # # #     g.add_argument("--videos", default=DEFAULT_VIDEOS, help="Thư mục chứa các video của dataset")
# # # #     g.add_argument("--xbot", default=DEFAULT_XBOT, help="File Xbot.glb")
# # # #     g.add_argument("--cache", default=DEFAULT_CACHE, help="Thư mục lưu tọa độ đã tính (.npz)")
# # # #     g.add_argument("--out", default=DEFAULT_OUT, help="File HTML đầu ra")
# # # #     g = p.add_argument_group("chọn video")
# # # #     g.add_argument("--region", default="B,T,N", help="Thứ tự ưu tiên giọng vùng: B=Bắc, T=Trung, N=Nam")
# # # #     g.add_argument("--search", help="Tìm nhãn chứa chuỗi này (không cần dấu) rồi thoát")
# # # #     g.add_argument("--precompute-all", action="store_true",
# # # #                    help="Tính trước tọa độ cho mọi gloss (lâu, chạy một lần)")
# # # #     g = p.add_argument_group("chuyển động")
# # # #     g.add_argument("--fps", type=float, default=30.0)
# # # #     g.add_argument("--transition", type=float, default=0.25, help="Giây chuyển tiếp giữa 2 từ")
# # # #     g.add_argument("--hold", type=float, default=0.2, help="Giây giữ tư thế đầu/cuối")
# # # #     g.add_argument("--smooth-body", type=float, default=1.5, help="Độ mượt thân (khung hình, 0 = tắt)")
# # # #     g.add_argument("--smooth-hands", type=float, default=1.0, help="Độ mượt ngón tay (0 = tắt)")
# # # #     g.add_argument("--hand-gap", type=int, default=6, help="Nội suy khi mất tay tối đa N khung")
# # # #     g.add_argument("--no-trim", action="store_true", help="Không cắt đoạn tay buông ở đầu/cuối video")
# # # #     g.add_argument("--rest-threshold", type=float, default=0.10,
# # # #                    help="Cổ tay phải cao hơn hông bao nhiêu mét để tính là đang ký")
# # # #     g.add_argument("--complexity", type=int, default=1, choices=[0, 1, 2],
# # # #                    help="Độ chính xác MediaPipe Pose (2 = chính xác nhất, chậm nhất)")
# # # #     p.add_argument("--open", action="store_true", help="Mở file HTML sau khi tạo")
# # # #     return p


# # # # def get_glosses(args):
# # # #     if args.glosses:
# # # #         return [g for g in args.glosses if g.strip()]
# # # #     if args.sentence:
# # # #         return [g.strip() for g in args.sentence.split("|") if g.strip()]
# # # #     if args.glosses_file:
# # # #         txt = read_text_auto(args.glosses_file)
# # # #         if args.glosses_file.lower().endswith(".json"):
# # # #             return [str(g) for g in json.loads(txt)]
# # # #         return [l.strip() for l in txt.splitlines() if l.strip()]
# # # #     return []


# # # # def main(argv=None, detector_factory=None):
# # # #     args = build_parser().parse_args(argv)
# # # #     videos_dir = Path(args.videos)

# # # #     labels = args.labels or find_labels_file(videos_dir)
# # # #     if not labels or not Path(labels).exists():
# # # #         print("Không tìm thấy file nhãn. Hãy chỉ rõ bằng --labels \"đường\\dẫn\\file.csv\"")
# # # #         return 2
# # # #     records = load_records(labels)
# # # #     index = GlossIndex(records, args.region.split(","))
# # # #     print(f"Đã đọc {len(records)} video / {len(index.by_key)} khóa tra cứu từ: {labels}")

# # # #     if args.search:
# # # #         hits = index.search(args.search)
# # # #         print(f'\nCác nhãn chứa "{args.search}" ({len(hits)} kết quả đầu):')
# # # #         for r in hits:
# # # #             print(f"  {r['video']:<14} {r['label']}")
# # # #         return 0

# # # #     if detector_factory is None:
# # # #         detector_factory = lambda: MediaPipeDetector(args.complexity)

# # # #     if args.precompute_all:
# # # #         picks = {}
# # # #         for rec in index.recs:
# # # #             key = norm(rec["label"])
# # # #             if key not in picks:
# # # #                 picks[key] = index.choose(index.lookup(rec["label"]))[0]
# # # #         todo = sorted(picks.values(), key=lambda r: natural_key(r["stem"]))
# # # #         print(f"Tính trước {len(todo)} video (mỗi gloss một video)...")
# # # #         for i, rec in enumerate(todo, 1):
# # # #             vp = videos_dir / rec["video"]
# # # #             try:
# # # #                 _, hit = get_clip_data(vp, args.cache, detector_factory)
# # # #                 print(f"[{i}/{len(todo)}] {rec['video']} {'(đã có)' if hit else 'xong'}")
# # # #             except Exception as e:
# # # #                 print(f"[{i}/{len(todo)}] {rec['video']} LỖI: {e}")
# # # #         return 0

# # # #     glosses = get_glosses(args)
# # # #     if not glosses:
# # # #         raw = input('Nhập các gloss, ngăn cách bằng dấu | (ví dụ: bạn | đi học | có không): ')
# # # #         glosses = [g.strip() for g in raw.split("|") if g.strip()]
# # # #     if not glosses:
# # # #         print("Chưa có gloss nào.")
# # # #         return 2

# # # #     # ---- gloss -> video ----
# # # #     picks, problems = [], []
# # # #     for g in glosses:
# # # #         found, missing = index.resolve_one(g)
# # # #         picks += found
# # # #         for w in missing:
# # # #             sug = index.suggest(w)
# # # #             problems.append(f'Không có gloss "{w}"' + (f" (gần giống: {', '.join(sug)})" if sug else ""))
# # # #     print("\nChuỗi gloss -> video:")
# # # #     for g, rec, note in picks:
# # # #         print(f"  {g:<18} -> {rec['video']:<14} [{rec['label']}]" + (f"  ({note})" if note else ""))
# # # #     for p in problems:
# # # #         print("  CẢNH BÁO:", p)
# # # #     if not picks:
# # # #         return 1

# # # #     # ---- landmarks (cached) ----
# # # #     clips = []
# # # #     for i, (g, rec, _) in enumerate(picks, 1):
# # # #         vp = videos_dir / rec["video"]
# # # #         cache_file = Path(args.cache) / (rec["stem"] + ".npz")
# # # #         if not vp.exists() and not cache_file.exists():
# # # #             print(f"  CẢNH BÁO: không thấy video {vp}")
# # # #             continue
# # # #         try:
# # # #             raw, hit = get_clip_data(vp, args.cache, detector_factory)
# # # #         except Exception as e:
# # # #             print(f"  CẢNH BÁO: lỗi với {rec['video']}: {e}")
# # # #             continue
# # # #         clip, ok = process_clip(raw, args.fps, args)
# # # #         if clip is None:
# # # #             print(f"  CẢNH BÁO: {rec['video']} chỉ nhận diện được {ok:.0%} khung hình, bỏ qua")
# # # #             continue
# # # #         hands_ok = [float((~np.isnan(clip[k].reshape(len(clip[k]), -1)).any(axis=1)).mean())
# # # #                     for k in ("lh", "rh")]
# # # #         print(f"  [{i}/{len(picks)}] {rec['video']}: {len(clip['body'])} khung ({len(clip['body'])/args.fps:.1f}s), "
# # # #               f"có tay trái {hands_ok[0]:.0%} / tay phải {hands_ok[1]:.0%}" + ("" if hit else "  (vừa tính xong, đã lưu cache)"))
# # # #         clip.update({"gloss": g, "video": rec["video"]})
# # # #         clips.append(clip)
# # # #     if not clips:
# # # #         print("Không có video nào dùng được.")
# # # #         return 1

# # # #     # ---- one continuous timeline -> html ----
# # # #     timeline = assemble(clips, args.fps, args.transition, args.hold)
# # # #     if not Path(args.xbot).exists():
# # # #         print(f"Không thấy file Xbot: {args.xbot}  (dùng --xbot để chỉ đường dẫn)")
# # # #         return 2
# # # #     out = write_html(timeline, args.xbot, args.out, "Avatar: " + " | ".join(c["gloss"] for c in clips))
# # # #     print(f"\nXong: {timeline['n']} khung hình = {timeline['n']/args.fps:.1f} giây")
# # # #     print(f"Mở file này (bấm đúp): {out.resolve()}")
# # # #     if args.open:
# # # #         webbrowser.open(out.resolve().as_uri())
# # # #     return 0


# # # # if __name__ == "__main__":
# # # #     sys.exit(main())





















































# # #!/usr/bin/env python3
# # # -*- coding: utf-8 -*-
# # """
# # sign_to_avatar.py
# # =================
# # Gloss list  ->  videos of the dataset  ->  3D landmarks (cached .npz)
# #             ->  ONE continuous animation of the Xbot avatar (standalone .html).

# # Example:
# #     python sign_to_avatar.py --glosses "bạn" "đi học" "có không"
# #     python sign_to_avatar.py --sentence "bạn | đi học | có không" --open
# #     python sign_to_avatar.py --search "địa chỉ"

# # The output .html is a single file: double-click it, no server / localhost needed.
# # (It only needs Internet once per open, to load three.js from a CDN.)
# # """
# # import argparse
# # import base64
# # import csv
# # import difflib
# # import io
# # import json
# # import os
# # import re
# # import sys
# # import unicodedata
# # import webbrowser
# # from pathlib import Path

# # import numpy as np

# # # =====================================================================
# # # DEFAULTS (edit these once, then you never need to type the paths)
# # # =====================================================================
# # DEFAULT_VIDEOS = r"C:\Users\ADMIN\qh\vsl-vietnamese-sign-languages\versions\5\Dataset\Videos"
# # DEFAULT_XBOT = os.path.join("frontend_dis", "models", "Xbot.glb")
# # DEFAULT_CACHE = "landmark_cache"
# # DEFAULT_OUT = os.path.join("output", "sentence.html")

# # CACHE_VERSION = 1
# # VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")

# # BODY_NAMES = [
# #     "Hips", "Spine1", "Spine2", "Neck", "Head",
# #     "LeftArm", "LeftForeArm", "LeftHand",
# #     "RightArm", "RightForeArm", "RightHand",
# #     "LeftUpLeg", "LeftLeg", "LeftFoot",
# #     "RightUpLeg", "RightLeg", "RightFoot",
# # ]

# # try:  # make Vietnamese text safe to print on any console
# #     sys.stdout.reconfigure(errors="replace")
# #     sys.stderr.reconfigure(errors="replace")
# # except Exception:
# #     pass


# # # =====================================================================
# # # 1. Text helpers
# # # =====================================================================
# # def norm(s):
# #     """NFC + lower-case + collapsed spaces."""
# #     return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s)).strip().lower())


# # def strip_accents(s):
# #     s = norm(s).replace("đ", "d")
# #     s = unicodedata.normalize("NFD", s)
# #     return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# # def without_parens(s):
# #     return norm(re.sub(r"\([^)]*\)", " ", str(s)))


# # def natural_key(s):
# #     return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


# # VIDEO_RE = re.compile(r"^(?P<base>.*\d)(?P<reg>[NTBntb])?$")


# # def parse_video(name):
# #     """'D0001N.mp4' -> ('D0001', 'N');  'D0002.mp4' -> ('D0002', '')."""
# #     stem = Path(str(name).strip()).stem
# #     m = VIDEO_RE.match(stem)
# #     if m:
# #         return m.group("base"), (m.group("reg") or "").upper()
# #     return stem, ""


# # def label_keys(label):
# #     """All the lookup keys under which a dataset label can be found."""
# #     plain = without_parens(label)
# #     parts = {norm(label), plain}
# #     for p in re.split(r"\s*[;/,]\s*", plain):
# #         if p.strip():
# #             parts.add(norm(p))
# #     keys = set()
# #     for p in parts:
# #         if p:
# #             keys.add(p)
# #             keys.add(strip_accents(p))
# #     return keys


# # # =====================================================================
# # # 2. Reading the label file (csv / tsv / txt / xlsx / json)
# # # =====================================================================
# # def read_text_auto(path):
# #     raw = Path(path).read_bytes()
# #     if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:200]:
# #         return raw.decode("utf-16", errors="replace")
# #     try:
# #         return raw.decode("utf-8-sig")
# #     except UnicodeDecodeError:
# #         return raw.decode("cp1258", errors="replace")


# # def _pick_columns(header):
# #     h = [norm(c) for c in header]
# #     vi = next((i for i, c in enumerate(h) if c in ("video", "file", "filename", "name")), None)
# #     li = next((i for i, c in enumerate(h) if c in ("label", "gloss", "nhan", "nhãn", "text")), None)
# #     return vi, li


# # def load_records(path):
# #     """Return [(video_name, label), ...] from any supported file type."""
# #     path = str(path)
# #     ext = Path(path).suffix.lower()

# #     if ext == ".json":
# #         data = json.loads(read_text_auto(path))
# #         recs = []
# #         if isinstance(data, dict):
# #             for gloss, vids in data.items():
# #                 if isinstance(vids, (str, dict)):
# #                     vids = [vids]
# #                 for v in vids:
# #                     recs.append((v["video"] if isinstance(v, dict) else v, gloss))
# #         else:
# #             for item in data:
# #                 if isinstance(item, dict):
# #                     low = {norm(k): v for k, v in item.items()}
# #                     recs.append((low.get("video") or low.get("file"),
# #                                  low.get("label") or low.get("gloss")))
# #                 else:
# #                     recs.append((item[0], item[1]))
# #         return [(str(v), str(l)) for v, l in recs if v and l]

# #     if ext in (".xlsx", ".xls", ".xlsm"):
# #         import pandas as pd  # needs openpyxl for .xlsx
# #         df = pd.read_excel(path, dtype=str).fillna("")
# #         rows = [list(df.columns)] + df.values.tolist()
# #     else:
# #         text = read_text_auto(path)
# #         first = text.splitlines()[0] if text else ""
# #         delim = max(["\t", ",", ";"], key=first.count)
# #         rows = list(csv.reader(io.StringIO(text), delimiter=delim))

# #     rows = [r for r in rows if r and any(str(c).strip() for c in r)]
# #     if not rows:
# #         return []
# #     vi, li = _pick_columns(rows[0])
# #     start = 1
# #     if vi is None or li is None:  # no header: first two columns
# #         vi, li = 0, 1
# #         start = 0 if Path(str(rows[0][0])).suffix.lower() in VIDEO_EXTS else 1
# #     out = []
# #     for r in rows[start:]:
# #         if len(r) > max(vi, li) and str(r[vi]).strip() and str(r[li]).strip():
# #             out.append((str(r[vi]).strip(), str(r[li]).strip()))
# #     return out


# # def find_labels_file(videos_dir):
# #     vd = Path(videos_dir)
# #     exts = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json")
# #     cands = []
# #     for d in (vd, vd.parent, vd.parent.parent):
# #         if d.is_dir():
# #             cands += [p for p in d.iterdir() if p.suffix.lower() in exts]
# #     hits = [p for p in cands if "label" in p.name.lower()]
# #     if len(hits) >= 1:
# #         return str(sorted(hits, key=lambda p: len(str(p)))[0])
# #     return None


# # # =====================================================================
# # # 3. Gloss index: label -> video
# # # =====================================================================
# # class GlossIndex:
# #     def __init__(self, records, region_pref=("B", "T", "N")):
# #         self.region_pref = [r.upper() for r in region_pref]
# #         self.recs = []
# #         self.by_key = {}
# #         self.by_stem = {}
# #         for video, label in records:
# #             base, reg = parse_video(video)
# #             rec = {"video": Path(video).name, "stem": Path(video).stem,
# #                    "base": base, "region": reg, "label": label}
# #             self.recs.append(rec)
# #             self.by_stem[norm(rec["stem"])] = rec
# #             for k in label_keys(label):
# #                 self.by_key.setdefault(k, []).append(rec)

# #     def lookup(self, text):
# #         for v in (norm(text), without_parens(text),
# #                   strip_accents(text), strip_accents(without_parens(text))):
# #             if v and v in self.by_key:
# #                 return self.by_key[v]
# #         return []

# #     def choose(self, recs):
# #         """One video for a gloss: first sign (lowest id), preferred region."""
# #         groups = {}
# #         for r in recs:
# #             groups.setdefault(r["base"], []).append(r)
# #         bases = sorted(groups, key=natural_key)
# #         group = groups[bases[0]]
# #         group.sort(key=lambda r: (self.region_pref.index(r["region"])
# #                                   if r["region"] in self.region_pref else 99,
# #                                   natural_key(r["stem"])))
# #         return group[0], len(bases) - 1

# #     def resolve_one(self, gloss):
# #         """Return (list of (gloss_text, rec, note), list of missing words)."""
# #         g = str(gloss).strip()
# #         if not g:
# #             return [], []
# #         # a video id typed directly, e.g. "D0001T"
# #         rec = self.by_stem.get(norm(Path(g).stem))
# #         if rec is not None and re.fullmatch(r"[dD]\d+[NTBntb]?(\.\w+)?", g):
# #             return [(g, rec, "")], []

# #         recs = self.lookup(g)
# #         if recs:
# #             rec, extra = self.choose(recs)
# #             note = f"còn {extra} cách ký khác" if extra > 0 else ""
# #             return [(g, rec, note)], []

# #         # not a known gloss: split into the longest known pieces
# #         words = norm(g).split()
# #         found, missing, i = [], [], 0
# #         while i < len(words):
# #             for j in range(len(words), i, -1):
# #                 phrase = " ".join(words[i:j])
# #                 recs = self.lookup(phrase)
# #                 if recs:
# #                     rec, extra = self.choose(recs)
# #                     found.append((phrase, rec, f'tách từ "{g}"'))
# #                     i = j
# #                     break
# #             else:
# #                 missing.append(words[i])
# #                 i += 1
# #         if not found:
# #             return [], [g]
# #         return found, missing

# #     def suggest(self, text, n=4):
# #         pool = {}
# #         for k, recs in self.by_key.items():
# #             if strip_accents(k) == k:
# #                 pool[k] = recs[0]["label"]
# #         close = difflib.get_close_matches(strip_accents(text), list(pool), n=n, cutoff=0.6)
# #         return [pool[c] for c in close]

# #     def search(self, text, limit=30):
# #         t = strip_accents(text)
# #         hits = [r for r in self.recs if t in strip_accents(r["label"])]
# #         return sorted(hits, key=lambda r: natural_key(r["stem"]))[:limit]


# # # =====================================================================
# # # 4. Landmark extraction (MediaPipe) + cache
# # # =====================================================================
# # def assign_hands(hands, left_wrist, right_wrist):
# #     """
# #     hands: [(image_wrist_xy, world_21x3, label)], wrists in normalised image coords.
# #     Decide which detected hand is the person's LEFT / RIGHT by comparing with the
# #     body-pose wrists (more reliable than the handedness label for un-mirrored video).
# #     """
# #     res = {"L": None, "R": None}
# #     if not hands:
# #         return res

# #     def d(a, b):
# #         return float(np.hypot(a[0] - b[0], a[1] - b[1]))

# #     if left_wrist is not None and right_wrist is not None:
# #         if len(hands) == 1:
# #             h = hands[0]
# #             res["L" if d(h[0], left_wrist) <= d(h[0], right_wrist) else "R"] = h[1]
# #         else:
# #             h0, h1 = hands[0], hands[1]
# #             a = d(h0[0], left_wrist) + d(h1[0], right_wrist)
# #             b = d(h0[0], right_wrist) + d(h1[0], left_wrist)
# #             if a <= b:
# #                 res["L"], res["R"] = h0[1], h1[1]
# #             else:
# #                 res["L"], res["R"] = h1[1], h0[1]
# #     else:  # no body wrists: use the label (MediaPipe assumes a mirrored image -> swap)
# #         for h in hands:
# #             res["R" if h[2] == "Left" else "L"] = h[1]
# #     return res


# # class MediaPipeDetector:
# #     """Pose (33 world landmarks) + Hands (21 world landmarks each), one video at a time."""

# #     def __init__(self, complexity=1):
# #         import mediapipe as mp
# #         self.pose = mp.solutions.pose.Pose(
# #             static_image_mode=False, model_complexity=complexity, smooth_landmarks=True,
# #             min_detection_confidence=0.5, min_tracking_confidence=0.5)
# #         self.hands = mp.solutions.hands.Hands(
# #             static_image_mode=False, max_num_hands=2, model_complexity=1,
# #             min_detection_confidence=0.5, min_tracking_confidence=0.5)

# #     def __enter__(self):
# #         return self

# #     def __exit__(self, *a):
# #         self.pose.close()
# #         self.hands.close()
# #         return False

# #     def process(self, rgb):
# #         pr = self.pose.process(rgb)
# #         hr = self.hands.process(rgb)
# #         pose_world = left_w = right_w = None
# #         if pr.pose_world_landmarks:
# #             pose_world = np.array([[l.x, l.y, l.z] for l in pr.pose_world_landmarks.landmark],
# #                                   dtype=np.float32)
# #         if pr.pose_landmarks:
# #             lm = pr.pose_landmarks.landmark
# #             left_w, right_w = (lm[15].x, lm[15].y), (lm[16].x, lm[16].y)
# #         hands = []
# #         if hr.multi_hand_world_landmarks and hr.multi_hand_landmarks:
# #             for wl, il, hd in zip(hr.multi_hand_world_landmarks,
# #                                   hr.multi_hand_landmarks, hr.multi_handedness):
# #                 world = np.array([[l.x, l.y, l.z] for l in wl.landmark], dtype=np.float32)
# #                 hands.append(((il.landmark[0].x, il.landmark[0].y), world,
# #                               hd.classification[0].label))
# #         return {"pose": pose_world, "left_wrist": left_w, "right_wrist": right_w, "hands": hands}


# # def extract_video(video_path, detector_factory, target_width=640):
# #     """Run the detector on every frame. Returns dict of arrays (NaN = not detected)."""
# #     import cv2
# #     cap = cv2.VideoCapture(str(video_path))
# #     if not cap.isOpened():
# #         raise IOError(f"Không mở được video: {video_path}")
# #     fps = cap.get(cv2.CAP_PROP_FPS)
# #     if not fps or fps != fps or fps <= 1:
# #         fps = 30.0
# #     pose_l, lh_l, rh_l = [], [], []
# #     nan_pose = np.full((33, 3), np.nan, np.float32)
# #     nan_hand = np.full((21, 3), np.nan, np.float32)
# #     with detector_factory() as det:
# #         while True:
# #             ok, frame = cap.read()
# #             if not ok:
# #                 break
# #             h, w = frame.shape[:2]
# #             if w != target_width and w > 0:
# #                 frame = cv2.resize(frame, (target_width, int(h * target_width / w)))
# #             rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
# #             r = det.process(rgb)
# #             pose_l.append(r["pose"] if r["pose"] is not None else nan_pose)
# #             a = assign_hands(r["hands"], r["left_wrist"], r["right_wrist"])
# #             lh_l.append(a["L"] if a["L"] is not None else nan_hand)
# #             rh_l.append(a["R"] if a["R"] is not None else nan_hand)
# #     cap.release()
# #     if not pose_l:
# #         raise IOError(f"Video rỗng: {video_path}")
# #     return {"pose": np.stack(pose_l).astype(np.float32),
# #             "lhand": np.stack(lh_l).astype(np.float32),
# #             "rhand": np.stack(rh_l).astype(np.float32),
# #             "fps": float(fps)}


# # def get_clip_data(video_path, cache_dir, detector_factory):
# #     cache_path = Path(cache_dir) / (Path(video_path).stem + ".npz")
# #     if cache_path.exists():
# #         try:
# #             d = np.load(cache_path)
# #             if int(d["version"]) == CACHE_VERSION:
# #                 data = {k: d[k] for k in ("pose", "lhand", "rhand")}
# #                 data["fps"] = float(d["fps"])
# #                 return data, True
# #         except Exception:
# #             pass
# #     data = extract_video(video_path, detector_factory)
# #     cache_path.parent.mkdir(parents=True, exist_ok=True)
# #     np.savez_compressed(cache_path, pose=data["pose"], lhand=data["lhand"],
# #                         rhand=data["rhand"], fps=data["fps"], version=CACHE_VERSION)
# #     return data, False


# # # =====================================================================
# # # 5. Clean-up: resample, fill gaps, smooth, trim, join
# # # =====================================================================
# # def resample(arr, src_fps, dst_fps):
# #     T = len(arr)
# #     if T < 2 or abs(src_fps - dst_fps) < 1e-3:
# #         return arr
# #     new_T = max(2, int(round((T - 1) * dst_fps / src_fps)) + 1)
# #     t = np.linspace(0, T - 1, new_T)
# #     i0 = np.floor(t).astype(int)
# #     i1 = np.minimum(i0 + 1, T - 1)
# #     a = (t - i0).reshape((-1,) + (1,) * (arr.ndim - 1))
# #     return arr[i0] * (1 - a) + arr[i1] * a   # NaN stays NaN if either neighbour is missing


# # def fill_gaps(arr, max_gap, hold_edges):
# #     T = len(arr)
# #     flat = arr.reshape(T, -1).astype(np.float64)
# #     valid = ~np.isnan(flat).any(axis=1)
# #     idx = np.where(valid)[0]
# #     if len(idx) == 0:
# #         return arr
# #     out = flat.copy()
# #     for a, b in zip(idx[:-1], idx[1:]):
# #         gap = b - a - 1
# #         if 0 < gap <= max_gap:
# #             for k in range(1, gap + 1):
# #                 w = k / (gap + 1)
# #                 out[a + k] = flat[a] * (1 - w) + flat[b] * w
# #     if hold_edges:
# #         out[:idx[0]] = flat[idx[0]]
# #         out[idx[-1] + 1:] = flat[idx[-1]]
# #     return out.reshape(arr.shape).astype(np.float32)


# # def hold_last_valid(arr):
# #     """Replace remaining NaN frames by the previous (or next) valid frame."""
# #     T = len(arr)
# #     flat = arr.reshape(T, -1).copy()
# #     valid = ~np.isnan(flat).any(axis=1)
# #     if not valid.any():
# #         return arr
# #     last = None
# #     for i in range(T):
# #         if valid[i]:
# #             last = flat[i].copy()
# #         elif last is not None:
# #             flat[i] = last
# #     first = np.where(valid)[0][0]
# #     flat[:first] = flat[first]
# #     return flat.reshape(arr.shape)


# # def smooth_nan(arr, sigma):
# #     """Gaussian smoothing along time; invalid (NaN) frames stay invalid."""
# #     T = len(arr)
# #     if sigma <= 0 or T < 2:
# #         return arr
# #     flat = arr.reshape(T, -1).astype(np.float64)
# #     valid = ~np.isnan(flat).any(axis=1)
# #     if not valid.any():
# #         return arr
# #     i = np.arange(T)
# #     W = np.exp(-0.5 * ((i[:, None] - i[None, :]) / sigma) ** 2) * valid[None, :]
# #     num = W @ np.where(valid[:, None], flat, 0.0)
# #     den = np.maximum(W.sum(axis=1, keepdims=True), 1e-9)
# #     out = num / den
# #     out[~valid] = np.nan
# #     return out.reshape(arr.shape).astype(np.float32)


# # def body_keypoints(pose):
# #     """(T,33,3) MediaPipe pose -> (T,17,3) avatar keypoints (order = BODY_NAMES)."""
# #     hips = (pose[:, 23] + pose[:, 24]) / 2
# #     neck = (pose[:, 11] + pose[:, 12]) / 2
# #     head = (pose[:, 7] + pose[:, 8]) / 2
# #     spine1 = hips + (neck - hips) / 3
# #     spine2 = hips + (neck - hips) * 2 / 3
# #     kp = [hips, spine1, spine2, neck, head,
# #           pose[:, 11], pose[:, 13], pose[:, 15],
# #           pose[:, 12], pose[:, 14], pose[:, 16],
# #           pose[:, 23], pose[:, 25], pose[:, 27],
# #           pose[:, 24], pose[:, 26], pose[:, 28]]
# #     return np.stack(kp, axis=1).astype(np.float32)


# # def active_range(pose, threshold, pad):
# #     """Frames where at least one wrist is clearly above the hips (= signing)."""
# #     T = len(pose)
# #     hips_y = (pose[:, 23, 1] + pose[:, 24, 1]) / 2
# #     wrist_y = np.minimum(pose[:, 15, 1], pose[:, 16, 1])   # MediaPipe y points DOWN
# #     idx = np.where(wrist_y < hips_y - threshold)[0]
# #     if len(idx) == 0:
# #         return 0, T
# #     return max(0, int(idx[0]) - pad), min(T, int(idx[-1]) + pad + 1)


# # def process_clip(raw, fps, args):
# #     pose = resample(raw["pose"], raw["fps"], fps)
# #     lh = resample(raw["lhand"], raw["fps"], fps)
# #     rh = resample(raw["rhand"], raw["fps"], fps)

# #     ok_ratio = float((~np.isnan(pose.reshape(len(pose), -1)).any(axis=1)).mean())
# #     if ok_ratio < 0.3:
# #         return None, ok_ratio

# #     pose = fill_gaps(pose, max_gap=int(fps * 0.6), hold_edges=True)
# #     pose = hold_last_valid(pose)
# #     pose = smooth_nan(pose, args.smooth_body)
# #     lh = smooth_nan(fill_gaps(lh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)
# #     rh = smooth_nan(fill_gaps(rh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)

# #     if not args.no_trim:
# #         a, b = active_range(pose, args.rest_threshold, int(round(fps * 0.12)))
# #         pose, lh, rh = pose[a:b], lh[a:b], rh[a:b]
# #     return {"body": body_keypoints(pose), "lh": lh, "rh": rh}, ok_ratio


# # def _ease(w):
# #     return 0.5 - 0.5 * np.cos(np.pi * w)


# # def assemble(clips, fps, transition_s, hold_s):
# #     """clips: [{gloss, video, body, lh, rh}] -> one timeline."""
# #     ntr = max(0, int(round(transition_s * fps)))
# #     hold = max(0, int(round(hold_s * fps)))
# #     B, LH, RH, segs = [], [], [], []
# #     cursor = 0

# #     def add(body, lh, rh):
# #         nonlocal cursor
# #         B.append(body)
# #         LH.append(lh)
# #         RH.append(rh)
# #         cursor += len(body)

# #     for i, c in enumerate(clips):
# #         seg_start = cursor
# #         if i == 0 and hold:
# #             add(np.repeat(c["body"][:1], hold, 0), np.repeat(c["lh"][:1], hold, 0),
# #                 np.repeat(c["rh"][:1], hold, 0))
# #         if i > 0 and ntr:
# #             p = clips[i - 1]
# #             w = _ease(np.arange(1, ntr + 1) / (ntr + 1)).reshape(-1, 1, 1)
# #             body = p["body"][-1][None] * (1 - w) + c["body"][0][None] * w
# #             lh = p["lh"][-1][None] * (1 - w) + c["lh"][0][None] * w     # NaN if either is missing
# #             rh = p["rh"][-1][None] * (1 - w) + c["rh"][0][None] * w
# #             add(body, lh, rh)
# #         add(c["body"], c["lh"], c["rh"])
# #         if i == len(clips) - 1 and hold:
# #             add(np.repeat(c["body"][-1:], hold, 0), np.repeat(c["lh"][-1:], hold, 0),
# #                 np.repeat(c["rh"][-1:], hold, 0))
# #         segs.append({"s": seg_start, "e": cursor, "gloss": c["gloss"], "video": c["video"]})

# #     body = np.concatenate(B).astype(np.float64)
# #     lh = np.concatenate(LH).astype(np.float64)
# #     rh = np.concatenate(RH).astype(np.float64)
# #     lv = (~np.isnan(lh.reshape(len(lh), -1)).any(axis=1)).astype(int)
# #     rv = (~np.isnan(rh.reshape(len(rh), -1)).any(axis=1)).astype(int)
# #     lh = np.nan_to_num(lh, nan=0.0)
# #     rh = np.nan_to_num(rh, nan=0.0)
# #     return {"fps": fps, "n": int(len(body)),
# #             "body": np.round(body, 4).ravel().tolist(),
# #             "lh": np.round(lh, 4).ravel().tolist(),
# #             "rh": np.round(rh, 4).ravel().tolist(),
# #             "lv": lv.tolist(), "rv": rv.tolist(), "segments": segs}


# # # =====================================================================
# # # 6. The standalone player (HTML + JavaScript, three.js r128 from a CDN)
# # # =====================================================================
# # HTML_TEMPLATE = r'''<!DOCTYPE html>
# # <html lang="vi">
# # <head>
# # <meta charset="utf-8">
# # <meta name="viewport" content="width=device-width, initial-scale=1">
# # <title>__TITLE__</title>
# # <style>
# #   :root { color-scheme: dark; }
# #   html, body { margin: 0; height: 100%; overflow: hidden; background: #0b1220; color: #e5e7eb;
# #                font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
# #   #stage { position: fixed; inset: 0; }
# #   #stage canvas { display: block; }
# #   body:not(.app) #bar, body:not(.app) #sug { display: none; }
# #   #bar { position: fixed; top: 12px; left: 50%; transform: translateX(-50%); width: min(720px, 92vw); display: flex; gap: 8px; z-index: 6; }
# #   #q { flex: 1; padding: 10px 14px; font-size: 16px; border-radius: 10px; border: 1px solid #475569; background: #0f172a; color: #e5e7eb; }
# #   #sug { position: fixed; top: 58px; left: 50%; transform: translateX(-50%); width: min(720px, 92vw); display: flex; flex-wrap: wrap; gap: 6px; z-index: 6; }
# #   #status .w { color: #fbbf24; }
# #   #mode { max-width: 190px; }
# #   #caption { position: fixed; top: 18px; left: 0; right: 0; text-align: center; pointer-events: none;
# #              font-size: 34px; font-weight: 700; text-shadow: 0 2px 12px #000; min-height: 46px; }
# #   #panel { position: fixed; left: 12px; right: 12px; bottom: 12px; padding: 10px 14px;
# #            background: rgba(15, 23, 42, .90); border: 1px solid #334155; border-radius: 12px; }
# #   .row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 5px 0; }
# #   button, select { background: #1e293b; color: #e5e7eb; border: 1px solid #475569; border-radius: 8px;
# #                    padding: 6px 12px; font-size: 14px; cursor: pointer; }
# #   button:hover { background: #334155; }
# #   button.rec { border-color: #ef4444; }
# #   input[type=range] { flex: 1; min-width: 160px; }
# #   label { font-size: 13px; color: #cbd5e1; display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
# #   .chip { padding: 3px 10px; border-radius: 999px; border: 1px solid #475569; font-size: 13px; cursor: pointer; }
# #   .chip.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
# #   #status { font-size: 12px; color: #94a3b8; }
# #   #status.err { color: #fca5a5; font-size: 14px; }
# # </style>
# # </head>
# # <body>
# # <div id="stage"></div>
# # <div id="bar"><select id="mode" title="Cách nhập"><option value="sentence">Câu (model dịch)</option><option value="gloss">Từ</option></select><input id="q" type="text" autocomplete="off" placeholder=""><button id="run">Chạy</button></div>
# # <div id="sug"></div>
# # <div id="caption"></div>
# # <div id="panel">
# #   <div class="row">
# #     <button id="play">Tạm dừng</button>
# #     <button id="restart">Phát lại</button>
# #     <input type="range" id="seek" min="0" max="1" step="1" value="0">
# #     <span id="time">0.0 / 0.0 s</span>
# #     <select id="speed" title="Tốc độ">
# #       <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
# #       <option value="1" selected>1x</option><option value="1.5">1.5x</option>
# #     </select>
# #     <select id="view" title="Khung nhìn">
# #       <option value="upper" selected>Thân trên</option>
# #       <option value="hands">Cận tay</option>
# #       <option value="full">Toàn thân</option>
# #     </select>
# #   </div>
# #   <div class="row" id="chips"></div>
# #   <div class="row">
# #     <label><input type="checkbox" id="o_loop" checked> Lặp lại</label>
# #     <label><input type="checkbox" id="o_fingers" checked> Ngón tay</label>
# #     <label><input type="checkbox" id="o_legs"> Chân</label>
# #     <label><input type="checkbox" id="o_mirror"> Lật trái/phải</label>
# #     <label><input type="checkbox" id="o_flipz"> Đảo chiều sâu</label>
# #     <label><input type="checkbox" id="o_swap"> Đổi tay trái/phải</label>
# #     <label><input type="checkbox" id="o_rest" checked> Về tư thế nghỉ khi xong</label>
# #   </div>
# #   <div id="status">Đang tải mô hình...</div>
# # </div>

# # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
# # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
# # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
# # <script>
# # "use strict";
# # const DATA = __DATA_JSON__;
# # const GLB_B64 = "__GLB_B64__";
# # const GLB_URL = "__GLB_URL__";
# # const APP_MODE = __APP_MODE__;
# # const $ = (id) => document.getElementById(id);

# # function fail(msg) { const s = $("status"); s.textContent = msg; s.className = "err"; }

# # const opts = { mirror: false, flipZ: false, swapHands: false, legs: false,
# #                fingers: true, loop: !APP_MODE, speed: 1, rest: true };

# # // ==== RETARGET START ====
# # // Turns MediaPipe 3D points into bone rotations of the Mixamo-style Xbot skeleton.
# # const BODY = ["Hips","Spine1","Spine2","Neck","Head","LeftArm","LeftForeArm","LeftHand",
# #   "RightArm","RightForeArm","RightHand","LeftUpLeg","LeftLeg","LeftFoot","RightUpLeg","RightLeg","RightFoot"];
# # const FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"];
# # // [bone, bone it must point to] - parents first
# # const AIM_PAIRS = [
# #   ["Hips","Spine1"], ["Spine1","Spine2"], ["Spine2","Neck"], ["Neck","Head"],
# #   ["LeftArm","LeftForeArm"], ["LeftForeArm","LeftHand"],
# #   ["RightArm","RightForeArm"], ["RightForeArm","RightHand"],
# #   ["LeftUpLeg","LeftLeg"], ["LeftLeg","LeftFoot"],
# #   ["RightUpLeg","RightLeg"], ["RightLeg","RightFoot"],
# # ];
# # const LEG_BONES = ["LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"];

# # const bones = {};      // clean name -> bone
# # const restQ = {};      // clean name -> rest-pose rotation
# # let rootObj = null;
# # const handState = { Left: { w: 0, last: null }, Right: { w: 0, last: null } };

# # function cleanName(n) { return n.replace(/^mixamorig:?/, ""); }

# # function setupModel(model) {
# #   rootObj = model;
# #   model.traverse((o) => {
# #     if (o.isBone) { const c = cleanName(o.name); bones[c] = o; restQ[c] = o.quaternion.clone(); }
# #   });
# #   let fingerBases = 0;
# #   for (const s of ["Left", "Right"]) for (const f of FINGERS) if (bones[s + "Hand" + f + "1"]) fingerBases++;
# #   return { bones: Object.keys(bones).length, fingerBases };
# # }

# # function resetPose() {
# #   for (const k in bones) bones[k].quaternion.copy(restQ[k]);
# #   if (rootObj) rootObj.updateMatrixWorld(true);
# # }

# # // Rotate a bone by a rotation given in WORLD space.
# # function applyWorldRotation(bone, qWorld) {
# #   if (!bone || !bone.parent) return;
# #   bone.parent.updateWorldMatrix(true, false);
# #   const pq = bone.parent.getWorldQuaternion(new THREE.Quaternion());
# #   const adj = pq.clone().invert().multiply(qWorld).multiply(pq);
# #   bone.quaternion.premultiply(adj);
# #   bone.updateMatrixWorld(true);
# # }

# # // Make the direction  bone -> child  point along `dir` (world space).
# # function aimBone(bone, child, dir) {
# #   if (!bone || !child || dir.lengthSq() < 1e-10) return;
# #   bone.updateWorldMatrix(true, true);
# #   const p = bone.getWorldPosition(new THREE.Vector3());
# #   const c = child.getWorldPosition(new THREE.Vector3());
# #   const cur = c.sub(p);
# #   if (cur.lengthSq() < 1e-12) return;
# #   cur.normalize();
# #   applyWorldRotation(bone, new THREE.Quaternion().setFromUnitVectors(cur, dir.clone().normalize()));
# # }

# # // Twist a bone around `axisDir` so that curSide lines up with tgtSide (palm orientation).
# # function rollBoneAround(bone, axisDir, curSide, tgtSide) {
# #   const a = axisDir.clone().normalize();
# #   const c = curSide.clone().sub(a.clone().multiplyScalar(curSide.dot(a)));
# #   const t = tgtSide.clone().sub(a.clone().multiplyScalar(tgtSide.dot(a)));
# #   if (c.lengthSq() < 1e-10 || t.lengthSq() < 1e-10) return;
# #   c.normalize(); t.normalize();
# #   let angle = Math.acos(THREE.MathUtils.clamp(c.dot(t), -1, 1));
# #   if (new THREE.Vector3().crossVectors(c, t).dot(a) < 0) angle = -angle;
# #   applyWorldRotation(bone, new THREE.Quaternion().setFromAxisAngle(a, angle));
# # }

# # function blendToRest(name, w) {
# #   if (w >= 0.999 || !bones[name]) return;
# #   const q = bones[name].quaternion.clone();
# #   bones[name].quaternion.copy(restQ[name]).slerp(q, w);
# #   bones[name].updateMatrixWorld(true);
# # }

# # function applyBody(P) {
# #   for (const [a, b] of AIM_PAIRS) {
# #     if (!opts.legs && LEG_BONES.includes(a)) continue;
# #     if (!bones[a] || !bones[b] || !P[a] || !P[b]) continue;
# #     aimBone(bones[a], bones[b], P[b].clone().sub(P[a]));
# #   }
# # }

# # // H: {Wrist, Thumb1..Pinky4} -> Vector3 ; w: 0..1 blend weight (0 = rest pose)
# # function applyHand(side, H, w) {
# #   if (!H || w <= 0.001) return;
# #   const wrist = bones[side + "Hand"], mid1 = bones[side + "HandMiddle1"];
# #   const idx1 = bones[side + "HandIndex1"], pky1 = bones[side + "HandPinky1"];
# #   if (wrist && mid1 && H.Wrist && H.Middle1) {
# #     const axis = H.Middle1.clone().sub(H.Wrist);
# #     aimBone(wrist, mid1, axis);
# #     if (idx1 && pky1 && H.Index1 && H.Pinky1) {
# #       const a = idx1.getWorldPosition(new THREE.Vector3());
# #       const b = pky1.getWorldPosition(new THREE.Vector3());
# #       rollBoneAround(wrist, axis, a.sub(b), H.Index1.clone().sub(H.Pinky1));
# #     }
# #     blendToRest(side + "Hand", w);
# #   }
# #   for (const f of FINGERS) {
# #     for (let n = 1; n <= 3; n++) {
# #       const name = side + "Hand" + f + n;
# #       const bone = bones[name], child = bones[side + "Hand" + f + (n + 1)];
# #       const p0 = H[f + n], p1 = H[f + (n + 1)];
# #       if (bone && child && p0 && p1) {
# #         aimBone(bone, child, p1.clone().sub(p0));
# #         blendToRest(name, w);
# #       }
# #     }
# #   }
# # }

# # // MediaPipe camera frame (x right, y down, z away) -> model frame (x right, y up, z towards viewer)
# # function toModel(x, y, z) {
# #   return new THREE.Vector3((opts.mirror ? -1 : 1) * x, -y, -(opts.flipZ ? -1 : 1) * z);
# # }

# # let TL = null;   // current timeline {n, fps, body, lh, rh, lv, rv, segments}
# # function setTimeline(D) { TL = D; }
# # const lerp1 = (u, v, a) => u + (v - u) * a;

# # // raw pose = {b: Float64Array(51), l: Float64Array(63) | null, r: ...} in MediaPipe camera coordinates
# # function rawAt(T, f) {
# #   const n = T.n, f0 = Math.max(0, Math.min(n - 1, Math.floor(f))), f1 = Math.min(f0 + 1, n - 1);
# #   const a = Math.max(0, Math.min(1, f - f0));
# #   const b = new Float64Array(51);
# #   for (let i = 0; i < 51; i++) b[i] = lerp1(T.body[f0 * 51 + i], T.body[f1 * 51 + i], a);
# #   const hand = (arr, val) => {
# #     if (!(val[f0] && val[f1])) return null;
# #     const h = new Float64Array(63);
# #     for (let i = 0; i < 63; i++) h[i] = lerp1(arr[f0 * 63 + i], arr[f1 * 63 + i], a);
# #     return h;
# #   };
# #   return { b, l: hand(T.lh, T.lv), r: hand(T.rh, T.rv) };
# # }
# # function blendRaw(A, B, w) {
# #   const mix = (x, y) => {
# #     if (!y) return null;
# #     if (!x) return y;
# #     const o = new Float64Array(y.length);
# #     for (let i = 0; i < y.length; i++) o[i] = lerp1(x[i], y[i], w);
# #     return o;
# #   };
# #   const b = new Float64Array(51);
# #   for (let i = 0; i < 51; i++) b[i] = lerp1(A.b[i], B.b[i], w);
# #   return { b, l: mix(A.l, B.l), r: mix(A.r, B.r) };
# # }
# # // standing, arms hanging down (camera coordinates: y points down)
# # const IDLE_RAW = { l: null, r: null, b: Float64Array.from([
# #   0,0,0,  0,-.15,0,  0,-.30,0,  0,-.45,0,  0,-.62,0,
# #   .18,-.42,0,  .21,-.16,-.02,  .22,.08,-.04,
# #   -.18,-.42,0,  -.21,-.16,-.02,  -.22,.08,-.04,
# #   .09,0,0,  .09,.45,0,  .09,.90,0,   -.09,0,0,  -.09,.45,0,  -.09,.90,0]) };

# # function rawToPoints(raw) {
# #   const P = {};
# #   for (let j = 0; j < BODY.length; j++) P[BODY[j]] = toModel(raw.b[j * 3], raw.b[j * 3 + 1], raw.b[j * 3 + 2]);
# #   const hands = { Left: null, Right: null };
# #   const [L, R] = opts.swapHands ? [raw.r, raw.l] : [raw.l, raw.r];
# #   for (const [side, h] of [["Left", L], ["Right", R]]) {
# #     if (!h) continue;
# #     const pt = (k) => toModel(h[k * 3], h[k * 3 + 1], h[k * 3 + 2]);
# #     const H = { Wrist: pt(0) };
# #     FINGERS.forEach((fn, fi) => { for (let n = 1; n <= 4; n++) H[fn + n] = pt(1 + 4 * fi + (n - 1)); });
# #     hands[side] = H;
# #   }
# #   return { P, hands };
# # }

# # // Pose the whole avatar from a raw pose. dt = seconds since last call.
# # function applyRaw(raw, dt) {
# #   if (!rootObj) return;
# #   const { P, hands } = rawToPoints(raw);
# #   resetPose();                      // always start from the rest pose: no drift, no accumulated twist
# #   applyBody(P);
# #   for (const side of ["Left", "Right"]) {
# #     const st = handState[side], H = hands[side];
# #     if (H && opts.fingers) { st.last = H; st.w = Math.min(1, st.w + dt / 0.12); }
# #     else { st.w = Math.max(0, st.w - dt / 0.12); }
# #     if (st.last && st.w > 0) applyHand(side, H && opts.fingers ? H : st.last, st.w);
# #   }
# #   rootObj.updateMatrixWorld(true);
# # }
# # function sampleFrame(f) { return rawToPoints(rawAt(TL, f)); }
# # function applyFrame(f, dt) { if (TL) applyRaw(rawAt(TL, f), dt); }

# # // ---- size and camera: measured from the SKELETON (the mesh bounding box is unreliable for skinned models) ----
# # function computeFit() {
# #   rootObj.updateMatrixWorld(true);
# #   let minY = Infinity, maxY = -Infinity;
# #   for (const k in bones) {
# #     const y = bones[k].getWorldPosition(new THREE.Vector3()).y;
# #     if (y < minY) minY = y;
# #     if (y > maxY) maxY = y;
# #   }
# #   const hips = bones.Hips ? bones.Hips.getWorldPosition(new THREE.Vector3()) : null;
# #   const head = bones.Head ? bones.Head.getWorldPosition(new THREE.Vector3()) : null;
# #   return { hips, footY: minY, topY: maxY,
# #            hipsY: hips ? hips.y : (minY + maxY) / 2, headY: head ? head.y : maxY };
# # }

# # // view: "upper" | "hands" | "full".  H = window height (px), panelH / captionH = UI that covers the scene (px)
# # function computeView(fit, view, aspect, fovDeg, H, panelH, captionH) {
# #   const bodyH = fit.headY - fit.hipsY;
# #   let lo, hi, halfW;
# #   if (view === "full") { lo = fit.footY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
# #   else if (view === "hands") { lo = fit.hipsY + 0.45 * bodyH; hi = fit.headY + 0.25; halfW = 0.60; }
# #   else { lo = fit.hipsY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
# #   const avail = Math.max(0.3, (H - panelH - captionH) / H);      // share of the screen that is free
# #   const t = Math.tan(fovDeg * Math.PI / 360);
# #   const dV = ((hi - lo) / avail) / (2 * t);
# #   const dH = halfW / (t * aspect);
# #   const d = Math.max(dV, dH) * 1.05;
# #   const visH = 2 * d * t;
# #   const centerY = (lo + hi) / 2;
# #   const ty = centerY + ((captionH - panelH) / 2) * (visH / H);   // put the avatar in the free part of the screen
# #   return { target: [0, ty, 0], position: [0, ty, d] };
# # }

# # const RETARGET = { bones, restQ, setupModel, applyFrame, applyRaw, sampleFrame, rawAt, blendRaw, IDLE_RAW,
# #                    setTimeline, handState, opts, resetPose, computeFit, computeView };
# # // ==== RETARGET END ====

# # (function main() {
# #   if (APP_MODE) document.body.classList.add("app");
# #   if (typeof THREE === "undefined" || !THREE.GLTFLoader || !THREE.OrbitControls) {
# #     fail("Không tải được three.js (cần Internet lần đầu). Hãy kiểm tra kết nối rồi tải lại trang.");
# #     return;
# #   }
# #   // ---------- scene ----------
# #   const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
# #   renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
# #   renderer.outputEncoding = THREE.sRGBEncoding;
# #   $("stage").appendChild(renderer.domElement);
# #   const scene = new THREE.Scene();
# #   scene.background = new THREE.Color(0x0b1220);
# #   const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
# #   camera.position.set(0, 1.0, 2.6);
# #   const controls = new THREE.OrbitControls(camera, renderer.domElement);
# #   controls.target.set(0, 0.9, 0);
# #   controls.minDistance = 0.5;
# #   controls.maxDistance = 10;
# #   controls.update();
# #   scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 0.95));
# #   const sun = new THREE.DirectionalLight(0xffffff, 0.8);
# #   sun.position.set(2, 4, 3);
# #   scene.add(sun);
# #   const ground = new THREE.Mesh(new THREE.CircleGeometry(3, 48), new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 1 }));
# #   ground.rotation.x = -Math.PI / 2;
# #   scene.add(ground);
# #   scene.add(new THREE.GridHelper(6, 24, 0x334155, 0x1f2937));

# #   let fit = null;                                   // skeleton measurements, set when the model is loaded
# #   const TOP_H = APP_MODE ? 150 : 70;                // screen space covered by the input bar / caption
# #   function applyView() {
# #     if (!fit) return;
# #     const v = computeView(fit, $("view").value, camera.aspect, camera.fov, window.innerHeight, $("panel").offsetHeight + 12, TOP_H);
# #     camera.position.set(v.position[0], v.position[1], v.position[2]);
# #     controls.target.set(v.target[0], v.target[1], v.target[2]);
# #     controls.update();
# #   }
# #   function resize() {
# #     const w = window.innerWidth, h = window.innerHeight;
# #     renderer.setSize(w, h);
# #     camera.aspect = w / h;
# #     camera.updateProjectionMatrix();
# #     applyView();
# #   }
# #   window.addEventListener("resize", resize);
# #   resize();

# #   // ---------- playback state: idle -> play -> hold -> idle, always blended so nothing ever jumps ----------
# #   const seek = $("seek"), chips = $("chips");
# #   let mode = "idle", playing = true, tFrame = 0, holdLeft = 0, loaded = false;
# #   let cur = IDLE_RAW, from = IDLE_RAW, blendLeft = 0, segEls = [];
# #   const BLEND = 0.35;
# #   const ease = (x) => 0.5 - 0.5 * Math.cos(Math.PI * x);
# #   const startBlend = () => { from = cur; blendLeft = BLEND; };
# #   const setPlayLabel = () => { $("play").textContent = (mode === "play" && playing) ? "Tạm dừng" : "Phát"; };

# #   function loadTimeline(D) {
# #     startBlend();
# #     setTimeline(D);
# #     tFrame = 0; mode = "play"; playing = true; setPlayLabel();
# #     seek.max = Math.max(1, D.n - 1);
# #     chips.innerHTML = "";
# #     segEls = D.segments.map((sg) => {
# #       const el = document.createElement("span");
# #       el.className = "chip"; el.textContent = sg.gloss; el.title = sg.video;
# #       el.onclick = () => { tFrame = sg.s; mode = "play"; };
# #       chips.appendChild(el);
# #       return el;
# #     });
# #   }
# #   window.loadTimeline = loadTimeline;
# #   window.__dbg = () => ({ mode, tFrame, playing, blendLeft, n: TL ? TL.n : 0, loaded });

# #   $("play").onclick = () => {
# #     if (TL && mode !== "play") { startBlend(); tFrame = 0; mode = "play"; playing = true; }
# #     else playing = !playing;
# #     setPlayLabel();
# #   };
# #   $("restart").onclick = () => { if (TL) { startBlend(); tFrame = 0; mode = "play"; playing = true; setPlayLabel(); } };
# #   seek.oninput = () => { if (TL) { tFrame = +seek.value; mode = "play"; playing = false; setPlayLabel(); } };
# #   $("speed").onchange = (e) => { opts.speed = +e.target.value; };
# #   $("view").onchange = applyView;
# #   for (const [id, key] of [["o_loop","loop"],["o_fingers","fingers"],["o_legs","legs"],
# #                            ["o_mirror","mirror"],["o_flipz","flipZ"],["o_swap","swapHands"],["o_rest","rest"]]) {
# #     $(id).checked = !!opts[key];
# #     $(id).onchange = (e) => { opts[key] = e.target.checked; };
# #   }
# #   window.addEventListener("keydown", (e) => {
# #     if (e.code === "Space" && e.target.tagName !== "INPUT") { e.preventDefault(); $("play").click(); }
# #   });

# #   // ---------- typing words ----------
# #   const q = $("q"), sug = $("sug");
# #   let labels = [], labelsF = [], modelNote = "", baseStatus = "";
# #   const fold = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").toLowerCase();
# #   const tokenInfo = () => {
# #     const i = Math.max(q.value.lastIndexOf(","), q.value.lastIndexOf("|"), q.value.lastIndexOf(";"));
# #     return { i, text: q.value.slice(i + 1).trim() };
# #   };
# #   const modeSel = $("mode");
# #   function updateMode() {
# #     q.placeholder = modeSel.value === "sentence" ? "Nhập một câu tiếng Việt"
# #                                                   : "Nhập 1 hoặc nhiều từ, cách nhau bằng dấu phẩy: tuần sau, học, không có";
# #     sug.innerHTML = "";
# #   }
# #   modeSel.onchange = updateMode;
# #   updateMode();
# #   function showSuggestions() {
# #     sug.innerHTML = "";
# #     if (modeSel.value !== "gloss") return;
# #     const t = fold(tokenInfo().text);
# #     if (!t || !labels.length) return;
# #     const starts = [], inside = [];
# #     for (let k = 0; k < labels.length && starts.length < 8; k++) {
# #       const p = labelsF[k].indexOf(t);
# #       if (p === 0) starts.push(labels[k]); else if (p > 0 && inside.length < 8) inside.push(labels[k]);
# #     }
# #     for (const lab of starts.concat(inside).slice(0, 8)) {
# #       const el = document.createElement("span");
# #       el.className = "chip"; el.textContent = lab;
# #       el.onmousedown = (e) => {
# #         e.preventDefault();
# #         const i = tokenInfo().i;
# #         q.value = (i >= 0 ? q.value.slice(0, i + 1) + " " : "") + lab + ", ";
# #         q.focus(); showSuggestions();
# #       };
# #       sug.appendChild(el);
# #     }
# #   }
# #   function setStatus(html, cls) { const st = $("status"); st.innerHTML = html; st.className = cls || ""; }
# #   function refreshStatus() { setStatus(baseStatus + (modelNote ? "<br>" + modelNote : ""), modelNote ? "err" : ""); }
# #   function runSentence() {
# #     const text = q.value.trim();
# #     if (!text) return;
# #     sug.innerHTML = "";
# #     const mode = modeSel.value;
# #     setStatus(mode === "sentence" ? "Đang dịch câu thành gloss..." : "Đang xử lý...");
# #     fetch("/api/sentence", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, mode }) })
# #       .then((r) => r.json())
# #       .then((res) => {
# #         const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
# #         const warn = (res.warnings || []).map((w) => '<span class="w"> ⚠ ' + esc(w) + "</span>").join("");
# #         const head = res.glosses ? "<b>Gloss:</b> " + res.glosses.map(esc).join(" | ") +
# #                      (res.translate_ms !== undefined ? " <i>(dịch " + res.translate_ms + " ms)</i>" : "") + "<br>" : "";
# #         if (!res.ok || !res.timeline) { setStatus(head + "Không chạy được: " + esc(res.error || "không có từ nào hợp lệ") + warn, "err"); return; }
# #         loadTimeline(res.timeline);
# #         setStatus(head + res.picks.map((p) => esc(p.gloss) + " → " + esc(p.video)).join(" | ") +
# #                   " &nbsp;(" + res.timeline.n + " khung, " + (res.timeline.n / res.timeline.fps).toFixed(1) + " s)" + warn);
# #       })
# #       .catch((e) => fail("Lỗi kết nối tới máy chủ: " + e));
# #   }
# #   q.addEventListener("input", showSuggestions);
# #   q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); runSentence(); } });
# #   $("run").onclick = runSentence;
# #   if (APP_MODE) {
# #     fetch("/api/glosses").then((r) => r.json()).then((a) => { labels = a; labelsF = a.map(fold); }).catch(() => {});
# #     const poll = (k) => fetch("/api/info").then((r) => r.json()).then((info) => {      // is the sentence -> gloss model ready?
# #       const opt = modeSel.querySelector('option[value="sentence"]');
# #       if (info.model === "unavailable") {
# #         opt.disabled = true; opt.textContent = "Câu (model chưa dùng được)"; opt.title = info.error || "";
# #         modeSel.value = "gloss"; updateMode();
# #         modelNote = "Model dịch câu chưa dùng được: " + String(info.error || "").replace(/[<>&]/g, "") + " — vẫn nhập gloss trực tiếp được.";
# #         if (loaded) refreshStatus();
# #       } else if (info.model === "loading") {
# #         opt.textContent = "Câu (đang nạp model...)";
# #         if (k < 120) setTimeout(() => poll(k + 1), 1500);
# #       } else { opt.textContent = "Câu"; }
# #     }).catch(() => {});
# #     poll(0);
# #     q.focus();
# #   }

# #   // ---------- model ----------
# #   const onModel = (gltf) => {
# #     const model = gltf.scene;
# #     model.traverse((o) => { if (o.isMesh) o.frustumCulled = false; });
# #     scene.add(model);
# #     const info = setupModel(model);
# #     let ft = computeFit();                          // size the avatar from its skeleton: feet -> head bone = 1.55 m
# #     model.scale.multiplyScalar(1.55 / Math.max(1e-6, ft.headY - ft.footY));
# #     ft = computeFit();
# #     model.position.y -= ft.footY;
# #     if (ft.hips) { model.position.x -= ft.hips.x; model.position.z -= ft.hips.z; }
# #     fit = computeFit();
# #     applyView();
# #     loaded = true;
# #     baseStatus = "Xương: " + info.bones + " | xương ngón tay: " + info.fingerBases + "/10" +
# #       (info.fingerBases < 10 ? " (mô hình thiếu xương ngón tay: ngón sẽ không cử động)" : "") +
# #       (APP_MODE ? " | Gõ ở ô trên rồi nhấn Enter." : "");
# #     refreshStatus();
# #   };
# #   const onModelError = (err) => fail("Không đọc được mô hình Xbot: " + (err && err.message ? err.message : err));
# #   try {
# #     if (GLB_URL) new THREE.GLTFLoader().load(GLB_URL, onModel, undefined, onModelError);
# #     else {
# #       const bin = atob(GLB_B64), buf = new Uint8Array(bin.length);
# #       for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
# #       new THREE.GLTFLoader().parse(buf.buffer, "", onModel, onModelError);
# #     }
# #   } catch (e) { fail("Lỗi nạp mô hình: " + e); }
# #   if (DATA.n > 0) loadTimeline(DATA);               // static .html mode: the sentence is already inside the page

# #   // ---------- render loop ----------
# #   let last = performance.now();
# #   function tick(now) {
# #     const dt = Math.min(0.1, (now - last) / 1000);
# #     last = now;
# #     if (TL && mode === "play" && playing) {
# #       tFrame += dt * TL.fps * opts.speed;
# #       if (tFrame >= TL.n - 1) {
# #         if (opts.loop) { startBlend(); tFrame = 0; }
# #         else { tFrame = TL.n - 1; mode = "hold"; holdLeft = 0.5; setPlayLabel(); }
# #       }
# #     } else if (mode === "hold") {
# #       holdLeft -= dt;
# #       if (holdLeft <= 0 && opts.rest) { startBlend(); mode = "idle"; }
# #     }
# #     const target = (TL && (mode === "play" || mode === "hold")) ? rawAt(TL, tFrame) : IDLE_RAW;
# #     if (blendLeft > 0) { blendLeft = Math.max(0, blendLeft - dt); cur = blendRaw(from, target, ease(1 - blendLeft / BLEND)); }
# #     else cur = target;
# #     if (loaded) applyRaw(cur, dt);

# #     const fi = Math.floor(tFrame);
# #     const showing = TL && (mode === "play" || mode === "hold");
# #     const idx = showing ? TL.segments.findIndex((sg) => fi >= sg.s && fi < sg.e) : -1;
# #     const ci = idx >= 0 ? idx : (showing ? TL.segments.length - 1 : -1);
# #     $("caption").textContent = ci >= 0 ? TL.segments[ci].gloss : "";
# #     segEls.forEach((el, i) => el.classList.toggle("on", i === ci));
# #     if (TL) {
# #       seek.value = fi;
# #       $("time").textContent = (tFrame / TL.fps).toFixed(1) + " / " + (TL.n / TL.fps).toFixed(1) + " s";
# #     }
# #     controls.update();
# #     renderer.render(scene, camera);
# #     requestAnimationFrame(tick);
# #   }
# #   requestAnimationFrame(tick);
# # })();
# # </script>
# # </body>
# # </html>
# # '''


# # def render_app_page(title="Xbot - ngôn ngữ ký hiệu", scripts=None):
# #     """The interactive page served by sign_app.py (model loaded from /xbot.glb, sentences from /api/sentence)."""
# #     empty = {"fps": 30, "n": 0, "body": [], "lh": [], "rh": [], "lv": [], "rv": [], "segments": []}
# #     html = (HTML_TEMPLATE.replace("__TITLE__", title).replace("__DATA_JSON__", json.dumps(empty))
# #             .replace("__GLB_B64__", "").replace("__GLB_URL__", "/xbot.glb").replace("__APP_MODE__", "true"))
# #     return html.encode("utf-8")


# # def write_html(timeline, xbot_path, out_path, title):
# #     glb = Path(xbot_path).read_bytes()
# #     data_json = json.dumps(timeline, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
# #     html = (HTML_TEMPLATE
# #             .replace("__TITLE__", title.replace("<", "&lt;"))
# #             .replace("__DATA_JSON__", data_json)
# #             .replace("__GLB_B64__", base64.b64encode(glb).decode("ascii"))
# #             .replace("__GLB_URL__", "")
# #             .replace("__APP_MODE__", "false"))
# #     out = Path(out_path)
# #     out.parent.mkdir(parents=True, exist_ok=True)
# #     out.write_text(html, encoding="utf-8")
# #     return out


# # # =====================================================================
# # # 7. Command line
# # # =====================================================================
# # def build_parser():
# #     p = argparse.ArgumentParser(
# #         description="Chuỗi gloss -> avatar Xbot chuyển động liên tục (file HTML độc lập).")
# #     g = p.add_argument_group("đầu vào")
# #     g.add_argument("--glosses", nargs="+", help='Danh sách gloss, ví dụ: --glosses "bạn" "đi học" "có không"')
# #     g.add_argument("--sentence", help='Các gloss ngăn cách bằng dấu |, ví dụ: "bạn | đi học | có không"')
# #     g.add_argument("--glosses-file", help="File .json (list) hoặc .txt (mỗi dòng 1 gloss)")
# #     g = p.add_argument_group("đường dẫn")
# #     g.add_argument("--labels", help="File ánh xạ VIDEO/LABEL (csv, tsv, txt, xlsx, json)")
# #     g.add_argument("--videos", default=DEFAULT_VIDEOS, help="Thư mục chứa các video của dataset")
# #     g.add_argument("--xbot", default=DEFAULT_XBOT, help="File Xbot.glb")
# #     g.add_argument("--cache", default=DEFAULT_CACHE, help="Thư mục lưu tọa độ đã tính (.npz)")
# #     g.add_argument("--out", default=DEFAULT_OUT, help="File HTML đầu ra")
# #     g = p.add_argument_group("chọn video")
# #     g.add_argument("--region", default="B,T,N", help="Thứ tự ưu tiên giọng vùng: B=Bắc, T=Trung, N=Nam")
# #     g.add_argument("--search", help="Tìm nhãn chứa chuỗi này (không cần dấu) rồi thoát")
# #     g.add_argument("--precompute-all", action="store_true",
# #                    help="Tính trước tọa độ cho mọi gloss (lâu, chạy một lần)")
# #     g = p.add_argument_group("chuyển động")
# #     g.add_argument("--fps", type=float, default=30.0)
# #     g.add_argument("--transition", type=float, default=0.25, help="Giây chuyển tiếp giữa 2 từ")
# #     g.add_argument("--hold", type=float, default=0.2, help="Giây giữ tư thế đầu/cuối")
# #     g.add_argument("--smooth-body", type=float, default=1.5, help="Độ mượt thân (khung hình, 0 = tắt)")
# #     g.add_argument("--smooth-hands", type=float, default=1.0, help="Độ mượt ngón tay (0 = tắt)")
# #     g.add_argument("--hand-gap", type=int, default=6, help="Nội suy khi mất tay tối đa N khung")
# #     g.add_argument("--no-trim", action="store_true", help="Không cắt đoạn tay buông ở đầu/cuối video")
# #     g.add_argument("--rest-threshold", type=float, default=0.10,
# #                    help="Cổ tay phải cao hơn hông bao nhiêu mét để tính là đang ký")
# #     g.add_argument("--complexity", type=int, default=1, choices=[0, 1, 2],
# #                    help="Độ chính xác MediaPipe Pose (2 = chính xác nhất, chậm nhất)")
# #     p.add_argument("--open", action="store_true", help="Mở file HTML sau khi tạo")
# #     return p


# # def get_glosses(args):
# #     if args.glosses:
# #         return [g for g in args.glosses if g.strip()]
# #     if args.sentence:
# #         return [g.strip() for g in args.sentence.split("|") if g.strip()]
# #     if args.glosses_file:
# #         txt = read_text_auto(args.glosses_file)
# #         if args.glosses_file.lower().endswith(".json"):
# #             return [str(g) for g in json.loads(txt)]
# #         return [l.strip() for l in txt.splitlines() if l.strip()]
# #     return []


# # def main(argv=None, detector_factory=None):
# #     args = build_parser().parse_args(argv)
# #     videos_dir = Path(args.videos)

# #     labels = args.labels or find_labels_file(videos_dir)
# #     if not labels or not Path(labels).exists():
# #         print("Không tìm thấy file nhãn. Hãy chỉ rõ bằng --labels \"đường\\dẫn\\file.csv\"")
# #         return 2
# #     records = load_records(labels)
# #     index = GlossIndex(records, args.region.split(","))
# #     print(f"Đã đọc {len(records)} video / {len(index.by_key)} khóa tra cứu từ: {labels}")

# #     if args.search:
# #         hits = index.search(args.search)
# #         print(f'\nCác nhãn chứa "{args.search}" ({len(hits)} kết quả đầu):')
# #         for r in hits:
# #             print(f"  {r['video']:<14} {r['label']}")
# #         return 0

# #     if detector_factory is None:
# #         detector_factory = lambda: MediaPipeDetector(args.complexity)

# #     if args.precompute_all:
# #         picks = {}
# #         for rec in index.recs:
# #             key = norm(rec["label"])
# #             if key not in picks:
# #                 picks[key] = index.choose(index.lookup(rec["label"]))[0]
# #         todo = sorted(picks.values(), key=lambda r: natural_key(r["stem"]))
# #         print(f"Tính trước {len(todo)} video (mỗi gloss một video)...")
# #         for i, rec in enumerate(todo, 1):
# #             vp = videos_dir / rec["video"]
# #             try:
# #                 _, hit = get_clip_data(vp, args.cache, detector_factory)
# #                 print(f"[{i}/{len(todo)}] {rec['video']} {'(đã có)' if hit else 'xong'}")
# #             except Exception as e:
# #                 print(f"[{i}/{len(todo)}] {rec['video']} LỖI: {e}")
# #         return 0

# #     glosses = get_glosses(args)
# #     if not glosses:
# #         raw = input('Nhập các gloss, ngăn cách bằng dấu | (ví dụ: bạn | đi học | có không): ')
# #         glosses = [g.strip() for g in raw.split("|") if g.strip()]
# #     if not glosses:
# #         print("Chưa có gloss nào.")
# #         return 2

# #     # ---- gloss -> video ----
# #     picks, problems = [], []
# #     for g in glosses:
# #         found, missing = index.resolve_one(g)
# #         picks += found
# #         for w in missing:
# #             sug = index.suggest(w)
# #             problems.append(f'Không có gloss "{w}"' + (f" (gần giống: {', '.join(sug)})" if sug else ""))
# #     print("\nChuỗi gloss -> video:")
# #     for g, rec, note in picks:
# #         print(f"  {g:<18} -> {rec['video']:<14} [{rec['label']}]" + (f"  ({note})" if note else ""))
# #     for p in problems:
# #         print("  CẢNH BÁO:", p)
# #     if not picks:
# #         return 1

# #     # ---- landmarks (cached) ----
# #     clips = []
# #     for i, (g, rec, _) in enumerate(picks, 1):
# #         vp = videos_dir / rec["video"]
# #         cache_file = Path(args.cache) / (rec["stem"] + ".npz")
# #         if not vp.exists() and not cache_file.exists():
# #             print(f"  CẢNH BÁO: không thấy video {vp}")
# #             continue
# #         try:
# #             raw, hit = get_clip_data(vp, args.cache, detector_factory)
# #         except Exception as e:
# #             print(f"  CẢNH BÁO: lỗi với {rec['video']}: {e}")
# #             continue
# #         clip, ok = process_clip(raw, args.fps, args)
# #         if clip is None:
# #             print(f"  CẢNH BÁO: {rec['video']} chỉ nhận diện được {ok:.0%} khung hình, bỏ qua")
# #             continue
# #         hands_ok = [float((~np.isnan(clip[k].reshape(len(clip[k]), -1)).any(axis=1)).mean())
# #                     for k in ("lh", "rh")]
# #         print(f"  [{i}/{len(picks)}] {rec['video']}: {len(clip['body'])} khung ({len(clip['body'])/args.fps:.1f}s), "
# #               f"có tay trái {hands_ok[0]:.0%} / tay phải {hands_ok[1]:.0%}" + ("" if hit else "  (vừa tính xong, đã lưu cache)"))
# #         clip.update({"gloss": g, "video": rec["video"]})
# #         clips.append(clip)
# #     if not clips:
# #         print("Không có video nào dùng được.")
# #         return 1

# #     # ---- one continuous timeline -> html ----
# #     timeline = assemble(clips, args.fps, args.transition, args.hold)
# #     if not Path(args.xbot).exists():
# #         print(f"Không thấy file Xbot: {args.xbot}  (dùng --xbot để chỉ đường dẫn)")
# #         return 2
# #     out = write_html(timeline, args.xbot, args.out, "Avatar: " + " | ".join(c["gloss"] for c in clips))
# #     print(f"\nXong: {timeline['n']} khung hình = {timeline['n']/args.fps:.1f} giây")
# #     print(f"Mở file này (bấm đúp): {out.resolve()}")
# #     if args.open:
# #         webbrowser.open(out.resolve().as_uri())
# #     return 0


# # if __name__ == "__main__":
# #     sys.exit(main())




















# # #!/usr/bin/env python3
# # # -*- coding: utf-8 -*-
# # """
# # sign_to_avatar.py
# # =================
# # Gloss list  ->  videos of the dataset  ->  3D landmarks (cached .npz)
# #             ->  ONE continuous animation of the Xbot avatar (standalone .html).

# # Example:
# #     python sign_to_avatar.py --glosses "bạn" "đi học" "có không"
# #     python sign_to_avatar.py --sentence "bạn | đi học | có không" --open
# #     python sign_to_avatar.py --search "địa chỉ"

# # The output .html is a single file: double-click it, no server / localhost needed.
# # (It only needs Internet once per open, to load three.js from a CDN.)
# # """
# # import argparse
# # import base64
# # import csv
# # import difflib
# # import io
# # import json
# # import os
# # import re
# # import sys
# # import unicodedata
# # import webbrowser
# # from pathlib import Path

# # import numpy as np

# # # =====================================================================
# # # DEFAULTS (edit these once, then you never need to type the paths)
# # # =====================================================================
# # DEFAULT_VIDEOS = r"C:\Users\ADMIN\qh\vsl-vietnamese-sign-languages\versions\5\Dataset\Videos"
# # DEFAULT_XBOT = os.path.join("frontend_dis", "models", "Xbot.glb")
# # DEFAULT_CACHE = "landmark_cache"
# # DEFAULT_OUT = os.path.join("output", "sentence.html")

# # CACHE_VERSION = 1
# # VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")

# # BODY_NAMES = [
# #     "Hips", "Spine1", "Spine2", "Neck", "Head",
# #     "LeftArm", "LeftForeArm", "LeftHand",
# #     "RightArm", "RightForeArm", "RightHand",
# #     "LeftUpLeg", "LeftLeg", "LeftFoot",
# #     "RightUpLeg", "RightLeg", "RightFoot",
# # ]

# # try:  # make Vietnamese text safe to print on any console
# #     sys.stdout.reconfigure(errors="replace")
# #     sys.stderr.reconfigure(errors="replace")
# # except Exception:
# #     pass


# # # =====================================================================
# # # 1. Text helpers
# # # =====================================================================
# # def norm(s):
# #     """NFC + lower-case + collapsed spaces."""
# #     return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s)).strip().lower())


# # def strip_accents(s):
# #     s = norm(s).replace("đ", "d")
# #     s = unicodedata.normalize("NFD", s)
# #     return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# # def without_parens(s):
# #     return norm(re.sub(r"\([^)]*\)", " ", str(s)))


# # def natural_key(s):
# #     return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


# # VIDEO_RE = re.compile(r"^(?P<base>.*\d)(?P<reg>[NTBntb])?$")


# # def parse_video(name):
# #     """'D0001N.mp4' -> ('D0001', 'N');  'D0002.mp4' -> ('D0002', '')."""
# #     stem = Path(str(name).strip()).stem
# #     m = VIDEO_RE.match(stem)
# #     if m:
# #         return m.group("base"), (m.group("reg") or "").upper()
# #     return stem, ""


# # def label_keys(label):
# #     """All the lookup keys under which a dataset label can be found."""
# #     plain = without_parens(label)
# #     parts = {norm(label), plain}
# #     for p in re.split(r"\s*[;/,]\s*", plain):
# #         if p.strip():
# #             parts.add(norm(p))
# #     keys = set()
# #     for p in parts:
# #         if p:
# #             keys.add(p)
# #             keys.add(strip_accents(p))
# #     return keys


# # # =====================================================================
# # # 2. Reading the label file (csv / tsv / txt / xlsx / json)
# # # =====================================================================
# # def read_text_auto(path):
# #     raw = Path(path).read_bytes()
# #     if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:200]:
# #         return raw.decode("utf-16", errors="replace")
# #     try:
# #         return raw.decode("utf-8-sig")
# #     except UnicodeDecodeError:
# #         return raw.decode("cp1258", errors="replace")


# # def _pick_columns(header):
# #     h = [norm(c) for c in header]
# #     vi = next((i for i, c in enumerate(h) if c in ("video", "file", "filename", "name")), None)
# #     li = next((i for i, c in enumerate(h) if c in ("label", "gloss", "nhan", "nhãn", "text")), None)
# #     return vi, li


# # def load_records(path):
# #     """Return [(video_name, label), ...] from any supported file type."""
# #     path = str(path)
# #     ext = Path(path).suffix.lower()

# #     if ext == ".json":
# #         data = json.loads(read_text_auto(path))
# #         recs = []
# #         if isinstance(data, dict):
# #             for gloss, vids in data.items():
# #                 if isinstance(vids, (str, dict)):
# #                     vids = [vids]
# #                 for v in vids:
# #                     recs.append((v["video"] if isinstance(v, dict) else v, gloss))
# #         else:
# #             for item in data:
# #                 if isinstance(item, dict):
# #                     low = {norm(k): v for k, v in item.items()}
# #                     recs.append((low.get("video") or low.get("file"),
# #                                  low.get("label") or low.get("gloss")))
# #                 else:
# #                     recs.append((item[0], item[1]))
# #         return [(str(v), str(l)) for v, l in recs if v and l]

# #     if ext in (".xlsx", ".xls", ".xlsm"):
# #         import pandas as pd  # needs openpyxl for .xlsx
# #         df = pd.read_excel(path, dtype=str).fillna("")
# #         rows = [list(df.columns)] + df.values.tolist()
# #     else:
# #         text = read_text_auto(path)
# #         first = text.splitlines()[0] if text else ""
# #         delim = max(["\t", ",", ";"], key=first.count)
# #         rows = list(csv.reader(io.StringIO(text), delimiter=delim))

# #     rows = [r for r in rows if r and any(str(c).strip() for c in r)]
# #     if not rows:
# #         return []
# #     vi, li = _pick_columns(rows[0])
# #     start = 1
# #     if vi is None or li is None:  # no header: first two columns
# #         vi, li = 0, 1
# #         start = 0 if Path(str(rows[0][0])).suffix.lower() in VIDEO_EXTS else 1
# #     out = []
# #     for r in rows[start:]:
# #         if len(r) > max(vi, li) and str(r[vi]).strip() and str(r[li]).strip():
# #             out.append((str(r[vi]).strip(), str(r[li]).strip()))
# #     return out


# # def find_labels_file(videos_dir):
# #     vd = Path(videos_dir)
# #     exts = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json")
# #     cands = []
# #     for d in (vd, vd.parent, vd.parent.parent):
# #         if d.is_dir():
# #             cands += [p for p in d.iterdir() if p.suffix.lower() in exts]
# #     hits = [p for p in cands if "label" in p.name.lower()]
# #     if len(hits) >= 1:
# #         return str(sorted(hits, key=lambda p: len(str(p)))[0])
# #     return None


# # # =====================================================================
# # # 3. Gloss index: label -> video
# # # =====================================================================
# # class GlossIndex:
# #     def __init__(self, records, region_pref=("B", "T", "N")):
# #         self.region_pref = [r.upper() for r in region_pref]
# #         self.recs = []
# #         self.by_key = {}
# #         self.by_stem = {}
# #         for video, label in records:
# #             base, reg = parse_video(video)
# #             rec = {"video": Path(video).name, "stem": Path(video).stem,
# #                    "base": base, "region": reg, "label": label}
# #             self.recs.append(rec)
# #             self.by_stem[norm(rec["stem"])] = rec
# #             for k in label_keys(label):
# #                 self.by_key.setdefault(k, []).append(rec)

# #     def lookup(self, text):
# #         for v in (norm(text), without_parens(text),
# #                   strip_accents(text), strip_accents(without_parens(text))):
# #             if v and v in self.by_key:
# #                 return self.by_key[v]
# #         return []

# #     def choose(self, recs):
# #         """One video for a gloss: first sign (lowest id), preferred region."""
# #         groups = {}
# #         for r in recs:
# #             groups.setdefault(r["base"], []).append(r)
# #         bases = sorted(groups, key=natural_key)
# #         group = groups[bases[0]]
# #         group.sort(key=lambda r: (self.region_pref.index(r["region"])
# #                                   if r["region"] in self.region_pref else 99,
# #                                   natural_key(r["stem"])))
# #         return group[0], len(bases) - 1

# #     def resolve_one(self, gloss):
# #         """Return (list of (gloss_text, rec, note), list of missing words)."""
# #         g = str(gloss).strip()
# #         if not g:
# #             return [], []
# #         # a video id typed directly, e.g. "D0001T"
# #         rec = self.by_stem.get(norm(Path(g).stem))
# #         if rec is not None and re.fullmatch(r"[dD]\d+[NTBntb]?(\.\w+)?", g):
# #             return [(g, rec, "")], []

# #         recs = self.lookup(g)
# #         if recs:
# #             rec, extra = self.choose(recs)
# #             note = f"còn {extra} cách ký khác" if extra > 0 else ""
# #             return [(g, rec, note)], []

# #         # not a known gloss: split into the longest known pieces
# #         words = norm(g).split()
# #         found, missing, i = [], [], 0
# #         while i < len(words):
# #             for j in range(len(words), i, -1):
# #                 phrase = " ".join(words[i:j])
# #                 recs = self.lookup(phrase)
# #                 if recs:
# #                     rec, extra = self.choose(recs)
# #                     found.append((phrase, rec, f'tách từ "{g}"'))
# #                     i = j
# #                     break
# #             else:
# #                 missing.append(words[i])
# #                 i += 1
# #         if not found:
# #             return [], [g]
# #         return found, missing

# #     def suggest(self, text, n=4):
# #         pool = {}
# #         for k, recs in self.by_key.items():
# #             if strip_accents(k) == k:
# #                 pool[k] = recs[0]["label"]
# #         close = difflib.get_close_matches(strip_accents(text), list(pool), n=n, cutoff=0.6)
# #         return [pool[c] for c in close]

# #     def search(self, text, limit=30):
# #         t = strip_accents(text)
# #         hits = [r for r in self.recs if t in strip_accents(r["label"])]
# #         return sorted(hits, key=lambda r: natural_key(r["stem"]))[:limit]


# # # =====================================================================
# # # 4. Landmark extraction (MediaPipe) + cache
# # # =====================================================================
# # def assign_hands(hands, left_wrist, right_wrist):
# #     """
# #     hands: [(image_wrist_xy, world_21x3, label)], wrists in normalised image coords.
# #     Decide which detected hand is the person's LEFT / RIGHT by comparing with the
# #     body-pose wrists (more reliable than the handedness label for un-mirrored video).
# #     """
# #     res = {"L": None, "R": None}
# #     if not hands:
# #         return res

# #     def d(a, b):
# #         return float(np.hypot(a[0] - b[0], a[1] - b[1]))

# #     if left_wrist is not None and right_wrist is not None:
# #         if len(hands) == 1:
# #             h = hands[0]
# #             res["L" if d(h[0], left_wrist) <= d(h[0], right_wrist) else "R"] = h[1]
# #         else:
# #             h0, h1 = hands[0], hands[1]
# #             a = d(h0[0], left_wrist) + d(h1[0], right_wrist)
# #             b = d(h0[0], right_wrist) + d(h1[0], left_wrist)
# #             if a <= b:
# #                 res["L"], res["R"] = h0[1], h1[1]
# #             else:
# #                 res["L"], res["R"] = h1[1], h0[1]
# #     else:  # no body wrists: use the label (MediaPipe assumes a mirrored image -> swap)
# #         for h in hands:
# #             res["R" if h[2] == "Left" else "L"] = h[1]
# #     return res


# # class MediaPipeDetector:
# #     """Pose (33 world landmarks) + Hands (21 world landmarks each), one video at a time."""

# #     def __init__(self, complexity=1):
# #         import mediapipe as mp
# #         self.pose = mp.solutions.pose.Pose(
# #             static_image_mode=False, model_complexity=complexity, smooth_landmarks=True,
# #             min_detection_confidence=0.5, min_tracking_confidence=0.5)
# #         self.hands = mp.solutions.hands.Hands(
# #             static_image_mode=False, max_num_hands=2, model_complexity=1,
# #             min_detection_confidence=0.5, min_tracking_confidence=0.5)

# #     def __enter__(self):
# #         return self

# #     def __exit__(self, *a):
# #         self.pose.close()
# #         self.hands.close()
# #         return False

# #     def process(self, rgb):
# #         pr = self.pose.process(rgb)
# #         hr = self.hands.process(rgb)
# #         pose_world = left_w = right_w = None
# #         if pr.pose_world_landmarks:
# #             pose_world = np.array([[l.x, l.y, l.z] for l in pr.pose_world_landmarks.landmark],
# #                                   dtype=np.float32)
# #         if pr.pose_landmarks:
# #             lm = pr.pose_landmarks.landmark
# #             left_w, right_w = (lm[15].x, lm[15].y), (lm[16].x, lm[16].y)
# #         hands = []
# #         if hr.multi_hand_world_landmarks and hr.multi_hand_landmarks:
# #             for wl, il, hd in zip(hr.multi_hand_world_landmarks,
# #                                   hr.multi_hand_landmarks, hr.multi_handedness):
# #                 world = np.array([[l.x, l.y, l.z] for l in wl.landmark], dtype=np.float32)
# #                 hands.append(((il.landmark[0].x, il.landmark[0].y), world,
# #                               hd.classification[0].label))
# #         return {"pose": pose_world, "left_wrist": left_w, "right_wrist": right_w, "hands": hands}


# # def extract_video(video_path, detector_factory, target_width=640):
# #     """Run the detector on every frame. Returns dict of arrays (NaN = not detected)."""
# #     import cv2
# #     cap = cv2.VideoCapture(str(video_path))
# #     if not cap.isOpened():
# #         raise IOError(f"Không mở được video: {video_path}")
# #     fps = cap.get(cv2.CAP_PROP_FPS)
# #     if not fps or fps != fps or fps <= 1:
# #         fps = 30.0
# #     pose_l, lh_l, rh_l = [], [], []
# #     nan_pose = np.full((33, 3), np.nan, np.float32)
# #     nan_hand = np.full((21, 3), np.nan, np.float32)
# #     with detector_factory() as det:
# #         while True:
# #             ok, frame = cap.read()
# #             if not ok:
# #                 break
# #             h, w = frame.shape[:2]
# #             if w != target_width and w > 0:
# #                 frame = cv2.resize(frame, (target_width, int(h * target_width / w)))
# #             rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
# #             r = det.process(rgb)
# #             pose_l.append(r["pose"] if r["pose"] is not None else nan_pose)
# #             a = assign_hands(r["hands"], r["left_wrist"], r["right_wrist"])
# #             lh_l.append(a["L"] if a["L"] is not None else nan_hand)
# #             rh_l.append(a["R"] if a["R"] is not None else nan_hand)
# #     cap.release()
# #     if not pose_l:
# #         raise IOError(f"Video rỗng: {video_path}")
# #     return {"pose": np.stack(pose_l).astype(np.float32),
# #             "lhand": np.stack(lh_l).astype(np.float32),
# #             "rhand": np.stack(rh_l).astype(np.float32),
# #             "fps": float(fps)}


# # def get_clip_data(video_path, cache_dir, detector_factory):
# #     cache_path = Path(cache_dir) / (Path(video_path).stem + ".npz")
# #     if cache_path.exists():
# #         try:
# #             d = np.load(cache_path)
# #             if int(d["version"]) == CACHE_VERSION:
# #                 data = {k: d[k] for k in ("pose", "lhand", "rhand")}
# #                 data["fps"] = float(d["fps"])
# #                 return data, True
# #         except Exception:
# #             pass
# #     data = extract_video(video_path, detector_factory)
# #     cache_path.parent.mkdir(parents=True, exist_ok=True)
# #     np.savez_compressed(cache_path, pose=data["pose"], lhand=data["lhand"],
# #                         rhand=data["rhand"], fps=data["fps"], version=CACHE_VERSION)
# #     return data, False


# # # =====================================================================
# # # 5. Clean-up: resample, fill gaps, smooth, trim, join
# # # =====================================================================
# # def resample(arr, src_fps, dst_fps):
# #     T = len(arr)
# #     if T < 2 or abs(src_fps - dst_fps) < 1e-3:
# #         return arr
# #     new_T = max(2, int(round((T - 1) * dst_fps / src_fps)) + 1)
# #     t = np.linspace(0, T - 1, new_T)
# #     i0 = np.floor(t).astype(int)
# #     i1 = np.minimum(i0 + 1, T - 1)
# #     a = (t - i0).reshape((-1,) + (1,) * (arr.ndim - 1))
# #     return arr[i0] * (1 - a) + arr[i1] * a   # NaN stays NaN if either neighbour is missing


# # def fill_gaps(arr, max_gap, hold_edges):
# #     T = len(arr)
# #     flat = arr.reshape(T, -1).astype(np.float64)
# #     valid = ~np.isnan(flat).any(axis=1)
# #     idx = np.where(valid)[0]
# #     if len(idx) == 0:
# #         return arr
# #     out = flat.copy()
# #     for a, b in zip(idx[:-1], idx[1:]):
# #         gap = b - a - 1
# #         if 0 < gap <= max_gap:
# #             for k in range(1, gap + 1):
# #                 w = k / (gap + 1)
# #                 out[a + k] = flat[a] * (1 - w) + flat[b] * w
# #     if hold_edges:
# #         out[:idx[0]] = flat[idx[0]]
# #         out[idx[-1] + 1:] = flat[idx[-1]]
# #     return out.reshape(arr.shape).astype(np.float32)


# # def hold_last_valid(arr):
# #     """Replace remaining NaN frames by the previous (or next) valid frame."""
# #     T = len(arr)
# #     flat = arr.reshape(T, -1).copy()
# #     valid = ~np.isnan(flat).any(axis=1)
# #     if not valid.any():
# #         return arr
# #     last = None
# #     for i in range(T):
# #         if valid[i]:
# #             last = flat[i].copy()
# #         elif last is not None:
# #             flat[i] = last
# #     first = np.where(valid)[0][0]
# #     flat[:first] = flat[first]
# #     return flat.reshape(arr.shape)


# # def smooth_nan(arr, sigma):
# #     """Gaussian smoothing along time; invalid (NaN) frames stay invalid."""
# #     T = len(arr)
# #     if sigma <= 0 or T < 2:
# #         return arr
# #     flat = arr.reshape(T, -1).astype(np.float64)
# #     valid = ~np.isnan(flat).any(axis=1)
# #     if not valid.any():
# #         return arr
# #     i = np.arange(T)
# #     W = np.exp(-0.5 * ((i[:, None] - i[None, :]) / sigma) ** 2) * valid[None, :]
# #     num = W @ np.where(valid[:, None], flat, 0.0)
# #     den = np.maximum(W.sum(axis=1, keepdims=True), 1e-9)
# #     out = num / den
# #     out[~valid] = np.nan
# #     return out.reshape(arr.shape).astype(np.float32)


# # def body_keypoints(pose):
# #     """(T,33,3) MediaPipe pose -> (T,17,3) avatar keypoints (order = BODY_NAMES)."""
# #     hips = (pose[:, 23] + pose[:, 24]) / 2
# #     neck = (pose[:, 11] + pose[:, 12]) / 2
# #     head = (pose[:, 7] + pose[:, 8]) / 2
# #     spine1 = hips + (neck - hips) / 3
# #     spine2 = hips + (neck - hips) * 2 / 3
# #     kp = [hips, spine1, spine2, neck, head,
# #           pose[:, 11], pose[:, 13], pose[:, 15],
# #           pose[:, 12], pose[:, 14], pose[:, 16],
# #           pose[:, 23], pose[:, 25], pose[:, 27],
# #           pose[:, 24], pose[:, 26], pose[:, 28]]
# #     return np.stack(kp, axis=1).astype(np.float32)


# # def active_range(pose, threshold, pad):
# #     """Frames where at least one wrist is clearly above the hips (= signing)."""
# #     T = len(pose)
# #     hips_y = (pose[:, 23, 1] + pose[:, 24, 1]) / 2
# #     wrist_y = np.minimum(pose[:, 15, 1], pose[:, 16, 1])   # MediaPipe y points DOWN
# #     idx = np.where(wrist_y < hips_y - threshold)[0]
# #     if len(idx) == 0:
# #         return 0, T
# #     return max(0, int(idx[0]) - pad), min(T, int(idx[-1]) + pad + 1)


# # def process_clip(raw, fps, args):
# #     pose = resample(raw["pose"], raw["fps"], fps)
# #     lh = resample(raw["lhand"], raw["fps"], fps)
# #     rh = resample(raw["rhand"], raw["fps"], fps)

# #     ok_ratio = float((~np.isnan(pose.reshape(len(pose), -1)).any(axis=1)).mean())
# #     if ok_ratio < 0.3:
# #         return None, ok_ratio

# #     pose = fill_gaps(pose, max_gap=int(fps * 0.6), hold_edges=True)
# #     pose = hold_last_valid(pose)
# #     pose = smooth_nan(pose, args.smooth_body)
# #     lh = smooth_nan(fill_gaps(lh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)
# #     rh = smooth_nan(fill_gaps(rh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)

# #     if not args.no_trim:
# #         a, b = active_range(pose, args.rest_threshold, int(round(fps * 0.12)))
# #         pose, lh, rh = pose[a:b], lh[a:b], rh[a:b]
# #     return {"body": body_keypoints(pose), "lh": lh, "rh": rh}, ok_ratio


# # def _ease(w):
# #     return 0.5 - 0.5 * np.cos(np.pi * w)


# # def assemble(clips, fps, transition_s, hold_s):
# #     """clips: [{gloss, video, body, lh, rh}] -> one timeline."""
# #     ntr = max(0, int(round(transition_s * fps)))
# #     hold = max(0, int(round(hold_s * fps)))
# #     B, LH, RH, segs = [], [], [], []
# #     cursor = 0

# #     def add(body, lh, rh):
# #         nonlocal cursor
# #         B.append(body)
# #         LH.append(lh)
# #         RH.append(rh)
# #         cursor += len(body)

# #     for i, c in enumerate(clips):
# #         seg_start = cursor
# #         if i == 0 and hold:
# #             add(np.repeat(c["body"][:1], hold, 0), np.repeat(c["lh"][:1], hold, 0),
# #                 np.repeat(c["rh"][:1], hold, 0))
# #         if i > 0 and ntr:
# #             p = clips[i - 1]
# #             w = _ease(np.arange(1, ntr + 1) / (ntr + 1)).reshape(-1, 1, 1)
# #             body = p["body"][-1][None] * (1 - w) + c["body"][0][None] * w
# #             lh = p["lh"][-1][None] * (1 - w) + c["lh"][0][None] * w     # NaN if either is missing
# #             rh = p["rh"][-1][None] * (1 - w) + c["rh"][0][None] * w
# #             add(body, lh, rh)
# #         add(c["body"], c["lh"], c["rh"])
# #         if i == len(clips) - 1 and hold:
# #             add(np.repeat(c["body"][-1:], hold, 0), np.repeat(c["lh"][-1:], hold, 0),
# #                 np.repeat(c["rh"][-1:], hold, 0))
# #         segs.append({"s": seg_start, "e": cursor, "gloss": c["gloss"], "video": c["video"]})

# #     body = np.concatenate(B).astype(np.float64)
# #     lh = np.concatenate(LH).astype(np.float64)
# #     rh = np.concatenate(RH).astype(np.float64)
# #     lv = (~np.isnan(lh.reshape(len(lh), -1)).any(axis=1)).astype(int)
# #     rv = (~np.isnan(rh.reshape(len(rh), -1)).any(axis=1)).astype(int)
# #     lh = np.nan_to_num(lh, nan=0.0)
# #     rh = np.nan_to_num(rh, nan=0.0)
# #     return {"fps": fps, "n": int(len(body)),
# #             "body": np.round(body, 4).ravel().tolist(),
# #             "lh": np.round(lh, 4).ravel().tolist(),
# #             "rh": np.round(rh, 4).ravel().tolist(),
# #             "lv": lv.tolist(), "rv": rv.tolist(), "segments": segs}


# # # =====================================================================
# # # 6. The standalone player (HTML + JavaScript, three.js r128 from a CDN)
# # # =====================================================================
# # HTML_TEMPLATE = r'''<!DOCTYPE html>
# # <html lang="vi">
# # <head>
# # <meta charset="utf-8">
# # <meta name="viewport" content="width=device-width, initial-scale=1">
# # <title>__TITLE__</title>
# # <style>
# #   :root { color-scheme: dark; }
# #   html, body { margin: 0; height: 100%; overflow: hidden; background: #0b1220; color: #e5e7eb;
# #                font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
# #   #stage { position: fixed; inset: 0; }
# #   #stage canvas { display: block; }
# #   body:not(.app) #bar, body:not(.app) #sug { display: none; }
# #   #bar { position: fixed; top: 12px; left: 50%; transform: translateX(-50%); width: min(720px, 92vw); display: flex; gap: 8px; z-index: 6; }
# #   #qwrap { position: relative; flex: 1; display: flex; }
# #   #qwrap #clear { display: none; position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
# #                   background: transparent; border: none; color: #94a3b8; font-size: 16px; padding: 4px 9px; }
# #   #qwrap #clear:hover { color: #e5e7eb; }
# #   #qwrap.has #clear { display: block; }
# #   #q { flex: 1; padding: 10px 38px 10px 14px; font-size: 16px; border-radius: 10px; border: 1px solid #475569; background: #0f172a; color: #e5e7eb; }
# #   #sug { position: fixed; top: 58px; left: 50%; transform: translateX(-50%); width: min(720px, 92vw); display: flex; flex-wrap: wrap; gap: 6px; z-index: 6; }
# #   #status .w { color: #fbbf24; }
# #   #mode { max-width: 190px; }
# #   #caption { position: fixed; top: calc(var(--cap-vh, 15) * 1vh); left: 0; right: 0; text-align: center; pointer-events: none;
# #              font-size: calc(var(--cap-px, 34) * 1px); font-weight: 700; text-shadow: 0 2px 12px #000; min-height: 46px; }
# #   #panel { position: fixed; left: 12px; right: 12px; bottom: 12px; padding: 10px 14px;
# #            background: rgba(15, 23, 42, .90); border: 1px solid #334155; border-radius: 12px; }
# #   .row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 5px 0; }
# #   button, select { background: #1e293b; color: #e5e7eb; border: 1px solid #475569; border-radius: 8px;
# #                    padding: 6px 12px; font-size: 14px; cursor: pointer; }
# #   button:hover { background: #334155; }
# #   button.rec { border-color: #ef4444; }
# #   input[type=range] { flex: 1; min-width: 160px; }
# #   label { font-size: 13px; color: #cbd5e1; display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
# #   .chip { padding: 3px 10px; border-radius: 999px; border: 1px solid #475569; font-size: 13px; cursor: pointer; }
# #   .chip.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
# #   #status { font-size: 12px; color: #94a3b8; }
# #   #status.err { color: #fca5a5; font-size: 14px; }
# # </style>
# # </head>
# # <body>
# # <div id="stage"></div>
# # <div id="bar"><select id="mode" title="Cách nhập"><option value="sentence">Câu (model dịch)</option><option value="gloss">Từ</option></select><div id="qwrap"><input id="q" type="text" autocomplete="off" placeholder=""><button id="clear" type="button" title="Xóa hết (Esc)" aria-label="Xóa hết">✕</button></div><button id="run">Chạy</button></div>
# # <div id="sug"></div>
# # <div id="caption"></div>
# # <div id="panel">
# #   <div class="row">
# #     <button id="play">Tạm dừng</button>
# #     <button id="restart">Phát lại</button>
# #     <input type="range" id="seek" min="0" max="1" step="1" value="0">
# #     <span id="time">0.0 / 0.0 s</span>
# #     <select id="speed" title="Tốc độ">
# #       <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
# #       <option value="1" selected>1x</option><option value="1.5">1.5x</option>
# #     </select>
# #     <select id="view" title="Khung nhìn">
# #       <option value="upper" selected>Thân trên</option>
# #       <option value="hands">Cận tay</option>
# #       <option value="full">Toàn thân</option>
# #     </select>
# #   </div>
# #   <div class="row" id="chips"></div>
# #   <div class="row">
# #     <label><input type="checkbox" id="o_loop" checked> Lặp lại</label>
# #     <label><input type="checkbox" id="o_fingers" checked> Ngón tay</label>
# #     <label><input type="checkbox" id="o_legs"> Chân</label>
# #     <label><input type="checkbox" id="o_mirror"> Lật trái/phải</label>
# #     <label><input type="checkbox" id="o_flipz"> Đảo chiều sâu</label>
# #     <label><input type="checkbox" id="o_swap"> Đổi tay trái/phải</label>
# #     <label><input type="checkbox" id="o_rest" checked> Về tư thế nghỉ khi xong</label>
# #     <label>Độ cao chữ <input type="range" id="o_capy" min="0" max="85" step="1"></label>
# #     <label>Cỡ chữ <input type="range" id="o_caps" min="16" max="96" step="1"></label>
# #   </div>
# #   <div id="status">Đang tải mô hình...</div>
# # </div>

# # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
# # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
# # <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
# # <script>
# # "use strict";
# # const DATA = __DATA_JSON__;
# # const GLB_B64 = "__GLB_B64__";
# # const GLB_URL = "__GLB_URL__";
# # const APP_MODE = __APP_MODE__;
# # const $ = (id) => document.getElementById(id);

# # function fail(msg) { const s = $("status"); s.textContent = msg; s.className = "err"; }

# # const opts = { mirror: false, flipZ: false, swapHands: false, legs: false,
# #                fingers: true, loop: !APP_MODE, speed: 1, rest: true };

# # // ==== RETARGET START ====
# # // Turns MediaPipe 3D points into bone rotations of the Mixamo-style Xbot skeleton.
# # const BODY = ["Hips","Spine1","Spine2","Neck","Head","LeftArm","LeftForeArm","LeftHand",
# #   "RightArm","RightForeArm","RightHand","LeftUpLeg","LeftLeg","LeftFoot","RightUpLeg","RightLeg","RightFoot"];
# # const FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"];
# # // [bone, bone it must point to] - parents first
# # const AIM_PAIRS = [
# #   ["Hips","Spine1"], ["Spine1","Spine2"], ["Spine2","Neck"], ["Neck","Head"],
# #   ["LeftArm","LeftForeArm"], ["LeftForeArm","LeftHand"],
# #   ["RightArm","RightForeArm"], ["RightForeArm","RightHand"],
# #   ["LeftUpLeg","LeftLeg"], ["LeftLeg","LeftFoot"],
# #   ["RightUpLeg","RightLeg"], ["RightLeg","RightFoot"],
# # ];
# # const LEG_BONES = ["LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"];

# # const bones = {};      // clean name -> bone
# # const restQ = {};      // clean name -> rest-pose rotation
# # let rootObj = null;
# # const handState = { Left: { w: 0, last: null }, Right: { w: 0, last: null } };

# # function cleanName(n) { return n.replace(/^mixamorig:?/, ""); }

# # function setupModel(model) {
# #   rootObj = model;
# #   model.traverse((o) => {
# #     if (o.isBone) { const c = cleanName(o.name); bones[c] = o; restQ[c] = o.quaternion.clone(); }
# #   });
# #   let fingerBases = 0;
# #   for (const s of ["Left", "Right"]) for (const f of FINGERS) if (bones[s + "Hand" + f + "1"]) fingerBases++;
# #   return { bones: Object.keys(bones).length, fingerBases };
# # }

# # function resetPose() {
# #   for (const k in bones) bones[k].quaternion.copy(restQ[k]);
# #   if (rootObj) rootObj.updateMatrixWorld(true);
# # }

# # // Rotate a bone by a rotation given in WORLD space.
# # function applyWorldRotation(bone, qWorld) {
# #   if (!bone || !bone.parent) return;
# #   bone.parent.updateWorldMatrix(true, false);
# #   const pq = bone.parent.getWorldQuaternion(new THREE.Quaternion());
# #   const adj = pq.clone().invert().multiply(qWorld).multiply(pq);
# #   bone.quaternion.premultiply(adj);
# #   bone.updateMatrixWorld(true);
# # }

# # // Make the direction  bone -> child  point along `dir` (world space).
# # function aimBone(bone, child, dir) {
# #   if (!bone || !child || dir.lengthSq() < 1e-10) return;
# #   bone.updateWorldMatrix(true, true);
# #   const p = bone.getWorldPosition(new THREE.Vector3());
# #   const c = child.getWorldPosition(new THREE.Vector3());
# #   const cur = c.sub(p);
# #   if (cur.lengthSq() < 1e-12) return;
# #   cur.normalize();
# #   applyWorldRotation(bone, new THREE.Quaternion().setFromUnitVectors(cur, dir.clone().normalize()));
# # }

# # // Twist a bone around `axisDir` so that curSide lines up with tgtSide (palm orientation).
# # function rollBoneAround(bone, axisDir, curSide, tgtSide) {
# #   const a = axisDir.clone().normalize();
# #   const c = curSide.clone().sub(a.clone().multiplyScalar(curSide.dot(a)));
# #   const t = tgtSide.clone().sub(a.clone().multiplyScalar(tgtSide.dot(a)));
# #   if (c.lengthSq() < 1e-10 || t.lengthSq() < 1e-10) return;
# #   c.normalize(); t.normalize();
# #   let angle = Math.acos(THREE.MathUtils.clamp(c.dot(t), -1, 1));
# #   if (new THREE.Vector3().crossVectors(c, t).dot(a) < 0) angle = -angle;
# #   applyWorldRotation(bone, new THREE.Quaternion().setFromAxisAngle(a, angle));
# # }

# # function blendToRest(name, w) {
# #   if (w >= 0.999 || !bones[name]) return;
# #   const q = bones[name].quaternion.clone();
# #   bones[name].quaternion.copy(restQ[name]).slerp(q, w);
# #   bones[name].updateMatrixWorld(true);
# # }

# # function applyBody(P) {
# #   for (const [a, b] of AIM_PAIRS) {
# #     if (!opts.legs && LEG_BONES.includes(a)) continue;
# #     if (!bones[a] || !bones[b] || !P[a] || !P[b]) continue;
# #     aimBone(bones[a], bones[b], P[b].clone().sub(P[a]));
# #   }
# # }

# # // H: {Wrist, Thumb1..Pinky4} -> Vector3 ; w: 0..1 blend weight (0 = rest pose)
# # function applyHand(side, H, w) {
# #   if (!H || w <= 0.001) return;
# #   const wrist = bones[side + "Hand"], mid1 = bones[side + "HandMiddle1"];
# #   const idx1 = bones[side + "HandIndex1"], pky1 = bones[side + "HandPinky1"];
# #   if (wrist && mid1 && H.Wrist && H.Middle1) {
# #     const axis = H.Middle1.clone().sub(H.Wrist);
# #     aimBone(wrist, mid1, axis);
# #     if (idx1 && pky1 && H.Index1 && H.Pinky1) {
# #       const a = idx1.getWorldPosition(new THREE.Vector3());
# #       const b = pky1.getWorldPosition(new THREE.Vector3());
# #       rollBoneAround(wrist, axis, a.sub(b), H.Index1.clone().sub(H.Pinky1));
# #     }
# #     blendToRest(side + "Hand", w);
# #   }
# #   for (const f of FINGERS) {
# #     for (let n = 1; n <= 3; n++) {
# #       const name = side + "Hand" + f + n;
# #       const bone = bones[name], child = bones[side + "Hand" + f + (n + 1)];
# #       const p0 = H[f + n], p1 = H[f + (n + 1)];
# #       if (bone && child && p0 && p1) {
# #         aimBone(bone, child, p1.clone().sub(p0));
# #         blendToRest(name, w);
# #       }
# #     }
# #   }
# # }

# # // MediaPipe camera frame (x right, y down, z away) -> model frame (x right, y up, z towards viewer)
# # function toModel(x, y, z) {
# #   return new THREE.Vector3((opts.mirror ? -1 : 1) * x, -y, -(opts.flipZ ? -1 : 1) * z);
# # }

# # let TL = null;   // current timeline {n, fps, body, lh, rh, lv, rv, segments}
# # function setTimeline(D) { TL = D; }
# # const lerp1 = (u, v, a) => u + (v - u) * a;

# # // raw pose = {b: Float64Array(51), l: Float64Array(63) | null, r: ...} in MediaPipe camera coordinates
# # function rawAt(T, f) {
# #   const n = T.n, f0 = Math.max(0, Math.min(n - 1, Math.floor(f))), f1 = Math.min(f0 + 1, n - 1);
# #   const a = Math.max(0, Math.min(1, f - f0));
# #   const b = new Float64Array(51);
# #   for (let i = 0; i < 51; i++) b[i] = lerp1(T.body[f0 * 51 + i], T.body[f1 * 51 + i], a);
# #   const hand = (arr, val) => {
# #     if (!(val[f0] && val[f1])) return null;
# #     const h = new Float64Array(63);
# #     for (let i = 0; i < 63; i++) h[i] = lerp1(arr[f0 * 63 + i], arr[f1 * 63 + i], a);
# #     return h;
# #   };
# #   return { b, l: hand(T.lh, T.lv), r: hand(T.rh, T.rv) };
# # }
# # function blendRaw(A, B, w) {
# #   const mix = (x, y) => {
# #     if (!y) return null;
# #     if (!x) return y;
# #     const o = new Float64Array(y.length);
# #     for (let i = 0; i < y.length; i++) o[i] = lerp1(x[i], y[i], w);
# #     return o;
# #   };
# #   const b = new Float64Array(51);
# #   for (let i = 0; i < 51; i++) b[i] = lerp1(A.b[i], B.b[i], w);
# #   return { b, l: mix(A.l, B.l), r: mix(A.r, B.r) };
# # }
# # // standing, arms hanging down (camera coordinates: y points down)
# # const IDLE_RAW = { l: null, r: null, b: Float64Array.from([
# #   0,0,0,  0,-.15,0,  0,-.30,0,  0,-.45,0,  0,-.62,0,
# #   .18,-.42,0,  .21,-.16,-.02,  .22,.08,-.04,
# #   -.18,-.42,0,  -.21,-.16,-.02,  -.22,.08,-.04,
# #   .09,0,0,  .09,.45,0,  .09,.90,0,   -.09,0,0,  -.09,.45,0,  -.09,.90,0]) };

# # function rawToPoints(raw) {
# #   const P = {};
# #   for (let j = 0; j < BODY.length; j++) P[BODY[j]] = toModel(raw.b[j * 3], raw.b[j * 3 + 1], raw.b[j * 3 + 2]);
# #   const hands = { Left: null, Right: null };
# #   const [L, R] = opts.swapHands ? [raw.r, raw.l] : [raw.l, raw.r];
# #   for (const [side, h] of [["Left", L], ["Right", R]]) {
# #     if (!h) continue;
# #     const pt = (k) => toModel(h[k * 3], h[k * 3 + 1], h[k * 3 + 2]);
# #     const H = { Wrist: pt(0) };
# #     FINGERS.forEach((fn, fi) => { for (let n = 1; n <= 4; n++) H[fn + n] = pt(1 + 4 * fi + (n - 1)); });
# #     hands[side] = H;
# #   }
# #   return { P, hands };
# # }

# # // Pose the whole avatar from a raw pose. dt = seconds since last call.
# # function applyRaw(raw, dt) {
# #   if (!rootObj) return;
# #   const { P, hands } = rawToPoints(raw);
# #   resetPose();                      // always start from the rest pose: no drift, no accumulated twist
# #   applyBody(P);
# #   for (const side of ["Left", "Right"]) {
# #     const st = handState[side], H = hands[side];
# #     if (H && opts.fingers) { st.last = H; st.w = Math.min(1, st.w + dt / 0.12); }
# #     else { st.w = Math.max(0, st.w - dt / 0.12); }
# #     if (st.last && st.w > 0) applyHand(side, H && opts.fingers ? H : st.last, st.w);
# #   }
# #   rootObj.updateMatrixWorld(true);
# # }
# # function sampleFrame(f) { return rawToPoints(rawAt(TL, f)); }
# # function applyFrame(f, dt) { if (TL) applyRaw(rawAt(TL, f), dt); }

# # // ---- size and camera: measured from the SKELETON (the mesh bounding box is unreliable for skinned models) ----
# # function computeFit() {
# #   rootObj.updateMatrixWorld(true);
# #   let minY = Infinity, maxY = -Infinity;
# #   for (const k in bones) {
# #     const y = bones[k].getWorldPosition(new THREE.Vector3()).y;
# #     if (y < minY) minY = y;
# #     if (y > maxY) maxY = y;
# #   }
# #   const hips = bones.Hips ? bones.Hips.getWorldPosition(new THREE.Vector3()) : null;
# #   const head = bones.Head ? bones.Head.getWorldPosition(new THREE.Vector3()) : null;
# #   return { hips, footY: minY, topY: maxY,
# #            hipsY: hips ? hips.y : (minY + maxY) / 2, headY: head ? head.y : maxY };
# # }

# # // view: "upper" | "hands" | "full".  H = window height (px), panelH / captionH = UI that covers the scene (px)
# # function computeView(fit, view, aspect, fovDeg, H, panelH, captionH) {
# #   const bodyH = fit.headY - fit.hipsY;
# #   let lo, hi, halfW;
# #   if (view === "full") { lo = fit.footY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
# #   else if (view === "hands") { lo = fit.hipsY + 0.45 * bodyH; hi = fit.headY + 0.25; halfW = 0.60; }
# #   else { lo = fit.hipsY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
# #   const avail = Math.max(0.3, (H - panelH - captionH) / H);      // share of the screen that is free
# #   const t = Math.tan(fovDeg * Math.PI / 360);
# #   const dV = ((hi - lo) / avail) / (2 * t);
# #   const dH = halfW / (t * aspect);
# #   const d = Math.max(dV, dH) * 1.05;
# #   const visH = 2 * d * t;
# #   const centerY = (lo + hi) / 2;
# #   const ty = centerY + ((captionH - panelH) / 2) * (visH / H);   // put the avatar in the free part of the screen
# #   return { target: [0, ty, 0], position: [0, ty, d] };
# # }

# # const RETARGET = { bones, restQ, setupModel, applyFrame, applyRaw, sampleFrame, rawAt, blendRaw, IDLE_RAW,
# #                    setTimeline, handState, opts, resetPose, computeFit, computeView };
# # // ==== RETARGET END ====

# # (function main() {
# #   if (APP_MODE) document.body.classList.add("app");
# #   if (typeof THREE === "undefined" || !THREE.GLTFLoader || !THREE.OrbitControls) {
# #     fail("Không tải được three.js (cần Internet lần đầu). Hãy kiểm tra kết nối rồi tải lại trang.");
# #     return;
# #   }
# #   // ---------- scene ----------
# #   const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
# #   renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
# #   renderer.outputEncoding = THREE.sRGBEncoding;
# #   $("stage").appendChild(renderer.domElement);
# #   const scene = new THREE.Scene();
# #   scene.background = new THREE.Color(0x0b1220);
# #   const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
# #   camera.position.set(0, 1.0, 2.6);
# #   const controls = new THREE.OrbitControls(camera, renderer.domElement);
# #   controls.target.set(0, 0.9, 0);
# #   controls.minDistance = 0.5;
# #   controls.maxDistance = 10;
# #   controls.update();
# #   scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 0.95));
# #   const sun = new THREE.DirectionalLight(0xffffff, 0.8);
# #   sun.position.set(2, 4, 3);
# #   scene.add(sun);
# #   const ground = new THREE.Mesh(new THREE.CircleGeometry(3, 48), new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 1 }));
# #   ground.rotation.x = -Math.PI / 2;
# #   scene.add(ground);
# #   scene.add(new THREE.GridHelper(6, 24, 0x334155, 0x1f2937));

# #   let fit = null;                                   // skeleton measurements, set when the model is loaded
# #   const TOP_H = APP_MODE ? 150 : 70;                // screen space covered by the input bar / caption
# #   function applyView() {
# #     if (!fit) return;
# #     const v = computeView(fit, $("view").value, camera.aspect, camera.fov, window.innerHeight, $("panel").offsetHeight + 12, TOP_H);
# #     camera.position.set(v.position[0], v.position[1], v.position[2]);
# #     controls.target.set(v.target[0], v.target[1], v.target[2]);
# #     controls.update();
# #   }
# #   function resize() {
# #     const w = window.innerWidth, h = window.innerHeight;
# #     renderer.setSize(w, h);
# #     camera.aspect = w / h;
# #     camera.updateProjectionMatrix();
# #     applyView();
# #   }
# #   window.addEventListener("resize", resize);
# #   resize();

# #   // ---------- playback state: idle -> play -> hold -> idle, always blended so nothing ever jumps ----------
# #   const seek = $("seek"), chips = $("chips");
# #   let mode = "idle", playing = true, tFrame = 0, holdLeft = 0, loaded = false;
# #   let cur = IDLE_RAW, from = IDLE_RAW, blendLeft = 0, segEls = [];
# #   const BLEND = 0.35;
# #   const ease = (x) => 0.5 - 0.5 * Math.cos(Math.PI * x);
# #   const startBlend = () => { from = cur; blendLeft = BLEND; };
# #   const setPlayLabel = () => { $("play").textContent = (mode === "play" && playing) ? "Tạm dừng" : "Phát"; };

# #   function loadTimeline(D) {
# #     startBlend();
# #     setTimeline(D);
# #     tFrame = 0; mode = "play"; playing = true; setPlayLabel();
# #     seek.max = Math.max(1, D.n - 1);
# #     chips.innerHTML = "";
# #     segEls = D.segments.map((sg) => {
# #       const el = document.createElement("span");
# #       el.className = "chip"; el.textContent = sg.gloss; el.title = sg.video;
# #       el.onclick = () => { tFrame = sg.s; mode = "play"; };
# #       chips.appendChild(el);
# #       return el;
# #     });
# #   }
# #   window.loadTimeline = loadTimeline;
# #   window.__dbg = () => ({ mode, tFrame, playing, blendLeft, n: TL ? TL.n : 0, loaded });

# #   $("play").onclick = () => {
# #     if (TL && mode !== "play") { startBlend(); tFrame = 0; mode = "play"; playing = true; }
# #     else playing = !playing;
# #     setPlayLabel();
# #   };
# #   $("restart").onclick = () => { if (TL) { startBlend(); tFrame = 0; mode = "play"; playing = true; setPlayLabel(); } };
# #   seek.oninput = () => { if (TL) { tFrame = +seek.value; mode = "play"; playing = false; setPlayLabel(); } };
# #   $("speed").onchange = (e) => { opts.speed = +e.target.value; };
# #   $("view").onchange = applyView;
# #   for (const [id, key] of [["o_loop","loop"],["o_fingers","fingers"],["o_legs","legs"],
# #                            ["o_mirror","mirror"],["o_flipz","flipZ"],["o_swap","swapHands"],["o_rest","rest"]]) {
# #     $(id).checked = !!opts[key];
# #     $(id).onchange = (e) => { opts[key] = e.target.checked; };
# #   }
# #   window.addEventListener("keydown", (e) => {
# #     if (e.code === "Space" && e.target.tagName !== "INPUT") { e.preventDefault(); $("play").click(); }
# #   });

# #   // ---------- typing words ----------
# #   const q = $("q"), sug = $("sug");
# #   let labels = [], labelsF = [], modelNote = "", baseStatus = "";
# #   const fold = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").toLowerCase();
# #   const tokenInfo = () => {
# #     const i = Math.max(q.value.lastIndexOf(","), q.value.lastIndexOf("|"), q.value.lastIndexOf(";"));
# #     return { i, text: q.value.slice(i + 1).trim() };
# #   };
# #   const modeSel = $("mode");
# #   function updateMode() {
# #     q.placeholder = modeSel.value === "sentence" ? "Nhập một câu tiếng Việt, ví dụ: ngày mai tôi đi học"
# #                                                   : "Nhập các gloss, cách nhau bằng dấu phẩy: tuần sau, học, không có";
# #     sug.innerHTML = "";
# #   }
# #   modeSel.onchange = updateMode;
# #   updateMode();
# #   function showSuggestions() {
# #     sug.innerHTML = "";
# #     if (modeSel.value !== "gloss") return;
# #     const t = fold(tokenInfo().text);
# #     if (!t || !labels.length) return;
# #     const starts = [], inside = [];
# #     for (let k = 0; k < labels.length && starts.length < 8; k++) {
# #       const p = labelsF[k].indexOf(t);
# #       if (p === 0) starts.push(labels[k]); else if (p > 0 && inside.length < 8) inside.push(labels[k]);
# #     }
# #     for (const lab of starts.concat(inside).slice(0, 8)) {
# #       const el = document.createElement("span");
# #       el.className = "chip"; el.textContent = lab;
# #       el.onmousedown = (e) => {
# #         e.preventDefault();
# #         const i = tokenInfo().i;
# #         q.value = (i >= 0 ? q.value.slice(0, i + 1) + " " : "") + lab + ", ";
# #         q.focus(); updateClear(); showSuggestions();
# #       };
# #       sug.appendChild(el);
# #     }
# #   }
# #   function setStatus(html, cls) { const st = $("status"); st.innerHTML = html; st.className = cls || ""; }
# #   function refreshStatus() { setStatus(baseStatus + (modelNote ? "<br>" + modelNote : ""), modelNote ? "err" : ""); }
# #   function runSentence() {
# #     const text = q.value.trim();
# #     if (!text) return;
# #     sug.innerHTML = "";
# #     const mode = modeSel.value;
# #     setStatus(mode === "sentence" ? "Đang dịch câu thành gloss..." : "Đang xử lý...");
# #     fetch("/api/sentence", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, mode }) })
# #       .then((r) => r.json())
# #       .then((res) => {
# #         const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
# #         const warn = (res.warnings || []).map((w) => '<span class="w"> ⚠ ' + esc(w) + "</span>").join("");
# #         const head = res.glosses ? "<b>Gloss:</b> " + res.glosses.map(esc).join(" | ") +
# #                      (res.translate_ms !== undefined ? " <i>(dịch " + res.translate_ms + " ms)</i>" : "") + "<br>" : "";
# #         if (!res.ok || !res.timeline) { setStatus(head + "Không chạy được: " + esc(res.error || "không có từ nào hợp lệ") + warn, "err"); return; }
# #         loadTimeline(res.timeline);
# #         setStatus(head + res.picks.map((p) => esc(p.gloss) + " → " + esc(p.video)).join(" | ") +
# #                   " &nbsp;(" + res.timeline.n + " khung, " + (res.timeline.n / res.timeline.fps).toFixed(1) + " s)" + warn);
# #       })
# #       .catch((e) => fail("Lỗi kết nối tới máy chủ: " + e));
# #   }
# #   q.addEventListener("input", showSuggestions);
# #   q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); runSentence(); } });
# #   $("run").onclick = runSentence;
# #   // clear (x) button: wipes everything typed; Esc does the same
# #   const qwrap = $("qwrap");
# #   const updateClear = () => qwrap.classList.toggle("has", q.value.length > 0);
# #   $("clear").onclick = () => { q.value = ""; sug.innerHTML = ""; updateClear(); q.focus(); };
# #   q.addEventListener("input", updateClear);
# #   q.addEventListener("keydown", (e) => { if (e.key === "Escape") $("clear").click(); });
# #   // the word being signed: height (% of the window) and size, remembered by the browser
# #   const rs = document.documentElement.style;
# #   const pref = (k, d) => { try { const v = parseFloat(localStorage.getItem(k)); return Number.isFinite(v) ? v : d; } catch (e) { return d; } };
# #   const savePref = (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} };
# #   const capY = $("o_capy"), capS = $("o_caps");
# #   capY.value = pref("capVh", APP_MODE ? 15 : 3);
# #   capS.value = pref("capPx", 34);
# #   const applyCaption = () => { rs.setProperty("--cap-vh", capY.value); rs.setProperty("--cap-px", capS.value); };
# #   capY.oninput = () => { applyCaption(); savePref("capVh", capY.value); };
# #   capS.oninput = () => { applyCaption(); savePref("capPx", capS.value); };
# #   applyCaption();
# #   if (APP_MODE) {
# #     fetch("/api/glosses").then((r) => r.json()).then((a) => { labels = a; labelsF = a.map(fold); }).catch(() => {});
# #     const poll = (k) => fetch("/api/info").then((r) => r.json()).then((info) => {      // is the sentence -> gloss model ready?
# #       const opt = modeSel.querySelector('option[value="sentence"]');
# #       if (info.model === "unavailable") {
# #         opt.disabled = true; opt.textContent = "Câu (model chưa dùng được)"; opt.title = info.error || "";
# #         modeSel.value = "gloss"; updateMode();
# #         modelNote = "Model dịch câu chưa dùng được: " + String(info.error || "").replace(/[<>&]/g, "") + " — vẫn nhập gloss trực tiếp được.";
# #         if (loaded) refreshStatus();
# #       } else if (info.model === "loading") {
# #         opt.textContent = "Câu (đang nạp model...)";
# #         if (k < 120) setTimeout(() => poll(k + 1), 1500);
# #       } else { opt.textContent = "Câu (model dịch)"; }
# #     }).catch(() => {});
# #     poll(0);
# #     q.focus();
# #   }

# #   // ---------- model ----------
# #   const onModel = (gltf) => {
# #     const model = gltf.scene;
# #     model.traverse((o) => { if (o.isMesh) o.frustumCulled = false; });
# #     scene.add(model);
# #     const info = setupModel(model);
# #     let ft = computeFit();                          // size the avatar from its skeleton: feet -> head bone = 1.55 m
# #     model.scale.multiplyScalar(1.55 / Math.max(1e-6, ft.headY - ft.footY));
# #     ft = computeFit();
# #     model.position.y -= ft.footY;
# #     if (ft.hips) { model.position.x -= ft.hips.x; model.position.z -= ft.hips.z; }
# #     fit = computeFit();
# #     applyView();
# #     loaded = true;
# #     baseStatus = "Xương: " + info.bones + " | xương ngón tay: " + info.fingerBases + "/10" +
# #       (info.fingerBases < 10 ? " (mô hình thiếu xương ngón tay: ngón sẽ không cử động)" : "") +
# #       (APP_MODE ? " | Gõ ở ô trên rồi nhấn Enter." : "");
# #     refreshStatus();
# #   };
# #   const onModelError = (err) => fail("Không đọc được mô hình Xbot: " + (err && err.message ? err.message : err));
# #   try {
# #     if (GLB_URL) new THREE.GLTFLoader().load(GLB_URL, onModel, undefined, onModelError);
# #     else {
# #       const bin = atob(GLB_B64), buf = new Uint8Array(bin.length);
# #       for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
# #       new THREE.GLTFLoader().parse(buf.buffer, "", onModel, onModelError);
# #     }
# #   } catch (e) { fail("Lỗi nạp mô hình: " + e); }
# #   if (DATA.n > 0) loadTimeline(DATA);               // static .html mode: the sentence is already inside the page

# #   // ---------- render loop ----------
# #   let last = performance.now();
# #   function tick(now) {
# #     const dt = Math.min(0.1, (now - last) / 1000);
# #     last = now;
# #     if (TL && mode === "play" && playing) {
# #       tFrame += dt * TL.fps * opts.speed;
# #       if (tFrame >= TL.n - 1) {
# #         if (opts.loop) { startBlend(); tFrame = 0; }
# #         else { tFrame = TL.n - 1; mode = "hold"; holdLeft = 0.5; setPlayLabel(); }
# #       }
# #     } else if (mode === "hold") {
# #       holdLeft -= dt;
# #       if (holdLeft <= 0 && opts.rest) { startBlend(); mode = "idle"; }
# #     }
# #     const target = (TL && (mode === "play" || mode === "hold")) ? rawAt(TL, tFrame) : IDLE_RAW;
# #     if (blendLeft > 0) { blendLeft = Math.max(0, blendLeft - dt); cur = blendRaw(from, target, ease(1 - blendLeft / BLEND)); }
# #     else cur = target;
# #     if (loaded) applyRaw(cur, dt);

# #     const fi = Math.floor(tFrame);
# #     const showing = TL && (mode === "play" || mode === "hold");
# #     const idx = showing ? TL.segments.findIndex((sg) => fi >= sg.s && fi < sg.e) : -1;
# #     const ci = idx >= 0 ? idx : (showing ? TL.segments.length - 1 : -1);
# #     $("caption").textContent = ci >= 0 ? TL.segments[ci].gloss : "";
# #     segEls.forEach((el, i) => el.classList.toggle("on", i === ci));
# #     if (TL) {
# #       seek.value = fi;
# #       $("time").textContent = (tFrame / TL.fps).toFixed(1) + " / " + (TL.n / TL.fps).toFixed(1) + " s";
# #     }
# #     controls.update();
# #     renderer.render(scene, camera);
# #     requestAnimationFrame(tick);
# #   }
# #   requestAnimationFrame(tick);
# # })();
# # </script>
# # </body>
# # </html>
# # '''


# # def render_app_page(title="Xbot - ngôn ngữ ký hiệu", scripts=None):
# #     """The interactive page served by sign_app.py (model loaded from /xbot.glb, sentences from /api/sentence)."""
# #     empty = {"fps": 30, "n": 0, "body": [], "lh": [], "rh": [], "lv": [], "rv": [], "segments": []}
# #     html = (HTML_TEMPLATE.replace("__TITLE__", title).replace("__DATA_JSON__", json.dumps(empty))
# #             .replace("__GLB_B64__", "").replace("__GLB_URL__", "/xbot.glb").replace("__APP_MODE__", "true"))
# #     return html.encode("utf-8")


# # def write_html(timeline, xbot_path, out_path, title):
# #     glb = Path(xbot_path).read_bytes()
# #     data_json = json.dumps(timeline, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
# #     html = (HTML_TEMPLATE
# #             .replace("__TITLE__", title.replace("<", "&lt;"))
# #             .replace("__DATA_JSON__", data_json)
# #             .replace("__GLB_B64__", base64.b64encode(glb).decode("ascii"))
# #             .replace("__GLB_URL__", "")
# #             .replace("__APP_MODE__", "false"))
# #     out = Path(out_path)
# #     out.parent.mkdir(parents=True, exist_ok=True)
# #     out.write_text(html, encoding="utf-8")
# #     return out


# # # =====================================================================
# # # 7. Command line
# # # =====================================================================
# # def build_parser():
# #     p = argparse.ArgumentParser(
# #         description="Chuỗi gloss -> avatar Xbot chuyển động liên tục (file HTML độc lập).")
# #     g = p.add_argument_group("đầu vào")
# #     g.add_argument("--glosses", nargs="+", help='Danh sách gloss, ví dụ: --glosses "bạn" "đi học" "có không"')
# #     g.add_argument("--sentence", help='Các gloss ngăn cách bằng dấu |, ví dụ: "bạn | đi học | có không"')
# #     g.add_argument("--glosses-file", help="File .json (list) hoặc .txt (mỗi dòng 1 gloss)")
# #     g = p.add_argument_group("đường dẫn")
# #     g.add_argument("--labels", help="File ánh xạ VIDEO/LABEL (csv, tsv, txt, xlsx, json)")
# #     g.add_argument("--videos", default=DEFAULT_VIDEOS, help="Thư mục chứa các video của dataset")
# #     g.add_argument("--xbot", default=DEFAULT_XBOT, help="File Xbot.glb")
# #     g.add_argument("--cache", default=DEFAULT_CACHE, help="Thư mục lưu tọa độ đã tính (.npz)")
# #     g.add_argument("--out", default=DEFAULT_OUT, help="File HTML đầu ra")
# #     g = p.add_argument_group("chọn video")
# #     g.add_argument("--region", default="B,T,N", help="Thứ tự ưu tiên giọng vùng: B=Bắc, T=Trung, N=Nam")
# #     g.add_argument("--search", help="Tìm nhãn chứa chuỗi này (không cần dấu) rồi thoát")
# #     g.add_argument("--precompute-all", action="store_true",
# #                    help="Tính trước tọa độ cho mọi gloss (lâu, chạy một lần)")
# #     g = p.add_argument_group("chuyển động")
# #     g.add_argument("--fps", type=float, default=30.0)
# #     g.add_argument("--transition", type=float, default=0.25, help="Giây chuyển tiếp giữa 2 từ")
# #     g.add_argument("--hold", type=float, default=0.2, help="Giây giữ tư thế đầu/cuối")
# #     g.add_argument("--smooth-body", type=float, default=1.5, help="Độ mượt thân (khung hình, 0 = tắt)")
# #     g.add_argument("--smooth-hands", type=float, default=1.0, help="Độ mượt ngón tay (0 = tắt)")
# #     g.add_argument("--hand-gap", type=int, default=6, help="Nội suy khi mất tay tối đa N khung")
# #     g.add_argument("--no-trim", action="store_true", help="Không cắt đoạn tay buông ở đầu/cuối video")
# #     g.add_argument("--rest-threshold", type=float, default=0.10,
# #                    help="Cổ tay phải cao hơn hông bao nhiêu mét để tính là đang ký")
# #     g.add_argument("--complexity", type=int, default=1, choices=[0, 1, 2],
# #                    help="Độ chính xác MediaPipe Pose (2 = chính xác nhất, chậm nhất)")
# #     p.add_argument("--open", action="store_true", help="Mở file HTML sau khi tạo")
# #     return p


# # def get_glosses(args):
# #     if args.glosses:
# #         return [g for g in args.glosses if g.strip()]
# #     if args.sentence:
# #         return [g.strip() for g in args.sentence.split("|") if g.strip()]
# #     if args.glosses_file:
# #         txt = read_text_auto(args.glosses_file)
# #         if args.glosses_file.lower().endswith(".json"):
# #             return [str(g) for g in json.loads(txt)]
# #         return [l.strip() for l in txt.splitlines() if l.strip()]
# #     return []


# # def main(argv=None, detector_factory=None):
# #     args = build_parser().parse_args(argv)
# #     videos_dir = Path(args.videos)

# #     labels = args.labels or find_labels_file(videos_dir)
# #     if not labels or not Path(labels).exists():
# #         print("Không tìm thấy file nhãn. Hãy chỉ rõ bằng --labels \"đường\\dẫn\\file.csv\"")
# #         return 2
# #     records = load_records(labels)
# #     index = GlossIndex(records, args.region.split(","))
# #     print(f"Đã đọc {len(records)} video / {len(index.by_key)} khóa tra cứu từ: {labels}")

# #     if args.search:
# #         hits = index.search(args.search)
# #         print(f'\nCác nhãn chứa "{args.search}" ({len(hits)} kết quả đầu):')
# #         for r in hits:
# #             print(f"  {r['video']:<14} {r['label']}")
# #         return 0

# #     if detector_factory is None:
# #         detector_factory = lambda: MediaPipeDetector(args.complexity)

# #     if args.precompute_all:
# #         picks = {}
# #         for rec in index.recs:
# #             key = norm(rec["label"])
# #             if key not in picks:
# #                 picks[key] = index.choose(index.lookup(rec["label"]))[0]
# #         todo = sorted(picks.values(), key=lambda r: natural_key(r["stem"]))
# #         print(f"Tính trước {len(todo)} video (mỗi gloss một video)...")
# #         for i, rec in enumerate(todo, 1):
# #             vp = videos_dir / rec["video"]
# #             try:
# #                 _, hit = get_clip_data(vp, args.cache, detector_factory)
# #                 print(f"[{i}/{len(todo)}] {rec['video']} {'(đã có)' if hit else 'xong'}")
# #             except Exception as e:
# #                 print(f"[{i}/{len(todo)}] {rec['video']} LỖI: {e}")
# #         return 0

# #     glosses = get_glosses(args)
# #     if not glosses:
# #         raw = input('Nhập các gloss, ngăn cách bằng dấu | (ví dụ: bạn | đi học | có không): ')
# #         glosses = [g.strip() for g in raw.split("|") if g.strip()]
# #     if not glosses:
# #         print("Chưa có gloss nào.")
# #         return 2

# #     # ---- gloss -> video ----
# #     picks, problems = [], []
# #     for g in glosses:
# #         found, missing = index.resolve_one(g)
# #         picks += found
# #         for w in missing:
# #             sug = index.suggest(w)
# #             problems.append(f'Không có gloss "{w}"' + (f" (gần giống: {', '.join(sug)})" if sug else ""))
# #     print("\nChuỗi gloss -> video:")
# #     for g, rec, note in picks:
# #         print(f"  {g:<18} -> {rec['video']:<14} [{rec['label']}]" + (f"  ({note})" if note else ""))
# #     for p in problems:
# #         print("  CẢNH BÁO:", p)
# #     if not picks:
# #         return 1

# #     # ---- landmarks (cached) ----
# #     clips = []
# #     for i, (g, rec, _) in enumerate(picks, 1):
# #         vp = videos_dir / rec["video"]
# #         cache_file = Path(args.cache) / (rec["stem"] + ".npz")
# #         if not vp.exists() and not cache_file.exists():
# #             print(f"  CẢNH BÁO: không thấy video {vp}")
# #             continue
# #         try:
# #             raw, hit = get_clip_data(vp, args.cache, detector_factory)
# #         except Exception as e:
# #             print(f"  CẢNH BÁO: lỗi với {rec['video']}: {e}")
# #             continue
# #         clip, ok = process_clip(raw, args.fps, args)
# #         if clip is None:
# #             print(f"  CẢNH BÁO: {rec['video']} chỉ nhận diện được {ok:.0%} khung hình, bỏ qua")
# #             continue
# #         hands_ok = [float((~np.isnan(clip[k].reshape(len(clip[k]), -1)).any(axis=1)).mean())
# #                     for k in ("lh", "rh")]
# #         print(f"  [{i}/{len(picks)}] {rec['video']}: {len(clip['body'])} khung ({len(clip['body'])/args.fps:.1f}s), "
# #               f"có tay trái {hands_ok[0]:.0%} / tay phải {hands_ok[1]:.0%}" + ("" if hit else "  (vừa tính xong, đã lưu cache)"))
# #         clip.update({"gloss": g, "video": rec["video"]})
# #         clips.append(clip)
# #     if not clips:
# #         print("Không có video nào dùng được.")
# #         return 1

# #     # ---- one continuous timeline -> html ----
# #     timeline = assemble(clips, args.fps, args.transition, args.hold)
# #     if not Path(args.xbot).exists():
# #         print(f"Không thấy file Xbot: {args.xbot}  (dùng --xbot để chỉ đường dẫn)")
# #         return 2
# #     out = write_html(timeline, args.xbot, args.out, "Avatar: " + " | ".join(c["gloss"] for c in clips))
# #     print(f"\nXong: {timeline['n']} khung hình = {timeline['n']/args.fps:.1f} giây")
# #     print(f"Mở file này (bấm đúp): {out.resolve()}")
# #     if args.open:
# #         webbrowser.open(out.resolve().as_uri())
# #     return 0


# # if __name__ == "__main__":
# #     sys.exit(main())























































































# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-
# """
# sign_to_avatar.py
# =================
# Gloss list  ->  videos of the dataset  ->  3D landmarks (cached .npz)
#             ->  ONE continuous animation of the Xbot avatar (standalone .html).

# Example:
#     python sign_to_avatar.py --glosses "bạn" "đi học" "có không"
#     python sign_to_avatar.py --sentence "bạn | đi học | có không" --open
#     python sign_to_avatar.py --search "địa chỉ"

# The output .html is a single file: double-click it, no server / localhost needed.
# (It only needs Internet once per open, to load three.js from a CDN.)
# """
# import argparse
# import base64
# import csv
# import difflib
# import io
# import json
# import os
# import re
# import sys
# import unicodedata
# import webbrowser
# from pathlib import Path

# import numpy as np

# # =====================================================================
# # DEFAULTS (edit these once, then you never need to type the paths)
# # =====================================================================
# DEFAULT_VIDEOS = r"C:\Users\ADMIN\qh\vsl-vietnamese-sign-languages\versions\5\Dataset\Videos"
# DEFAULT_XBOT = os.path.join("frontend_dis", "models", "Xbot.glb")
# DEFAULT_CACHE = "landmark_cache"
# DEFAULT_OUT = os.path.join("output", "sentence.html")

# CACHE_VERSION = 1
# VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")

# BODY_NAMES = [
#     "Hips", "Spine1", "Spine2", "Neck", "Head",
#     "LeftArm", "LeftForeArm", "LeftHand",
#     "RightArm", "RightForeArm", "RightHand",
#     "LeftUpLeg", "LeftLeg", "LeftFoot",
#     "RightUpLeg", "RightLeg", "RightFoot",
# ]

# try:  # make Vietnamese text safe to print on any console
#     sys.stdout.reconfigure(errors="replace")
#     sys.stderr.reconfigure(errors="replace")
# except Exception:
#     pass


# # =====================================================================
# # 1. Text helpers
# # =====================================================================
# def norm(s):
#     """NFC + lower-case + collapsed spaces."""
#     return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s)).strip().lower())


# def strip_accents(s):
#     s = norm(s).replace("đ", "d")
#     s = unicodedata.normalize("NFD", s)
#     return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# def without_parens(s):
#     return norm(re.sub(r"\([^)]*\)", " ", str(s)))


# def natural_key(s):
#     return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


# VIDEO_RE = re.compile(r"^(?P<base>.*\d)(?P<reg>[NTBntb])?$")


# def parse_video(name):
#     """'D0001N.mp4' -> ('D0001', 'N');  'D0002.mp4' -> ('D0002', '')."""
#     stem = Path(str(name).strip()).stem
#     m = VIDEO_RE.match(stem)
#     if m:
#         return m.group("base"), (m.group("reg") or "").upper()
#     return stem, ""


# def label_keys(label):
#     """All the lookup keys under which a dataset label can be found."""
#     plain = without_parens(label)
#     parts = {norm(label), plain}
#     for p in re.split(r"\s*[;/,]\s*", plain):
#         if p.strip():
#             parts.add(norm(p))
#     keys = set()
#     for p in parts:
#         if p:
#             keys.add(p)
#             keys.add(strip_accents(p))
#     return keys


# # =====================================================================
# # 2. Reading the label file (csv / tsv / txt / xlsx / json)
# # =====================================================================
# def read_text_auto(path):
#     raw = Path(path).read_bytes()
#     if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:200]:
#         return raw.decode("utf-16", errors="replace")
#     try:
#         return raw.decode("utf-8-sig")
#     except UnicodeDecodeError:
#         return raw.decode("cp1258", errors="replace")


# def _pick_columns(header):
#     h = [norm(c) for c in header]
#     vi = next((i for i, c in enumerate(h) if c in ("video", "file", "filename", "name")), None)
#     li = next((i for i, c in enumerate(h) if c in ("label", "gloss", "nhan", "nhãn", "text")), None)
#     return vi, li


# def load_records(path):
#     """Return [(video_name, label), ...] from any supported file type."""
#     path = str(path)
#     ext = Path(path).suffix.lower()

#     if ext == ".json":
#         data = json.loads(read_text_auto(path))
#         recs = []
#         if isinstance(data, dict):
#             for gloss, vids in data.items():
#                 if isinstance(vids, (str, dict)):
#                     vids = [vids]
#                 for v in vids:
#                     recs.append((v["video"] if isinstance(v, dict) else v, gloss))
#         else:
#             for item in data:
#                 if isinstance(item, dict):
#                     low = {norm(k): v for k, v in item.items()}
#                     recs.append((low.get("video") or low.get("file"),
#                                  low.get("label") or low.get("gloss")))
#                 else:
#                     recs.append((item[0], item[1]))
#         return [(str(v), str(l)) for v, l in recs if v and l]

#     if ext in (".xlsx", ".xls", ".xlsm"):
#         import pandas as pd  # needs openpyxl for .xlsx
#         df = pd.read_excel(path, dtype=str).fillna("")
#         rows = [list(df.columns)] + df.values.tolist()
#     else:
#         text = read_text_auto(path)
#         first = text.splitlines()[0] if text else ""
#         delim = max(["\t", ",", ";"], key=first.count)
#         rows = list(csv.reader(io.StringIO(text), delimiter=delim))

#     rows = [r for r in rows if r and any(str(c).strip() for c in r)]
#     if not rows:
#         return []
#     vi, li = _pick_columns(rows[0])
#     start = 1
#     if vi is None or li is None:  # no header: first two columns
#         vi, li = 0, 1
#         start = 0 if Path(str(rows[0][0])).suffix.lower() in VIDEO_EXTS else 1
#     out = []
#     for r in rows[start:]:
#         if len(r) > max(vi, li) and str(r[vi]).strip() and str(r[li]).strip():
#             out.append((str(r[vi]).strip(), str(r[li]).strip()))
#     return out


# def find_labels_file(videos_dir):
#     vd = Path(videos_dir)
#     exts = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json")
#     cands = []
#     for d in (vd, vd.parent, vd.parent.parent):
#         if d.is_dir():
#             cands += [p for p in d.iterdir() if p.suffix.lower() in exts]
#     hits = [p for p in cands if "label" in p.name.lower()]
#     if len(hits) >= 1:
#         return str(sorted(hits, key=lambda p: len(str(p)))[0])
#     return None


# # =====================================================================
# # 3. Gloss index: label -> video
# # =====================================================================
# class GlossIndex:
#     def __init__(self, records, region_pref=("B", "T", "N")):
#         self.region_pref = [r.upper() for r in region_pref]
#         self.recs = []
#         self.by_key = {}
#         self.by_stem = {}
#         for video, label in records:
#             base, reg = parse_video(video)
#             rec = {"video": Path(video).name, "stem": Path(video).stem,
#                    "base": base, "region": reg, "label": label}
#             self.recs.append(rec)
#             self.by_stem[norm(rec["stem"])] = rec
#             for k in label_keys(label):
#                 self.by_key.setdefault(k, []).append(rec)

#     def lookup(self, text):
#         for v in (norm(text), without_parens(text),
#                   strip_accents(text), strip_accents(without_parens(text))):
#             if v and v in self.by_key:
#                 return self.by_key[v]
#         return []

#     def choose(self, recs):
#         """One video for a gloss: first sign (lowest id), preferred region."""
#         groups = {}
#         for r in recs:
#             groups.setdefault(r["base"], []).append(r)
#         bases = sorted(groups, key=natural_key)
#         group = groups[bases[0]]
#         group.sort(key=lambda r: (self.region_pref.index(r["region"])
#                                   if r["region"] in self.region_pref else 99,
#                                   natural_key(r["stem"])))
#         return group[0], len(bases) - 1

#     def resolve_one(self, gloss):
#         """Return (list of (gloss_text, rec, note), list of missing words)."""
#         g = str(gloss).strip()
#         if not g:
#             return [], []
#         # a video id typed directly, e.g. "D0001T"
#         rec = self.by_stem.get(norm(Path(g).stem))
#         if rec is not None and re.fullmatch(r"[dD]\d+[NTBntb]?(\.\w+)?", g):
#             return [(g, rec, "")], []

#         recs = self.lookup(g)
#         if recs:
#             rec, extra = self.choose(recs)
#             note = f"còn {extra} cách ký khác" if extra > 0 else ""
#             return [(g, rec, note)], []

#         # not a known gloss: split into the longest known pieces
#         words = norm(g).split()
#         found, missing, i = [], [], 0
#         while i < len(words):
#             for j in range(len(words), i, -1):
#                 phrase = " ".join(words[i:j])
#                 recs = self.lookup(phrase)
#                 if recs:
#                     rec, extra = self.choose(recs)
#                     found.append((phrase, rec, f'tách từ "{g}"'))
#                     i = j
#                     break
#             else:
#                 missing.append(words[i])
#                 i += 1
#         if not found:
#             return [], [g]
#         return found, missing

#     def suggest(self, text, n=4):
#         pool = {}
#         for k, recs in self.by_key.items():
#             if strip_accents(k) == k:
#                 pool[k] = recs[0]["label"]
#         close = difflib.get_close_matches(strip_accents(text), list(pool), n=n, cutoff=0.6)
#         return [pool[c] for c in close]

#     def search(self, text, limit=30):
#         t = strip_accents(text)
#         hits = [r for r in self.recs if t in strip_accents(r["label"])]
#         return sorted(hits, key=lambda r: natural_key(r["stem"]))[:limit]


# # =====================================================================
# # 4. Landmark extraction (MediaPipe) + cache
# # =====================================================================
# def assign_hands(hands, left_wrist, right_wrist):
#     """
#     hands: [(image_wrist_xy, world_21x3, label)], wrists in normalised image coords.
#     Decide which detected hand is the person's LEFT / RIGHT by comparing with the
#     body-pose wrists (more reliable than the handedness label for un-mirrored video).
#     """
#     res = {"L": None, "R": None}
#     if not hands:
#         return res

#     def d(a, b):
#         return float(np.hypot(a[0] - b[0], a[1] - b[1]))

#     if left_wrist is not None and right_wrist is not None:
#         if len(hands) == 1:
#             h = hands[0]
#             res["L" if d(h[0], left_wrist) <= d(h[0], right_wrist) else "R"] = h[1]
#         else:
#             h0, h1 = hands[0], hands[1]
#             a = d(h0[0], left_wrist) + d(h1[0], right_wrist)
#             b = d(h0[0], right_wrist) + d(h1[0], left_wrist)
#             if a <= b:
#                 res["L"], res["R"] = h0[1], h1[1]
#             else:
#                 res["L"], res["R"] = h1[1], h0[1]
#     else:  # no body wrists: use the label (MediaPipe assumes a mirrored image -> swap)
#         for h in hands:
#             res["R" if h[2] == "Left" else "L"] = h[1]
#     return res


# class MediaPipeDetector:
#     """Pose (33 world landmarks) + Hands (21 world landmarks each), one video at a time."""

#     def __init__(self, complexity=1):
#         import mediapipe as mp
#         self.pose = mp.solutions.pose.Pose(
#             static_image_mode=False, model_complexity=complexity, smooth_landmarks=True,
#             min_detection_confidence=0.5, min_tracking_confidence=0.5)
#         self.hands = mp.solutions.hands.Hands(
#             static_image_mode=False, max_num_hands=2, model_complexity=1,
#             min_detection_confidence=0.5, min_tracking_confidence=0.5)

#     def __enter__(self):
#         return self

#     def __exit__(self, *a):
#         self.pose.close()
#         self.hands.close()
#         return False

#     def process(self, rgb):
#         pr = self.pose.process(rgb)
#         hr = self.hands.process(rgb)
#         pose_world = left_w = right_w = None
#         if pr.pose_world_landmarks:
#             pose_world = np.array([[l.x, l.y, l.z] for l in pr.pose_world_landmarks.landmark],
#                                   dtype=np.float32)
#         if pr.pose_landmarks:
#             lm = pr.pose_landmarks.landmark
#             left_w, right_w = (lm[15].x, lm[15].y), (lm[16].x, lm[16].y)
#         hands = []
#         if hr.multi_hand_world_landmarks and hr.multi_hand_landmarks:
#             for wl, il, hd in zip(hr.multi_hand_world_landmarks,
#                                   hr.multi_hand_landmarks, hr.multi_handedness):
#                 world = np.array([[l.x, l.y, l.z] for l in wl.landmark], dtype=np.float32)
#                 hands.append(((il.landmark[0].x, il.landmark[0].y), world,
#                               hd.classification[0].label))
#         return {"pose": pose_world, "left_wrist": left_w, "right_wrist": right_w, "hands": hands}


# def extract_video(video_path, detector_factory, target_width=640):
#     """Run the detector on every frame. Returns dict of arrays (NaN = not detected)."""
#     import cv2
#     cap = cv2.VideoCapture(str(video_path))
#     if not cap.isOpened():
#         raise IOError(f"Không mở được video: {video_path}")
#     fps = cap.get(cv2.CAP_PROP_FPS)
#     if not fps or fps != fps or fps <= 1:
#         fps = 30.0
#     pose_l, lh_l, rh_l = [], [], []
#     nan_pose = np.full((33, 3), np.nan, np.float32)
#     nan_hand = np.full((21, 3), np.nan, np.float32)
#     with detector_factory() as det:
#         while True:
#             ok, frame = cap.read()
#             if not ok:
#                 break
#             h, w = frame.shape[:2]
#             if w != target_width and w > 0:
#                 frame = cv2.resize(frame, (target_width, int(h * target_width / w)))
#             rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#             r = det.process(rgb)
#             pose_l.append(r["pose"] if r["pose"] is not None else nan_pose)
#             a = assign_hands(r["hands"], r["left_wrist"], r["right_wrist"])
#             lh_l.append(a["L"] if a["L"] is not None else nan_hand)
#             rh_l.append(a["R"] if a["R"] is not None else nan_hand)
#     cap.release()
#     if not pose_l:
#         raise IOError(f"Video rỗng: {video_path}")
#     return {"pose": np.stack(pose_l).astype(np.float32),
#             "lhand": np.stack(lh_l).astype(np.float32),
#             "rhand": np.stack(rh_l).astype(np.float32),
#             "fps": float(fps)}


# def get_clip_data(video_path, cache_dir, detector_factory):
#     cache_path = Path(cache_dir) / (Path(video_path).stem + ".npz")
#     if cache_path.exists():
#         try:
#             d = np.load(cache_path)
#             if int(d["version"]) == CACHE_VERSION:
#                 data = {k: d[k] for k in ("pose", "lhand", "rhand")}
#                 data["fps"] = float(d["fps"])
#                 return data, True
#         except Exception:
#             pass
#     data = extract_video(video_path, detector_factory)
#     cache_path.parent.mkdir(parents=True, exist_ok=True)
#     np.savez_compressed(cache_path, pose=data["pose"], lhand=data["lhand"],
#                         rhand=data["rhand"], fps=data["fps"], version=CACHE_VERSION)
#     return data, False


# # =====================================================================
# # 5. Clean-up: resample, fill gaps, smooth, trim, join
# # =====================================================================
# def resample(arr, src_fps, dst_fps):
#     T = len(arr)
#     if T < 2 or abs(src_fps - dst_fps) < 1e-3:
#         return arr
#     new_T = max(2, int(round((T - 1) * dst_fps / src_fps)) + 1)
#     t = np.linspace(0, T - 1, new_T)
#     i0 = np.floor(t).astype(int)
#     i1 = np.minimum(i0 + 1, T - 1)
#     a = (t - i0).reshape((-1,) + (1,) * (arr.ndim - 1))
#     return arr[i0] * (1 - a) + arr[i1] * a   # NaN stays NaN if either neighbour is missing


# def fill_gaps(arr, max_gap, hold_edges):
#     T = len(arr)
#     flat = arr.reshape(T, -1).astype(np.float64)
#     valid = ~np.isnan(flat).any(axis=1)
#     idx = np.where(valid)[0]
#     if len(idx) == 0:
#         return arr
#     out = flat.copy()
#     for a, b in zip(idx[:-1], idx[1:]):
#         gap = b - a - 1
#         if 0 < gap <= max_gap:
#             for k in range(1, gap + 1):
#                 w = k / (gap + 1)
#                 out[a + k] = flat[a] * (1 - w) + flat[b] * w
#     if hold_edges:
#         out[:idx[0]] = flat[idx[0]]
#         out[idx[-1] + 1:] = flat[idx[-1]]
#     return out.reshape(arr.shape).astype(np.float32)


# def hold_last_valid(arr):
#     """Replace remaining NaN frames by the previous (or next) valid frame."""
#     T = len(arr)
#     flat = arr.reshape(T, -1).copy()
#     valid = ~np.isnan(flat).any(axis=1)
#     if not valid.any():
#         return arr
#     last = None
#     for i in range(T):
#         if valid[i]:
#             last = flat[i].copy()
#         elif last is not None:
#             flat[i] = last
#     first = np.where(valid)[0][0]
#     flat[:first] = flat[first]
#     return flat.reshape(arr.shape)


# def smooth_nan(arr, sigma):
#     """Gaussian smoothing along time; invalid (NaN) frames stay invalid."""
#     T = len(arr)
#     if sigma <= 0 or T < 2:
#         return arr
#     flat = arr.reshape(T, -1).astype(np.float64)
#     valid = ~np.isnan(flat).any(axis=1)
#     if not valid.any():
#         return arr
#     i = np.arange(T)
#     W = np.exp(-0.5 * ((i[:, None] - i[None, :]) / sigma) ** 2) * valid[None, :]
#     num = W @ np.where(valid[:, None], flat, 0.0)
#     den = np.maximum(W.sum(axis=1, keepdims=True), 1e-9)
#     out = num / den
#     out[~valid] = np.nan
#     return out.reshape(arr.shape).astype(np.float32)


# def body_keypoints(pose):
#     """(T,33,3) MediaPipe pose -> (T,17,3) avatar keypoints (order = BODY_NAMES)."""
#     hips = (pose[:, 23] + pose[:, 24]) / 2
#     neck = (pose[:, 11] + pose[:, 12]) / 2
#     head = (pose[:, 7] + pose[:, 8]) / 2
#     spine1 = hips + (neck - hips) / 3
#     spine2 = hips + (neck - hips) * 2 / 3
#     kp = [hips, spine1, spine2, neck, head,
#           pose[:, 11], pose[:, 13], pose[:, 15],
#           pose[:, 12], pose[:, 14], pose[:, 16],
#           pose[:, 23], pose[:, 25], pose[:, 27],
#           pose[:, 24], pose[:, 26], pose[:, 28]]
#     return np.stack(kp, axis=1).astype(np.float32)


# def active_range(pose, threshold, pad):
#     """Frames where at least one wrist is clearly above the hips (= signing)."""
#     T = len(pose)
#     hips_y = (pose[:, 23, 1] + pose[:, 24, 1]) / 2
#     wrist_y = np.minimum(pose[:, 15, 1], pose[:, 16, 1])   # MediaPipe y points DOWN
#     idx = np.where(wrist_y < hips_y - threshold)[0]
#     if len(idx) == 0:
#         return 0, T
#     return max(0, int(idx[0]) - pad), min(T, int(idx[-1]) + pad + 1)


# def process_clip(raw, fps, args):
#     pose = resample(raw["pose"], raw["fps"], fps)
#     lh = resample(raw["lhand"], raw["fps"], fps)
#     rh = resample(raw["rhand"], raw["fps"], fps)

#     ok_ratio = float((~np.isnan(pose.reshape(len(pose), -1)).any(axis=1)).mean())
#     if ok_ratio < 0.3:
#         return None, ok_ratio

#     pose = fill_gaps(pose, max_gap=int(fps * 0.6), hold_edges=True)
#     pose = hold_last_valid(pose)
#     pose = smooth_nan(pose, args.smooth_body)
#     lh = smooth_nan(fill_gaps(lh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)
#     rh = smooth_nan(fill_gaps(rh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)

#     if not args.no_trim:
#         a, b = active_range(pose, args.rest_threshold, int(round(fps * 0.12)))
#         pose, lh, rh = pose[a:b], lh[a:b], rh[a:b]
#     return {"body": body_keypoints(pose), "lh": lh, "rh": rh}, ok_ratio


# def _ease(w):
#     return 0.5 - 0.5 * np.cos(np.pi * w)


# def assemble(clips, fps, transition_s, hold_s):
#     """clips: [{gloss, video, body, lh, rh}] -> one timeline."""
#     ntr = max(0, int(round(transition_s * fps)))
#     hold = max(0, int(round(hold_s * fps)))
#     B, LH, RH, segs = [], [], [], []
#     cursor = 0

#     def add(body, lh, rh):
#         nonlocal cursor
#         B.append(body)
#         LH.append(lh)
#         RH.append(rh)
#         cursor += len(body)

#     for i, c in enumerate(clips):
#         seg_start = cursor
#         if i == 0 and hold:
#             add(np.repeat(c["body"][:1], hold, 0), np.repeat(c["lh"][:1], hold, 0),
#                 np.repeat(c["rh"][:1], hold, 0))
#         if i > 0 and ntr:
#             p = clips[i - 1]
#             w = _ease(np.arange(1, ntr + 1) / (ntr + 1)).reshape(-1, 1, 1)
#             body = p["body"][-1][None] * (1 - w) + c["body"][0][None] * w
#             lh = p["lh"][-1][None] * (1 - w) + c["lh"][0][None] * w     # NaN if either is missing
#             rh = p["rh"][-1][None] * (1 - w) + c["rh"][0][None] * w
#             add(body, lh, rh)
#         add(c["body"], c["lh"], c["rh"])
#         if i == len(clips) - 1 and hold:
#             add(np.repeat(c["body"][-1:], hold, 0), np.repeat(c["lh"][-1:], hold, 0),
#                 np.repeat(c["rh"][-1:], hold, 0))
#         segs.append({"s": seg_start, "e": cursor, "gloss": c["gloss"], "video": c["video"]})

#     body = np.concatenate(B).astype(np.float64)
#     lh = np.concatenate(LH).astype(np.float64)
#     rh = np.concatenate(RH).astype(np.float64)
#     lv = (~np.isnan(lh.reshape(len(lh), -1)).any(axis=1)).astype(int)
#     rv = (~np.isnan(rh.reshape(len(rh), -1)).any(axis=1)).astype(int)
#     lh = np.nan_to_num(lh, nan=0.0)
#     rh = np.nan_to_num(rh, nan=0.0)
#     return {"fps": fps, "n": int(len(body)),
#             "body": np.round(body, 4).ravel().tolist(),
#             "lh": np.round(lh, 4).ravel().tolist(),
#             "rh": np.round(rh, 4).ravel().tolist(),
#             "lv": lv.tolist(), "rv": rv.tolist(), "segments": segs}


# # =====================================================================
# # 6. The standalone player (HTML + JavaScript, three.js r128 from a CDN)
# # =====================================================================
# HTML_TEMPLATE = r'''<!DOCTYPE html>
# <html lang="vi">
# <head>
# <meta charset="utf-8">
# <meta name="viewport" content="width=device-width, initial-scale=1">
# <title>__TITLE__</title>
# <style>
#   :root { color-scheme: dark; }
#   html, body { margin: 0; height: 100%; overflow: hidden; background: #0b1220; color: #e5e7eb;
#                font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
#   #stage { position: fixed; inset: 0; }
#   #stage canvas { display: block; }
#   body:not(.app) #bar, body:not(.app) #sug { display: none; }
#   #bar { position: fixed; top: 12px; left: 50%; transform: translateX(-50%); width: min(720px, 92vw); display: flex; gap: 8px; z-index: 6; }
#   #qwrap { position: relative; flex: 1; display: flex; }
#   #qwrap #clear { display: none; position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
#                   background: transparent; border: none; color: #94a3b8; font-size: 16px; padding: 4px 9px; }
#   #qwrap #clear:hover { color: #e5e7eb; }
#   #qwrap.has #clear { display: block; }
#   #q { flex: 1; padding: 10px 38px 10px 14px; font-size: 16px; border-radius: 10px; border: 1px solid #475569; background: #0f172a; color: #e5e7eb; }
#   #sug { position: fixed; top: 58px; left: 50%; transform: translateX(-50%); width: min(720px, 92vw); display: flex; flex-wrap: wrap; gap: 6px; z-index: 6; }
#   #status .w { color: #fbbf24; }
#   #mode { max-width: 190px; }
#   #caption { position: fixed; top: __CAP_VH__vh; left: 0; right: 0; text-align: center; pointer-events: none;
#              font-size: __CAP_PX__px; font-weight: 700; text-shadow: 0 2px 12px #000; min-height: 46px; }
#   #panel { position: fixed; left: 12px; right: 12px; bottom: 12px; padding: 10px 14px;
#            background: rgba(15, 23, 42, .90); border: 1px solid #334155; border-radius: 12px; }
#   .row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 5px 0; }
#   button, select { background: #1e293b; color: #e5e7eb; border: 1px solid #475569; border-radius: 8px;
#                    padding: 6px 12px; font-size: 14px; cursor: pointer; }
#   button:hover { background: #334155; }
#   button.rec { border-color: #ef4444; }
#   input[type=range] { flex: 1; min-width: 160px; }
#   label { font-size: 13px; color: #cbd5e1; display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
#   .chip { padding: 3px 10px; border-radius: 999px; border: 1px solid #475569; font-size: 13px; cursor: pointer; }
#   .chip.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
#   #status { font-size: 12px; color: #94a3b8; }
#   #status.err { color: #fca5a5; font-size: 14px; }
# </style>
# </head>
# <body>
# <div id="stage"></div>
# <div id="bar"><select id="mode" title="Cách nhập"><option value="sentence">Câu</option><option value="gloss">Từ</option></select><div id="qwrap"><input id="q" type="text" autocomplete="off" placeholder=""><button id="clear" type="button" title="Xóa hết (Esc)" aria-label="Xóa hết">✕</button></div><button id="run">Chạy</button></div>
# <div id="sug"></div>
# <div id="caption"></div>
# <div id="panel">
#   <div class="row">
#     <button id="play">Tạm dừng</button>
#     <button id="restart">Phát lại</button>
#     <input type="range" id="seek" min="0" max="1" step="1" value="0">
#     <span id="time">0.0 / 0.0 s</span>
#     <select id="speed" title="Tốc độ">
#       <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
#       <option value="1" selected>1x</option><option value="1.5">1.5x</option>
#     </select>
#     <select id="view" title="Khung nhìn">
#       <option value="upper" selected>Thân trên</option>
#       <option value="hands">Cận tay</option>
#       <option value="full">Toàn thân</option>
#     </select>
#   </div>
#   <div class="row" id="chips"></div>
#   <div class="row">
#     <label><input type="checkbox" id="o_loop" checked> Lặp lại</label>
#     <label><input type="checkbox" id="o_fingers" checked> Ngón tay</label>
#     <label><input type="checkbox" id="o_legs"> Chân</label>
#     <label><input type="checkbox" id="o_mirror"> Lật trái/phải</label>
#     <label><input type="checkbox" id="o_flipz"> Đảo chiều sâu</label>
#     <label><input type="checkbox" id="o_swap"> Đổi tay trái/phải</label>
#     <label><input type="checkbox" id="o_rest" checked> Về tư thế nghỉ khi xong</label>
#   </div>
#   <div id="status">Đang tải mô hình...</div>
# </div>

# <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
# <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
# <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
# <script>
# "use strict";
# const DATA = __DATA_JSON__;
# const GLB_B64 = "__GLB_B64__";
# const GLB_URL = "__GLB_URL__";
# const APP_MODE = __APP_MODE__;
# const $ = (id) => document.getElementById(id);

# function fail(msg) { const s = $("status"); s.textContent = msg; s.className = "err"; }

# const opts = { mirror: false, flipZ: false, swapHands: false, legs: false,
#                fingers: true, loop: !APP_MODE, speed: 1, rest: true };

# // ==== RETARGET START ====
# // Turns MediaPipe 3D points into bone rotations of the Mixamo-style Xbot skeleton.
# const BODY = ["Hips","Spine1","Spine2","Neck","Head","LeftArm","LeftForeArm","LeftHand",
#   "RightArm","RightForeArm","RightHand","LeftUpLeg","LeftLeg","LeftFoot","RightUpLeg","RightLeg","RightFoot"];
# const FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"];
# // [bone, bone it must point to] - parents first
# const AIM_PAIRS = [
#   ["Hips","Spine1"], ["Spine1","Spine2"], ["Spine2","Neck"], ["Neck","Head"],
#   ["LeftArm","LeftForeArm"], ["LeftForeArm","LeftHand"],
#   ["RightArm","RightForeArm"], ["RightForeArm","RightHand"],
#   ["LeftUpLeg","LeftLeg"], ["LeftLeg","LeftFoot"],
#   ["RightUpLeg","RightLeg"], ["RightLeg","RightFoot"],
# ];
# const LEG_BONES = ["LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"];

# const bones = {};      // clean name -> bone
# const restQ = {};      // clean name -> rest-pose rotation
# let rootObj = null;
# const handState = { Left: { w: 0, last: null }, Right: { w: 0, last: null } };

# function cleanName(n) { return n.replace(/^mixamorig:?/, ""); }

# function setupModel(model) {
#   rootObj = model;
#   model.traverse((o) => {
#     if (o.isBone) { const c = cleanName(o.name); bones[c] = o; restQ[c] = o.quaternion.clone(); }
#   });
#   let fingerBases = 0;
#   for (const s of ["Left", "Right"]) for (const f of FINGERS) if (bones[s + "Hand" + f + "1"]) fingerBases++;
#   return { bones: Object.keys(bones).length, fingerBases };
# }

# function resetPose() {
#   for (const k in bones) bones[k].quaternion.copy(restQ[k]);
#   if (rootObj) rootObj.updateMatrixWorld(true);
# }

# // Rotate a bone by a rotation given in WORLD space.
# function applyWorldRotation(bone, qWorld) {
#   if (!bone || !bone.parent) return;
#   bone.parent.updateWorldMatrix(true, false);
#   const pq = bone.parent.getWorldQuaternion(new THREE.Quaternion());
#   const adj = pq.clone().invert().multiply(qWorld).multiply(pq);
#   bone.quaternion.premultiply(adj);
#   bone.updateMatrixWorld(true);
# }

# // Make the direction  bone -> child  point along `dir` (world space).
# function aimBone(bone, child, dir) {
#   if (!bone || !child || dir.lengthSq() < 1e-10) return;
#   bone.updateWorldMatrix(true, true);
#   const p = bone.getWorldPosition(new THREE.Vector3());
#   const c = child.getWorldPosition(new THREE.Vector3());
#   const cur = c.sub(p);
#   if (cur.lengthSq() < 1e-12) return;
#   cur.normalize();
#   applyWorldRotation(bone, new THREE.Quaternion().setFromUnitVectors(cur, dir.clone().normalize()));
# }

# // Twist a bone around `axisDir` so that curSide lines up with tgtSide (palm orientation).
# function rollBoneAround(bone, axisDir, curSide, tgtSide) {
#   const a = axisDir.clone().normalize();
#   const c = curSide.clone().sub(a.clone().multiplyScalar(curSide.dot(a)));
#   const t = tgtSide.clone().sub(a.clone().multiplyScalar(tgtSide.dot(a)));
#   if (c.lengthSq() < 1e-10 || t.lengthSq() < 1e-10) return;
#   c.normalize(); t.normalize();
#   let angle = Math.acos(THREE.MathUtils.clamp(c.dot(t), -1, 1));
#   if (new THREE.Vector3().crossVectors(c, t).dot(a) < 0) angle = -angle;
#   applyWorldRotation(bone, new THREE.Quaternion().setFromAxisAngle(a, angle));
# }

# function blendToRest(name, w) {
#   if (w >= 0.999 || !bones[name]) return;
#   const q = bones[name].quaternion.clone();
#   bones[name].quaternion.copy(restQ[name]).slerp(q, w);
#   bones[name].updateMatrixWorld(true);
# }

# function applyBody(P) {
#   for (const [a, b] of AIM_PAIRS) {
#     if (!opts.legs && LEG_BONES.includes(a)) continue;
#     if (!bones[a] || !bones[b] || !P[a] || !P[b]) continue;
#     aimBone(bones[a], bones[b], P[b].clone().sub(P[a]));
#   }
# }

# // H: {Wrist, Thumb1..Pinky4} -> Vector3 ; w: 0..1 blend weight (0 = rest pose)
# function applyHand(side, H, w) {
#   if (!H || w <= 0.001) return;
#   const wrist = bones[side + "Hand"], mid1 = bones[side + "HandMiddle1"];
#   const idx1 = bones[side + "HandIndex1"], pky1 = bones[side + "HandPinky1"];
#   if (wrist && mid1 && H.Wrist && H.Middle1) {
#     const axis = H.Middle1.clone().sub(H.Wrist);
#     aimBone(wrist, mid1, axis);
#     if (idx1 && pky1 && H.Index1 && H.Pinky1) {
#       const a = idx1.getWorldPosition(new THREE.Vector3());
#       const b = pky1.getWorldPosition(new THREE.Vector3());
#       rollBoneAround(wrist, axis, a.sub(b), H.Index1.clone().sub(H.Pinky1));
#     }
#     blendToRest(side + "Hand", w);
#   }
#   for (const f of FINGERS) {
#     for (let n = 1; n <= 3; n++) {
#       const name = side + "Hand" + f + n;
#       const bone = bones[name], child = bones[side + "Hand" + f + (n + 1)];
#       const p0 = H[f + n], p1 = H[f + (n + 1)];
#       if (bone && child && p0 && p1) {
#         aimBone(bone, child, p1.clone().sub(p0));
#         blendToRest(name, w);
#       }
#     }
#   }
# }

# // MediaPipe camera frame (x right, y down, z away) -> model frame (x right, y up, z towards viewer)
# function toModel(x, y, z) {
#   return new THREE.Vector3((opts.mirror ? -1 : 1) * x, -y, -(opts.flipZ ? -1 : 1) * z);
# }

# let TL = null;   // current timeline {n, fps, body, lh, rh, lv, rv, segments}
# function setTimeline(D) { TL = D; }
# const lerp1 = (u, v, a) => u + (v - u) * a;

# // raw pose = {b: Float64Array(51), l: Float64Array(63) | null, r: ...} in MediaPipe camera coordinates
# function rawAt(T, f) {
#   const n = T.n, f0 = Math.max(0, Math.min(n - 1, Math.floor(f))), f1 = Math.min(f0 + 1, n - 1);
#   const a = Math.max(0, Math.min(1, f - f0));
#   const b = new Float64Array(51);
#   for (let i = 0; i < 51; i++) b[i] = lerp1(T.body[f0 * 51 + i], T.body[f1 * 51 + i], a);
#   const hand = (arr, val) => {
#     if (!(val[f0] && val[f1])) return null;
#     const h = new Float64Array(63);
#     for (let i = 0; i < 63; i++) h[i] = lerp1(arr[f0 * 63 + i], arr[f1 * 63 + i], a);
#     return h;
#   };
#   return { b, l: hand(T.lh, T.lv), r: hand(T.rh, T.rv) };
# }
# function blendRaw(A, B, w) {
#   const mix = (x, y) => {
#     if (!y) return null;
#     if (!x) return y;
#     const o = new Float64Array(y.length);
#     for (let i = 0; i < y.length; i++) o[i] = lerp1(x[i], y[i], w);
#     return o;
#   };
#   const b = new Float64Array(51);
#   for (let i = 0; i < 51; i++) b[i] = lerp1(A.b[i], B.b[i], w);
#   return { b, l: mix(A.l, B.l), r: mix(A.r, B.r) };
# }
# // standing, arms hanging down (camera coordinates: y points down)
# const IDLE_RAW = { l: null, r: null, b: Float64Array.from([
#   0,0,0,  0,-.15,0,  0,-.30,0,  0,-.45,0,  0,-.62,0,
#   .18,-.42,0,  .21,-.16,-.02,  .22,.08,-.04,
#   -.18,-.42,0,  -.21,-.16,-.02,  -.22,.08,-.04,
#   .09,0,0,  .09,.45,0,  .09,.90,0,   -.09,0,0,  -.09,.45,0,  -.09,.90,0]) };

# function rawToPoints(raw) {
#   const P = {};
#   for (let j = 0; j < BODY.length; j++) P[BODY[j]] = toModel(raw.b[j * 3], raw.b[j * 3 + 1], raw.b[j * 3 + 2]);
#   const hands = { Left: null, Right: null };
#   const [L, R] = opts.swapHands ? [raw.r, raw.l] : [raw.l, raw.r];
#   for (const [side, h] of [["Left", L], ["Right", R]]) {
#     if (!h) continue;
#     const pt = (k) => toModel(h[k * 3], h[k * 3 + 1], h[k * 3 + 2]);
#     const H = { Wrist: pt(0) };
#     FINGERS.forEach((fn, fi) => { for (let n = 1; n <= 4; n++) H[fn + n] = pt(1 + 4 * fi + (n - 1)); });
#     hands[side] = H;
#   }
#   return { P, hands };
# }

# // Pose the whole avatar from a raw pose. dt = seconds since last call.
# function applyRaw(raw, dt) {
#   if (!rootObj) return;
#   const { P, hands } = rawToPoints(raw);
#   resetPose();                      // always start from the rest pose: no drift, no accumulated twist
#   applyBody(P);
#   for (const side of ["Left", "Right"]) {
#     const st = handState[side], H = hands[side];
#     if (H && opts.fingers) { st.last = H; st.w = Math.min(1, st.w + dt / 0.12); }
#     else { st.w = Math.max(0, st.w - dt / 0.12); }
#     if (st.last && st.w > 0) applyHand(side, H && opts.fingers ? H : st.last, st.w);
#   }
#   rootObj.updateMatrixWorld(true);
# }
# function sampleFrame(f) { return rawToPoints(rawAt(TL, f)); }
# function applyFrame(f, dt) { if (TL) applyRaw(rawAt(TL, f), dt); }

# // ---- size and camera: measured from the SKELETON (the mesh bounding box is unreliable for skinned models) ----
# function computeFit() {
#   rootObj.updateMatrixWorld(true);
#   let minY = Infinity, maxY = -Infinity;
#   for (const k in bones) {
#     const y = bones[k].getWorldPosition(new THREE.Vector3()).y;
#     if (y < minY) minY = y;
#     if (y > maxY) maxY = y;
#   }
#   const hips = bones.Hips ? bones.Hips.getWorldPosition(new THREE.Vector3()) : null;
#   const head = bones.Head ? bones.Head.getWorldPosition(new THREE.Vector3()) : null;
#   return { hips, footY: minY, topY: maxY,
#            hipsY: hips ? hips.y : (minY + maxY) / 2, headY: head ? head.y : maxY };
# }

# // view: "upper" | "hands" | "full".  H = window height (px), panelH / captionH = UI that covers the scene (px)
# function computeView(fit, view, aspect, fovDeg, H, panelH, captionH) {
#   const bodyH = fit.headY - fit.hipsY;
#   let lo, hi, halfW;
#   if (view === "full") { lo = fit.footY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
#   else if (view === "hands") { lo = fit.hipsY + 0.45 * bodyH; hi = fit.headY + 0.25; halfW = 0.60; }
#   else { lo = fit.hipsY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
#   const avail = Math.max(0.3, (H - panelH - captionH) / H);      // share of the screen that is free
#   const t = Math.tan(fovDeg * Math.PI / 360);
#   const dV = ((hi - lo) / avail) / (2 * t);
#   const dH = halfW / (t * aspect);
#   const d = Math.max(dV, dH) * 1.05;
#   const visH = 2 * d * t;
#   const centerY = (lo + hi) / 2;
#   const ty = centerY + ((captionH - panelH) / 2) * (visH / H);   // put the avatar in the free part of the screen
#   return { target: [0, ty, 0], position: [0, ty, d] };
# }

# const RETARGET = { bones, restQ, setupModel, applyFrame, applyRaw, sampleFrame, rawAt, blendRaw, IDLE_RAW,
#                    setTimeline, handState, opts, resetPose, computeFit, computeView };
# // ==== RETARGET END ====

# (function main() {
#   if (APP_MODE) document.body.classList.add("app");
#   if (typeof THREE === "undefined" || !THREE.GLTFLoader || !THREE.OrbitControls) {
#     fail("Không tải được three.js (cần Internet lần đầu). Hãy kiểm tra kết nối rồi tải lại trang.");
#     return;
#   }
#   // ---------- scene ----------
#   const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
#   renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
#   renderer.outputEncoding = THREE.sRGBEncoding;
#   $("stage").appendChild(renderer.domElement);
#   const scene = new THREE.Scene();
#   scene.background = new THREE.Color(0x0b1220);
#   const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
#   camera.position.set(0, 1.0, 2.6);
#   const controls = new THREE.OrbitControls(camera, renderer.domElement);
#   controls.target.set(0, 0.9, 0);
#   controls.minDistance = 0.5;
#   controls.maxDistance = 10;
#   controls.update();
#   scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 0.95));
#   const sun = new THREE.DirectionalLight(0xffffff, 0.8);
#   sun.position.set(2, 4, 3);
#   scene.add(sun);
#   const ground = new THREE.Mesh(new THREE.CircleGeometry(3, 48), new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 1 }));
#   ground.rotation.x = -Math.PI / 2;
#   scene.add(ground);
#   scene.add(new THREE.GridHelper(6, 24, 0x334155, 0x1f2937));

#   let fit = null;                                   // skeleton measurements, set when the model is loaded
#   const TOP_H = APP_MODE ? 150 : 70;                // screen space covered by the input bar / caption
#   function applyView() {
#     if (!fit) return;
#     const v = computeView(fit, $("view").value, camera.aspect, camera.fov, window.innerHeight, $("panel").offsetHeight + 12, TOP_H);
#     camera.position.set(v.position[0], v.position[1], v.position[2]);
#     controls.target.set(v.target[0], v.target[1], v.target[2]);
#     controls.update();
#   }
#   function resize() {
#     const w = window.innerWidth, h = window.innerHeight;
#     renderer.setSize(w, h);
#     camera.aspect = w / h;
#     camera.updateProjectionMatrix();
#     applyView();
#   }
#   window.addEventListener("resize", resize);
#   resize();

#   // ---------- playback state: idle -> play -> hold -> idle, always blended so nothing ever jumps ----------
#   const seek = $("seek"), chips = $("chips");
#   let mode = "idle", playing = true, tFrame = 0, holdLeft = 0, loaded = false;
#   let cur = IDLE_RAW, from = IDLE_RAW, blendLeft = 0, segEls = [];
#   const BLEND = 0.35;
#   const ease = (x) => 0.5 - 0.5 * Math.cos(Math.PI * x);
#   const startBlend = () => { from = cur; blendLeft = BLEND; };
#   const setPlayLabel = () => { $("play").textContent = (mode === "play" && playing) ? "Tạm dừng" : "Phát"; };

#   function loadTimeline(D) {
#     startBlend();
#     setTimeline(D);
#     tFrame = 0; mode = "play"; playing = true; setPlayLabel();
#     seek.max = Math.max(1, D.n - 1);
#     chips.innerHTML = "";
#     segEls = D.segments.map((sg) => {
#       const el = document.createElement("span");
#       el.className = "chip"; el.textContent = sg.gloss; el.title = sg.video;
#       el.onclick = () => { tFrame = sg.s; mode = "play"; };
#       chips.appendChild(el);
#       return el;
#     });
#   }
#   window.loadTimeline = loadTimeline;
#   window.__dbg = () => ({ mode, tFrame, playing, blendLeft, n: TL ? TL.n : 0, loaded });

#   $("play").onclick = () => {
#     if (TL && mode !== "play") { startBlend(); tFrame = 0; mode = "play"; playing = true; }
#     else playing = !playing;
#     setPlayLabel();
#   };
#   $("restart").onclick = () => { if (TL) { startBlend(); tFrame = 0; mode = "play"; playing = true; setPlayLabel(); } };
#   seek.oninput = () => { if (TL) { tFrame = +seek.value; mode = "play"; playing = false; setPlayLabel(); } };
#   $("speed").onchange = (e) => { opts.speed = +e.target.value; };
#   $("view").onchange = applyView;
#   for (const [id, key] of [["o_loop","loop"],["o_fingers","fingers"],["o_legs","legs"],
#                            ["o_mirror","mirror"],["o_flipz","flipZ"],["o_swap","swapHands"],["o_rest","rest"]]) {
#     $(id).checked = !!opts[key];
#     $(id).onchange = (e) => { opts[key] = e.target.checked; };
#   }
#   window.addEventListener("keydown", (e) => {
#     if (e.code === "Space" && e.target.tagName !== "INPUT") { e.preventDefault(); $("play").click(); }
#   });

#   // ---------- typing words ----------
#   const q = $("q"), sug = $("sug");
#   let labels = [], labelsF = [], modelNote = "", baseStatus = "";
#   const fold = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").toLowerCase();
#   const tokenInfo = () => {
#     const i = Math.max(q.value.lastIndexOf(","), q.value.lastIndexOf("|"), q.value.lastIndexOf(";"));
#     return { i, text: q.value.slice(i + 1).trim() };
#   };
#   const modeSel = $("mode");
#   function updateMode() {
#     q.placeholder = modeSel.value === "sentence" ? "Nhập một câu"
#                                                   : "Nhập 1 hoặc nhiều từ, cách nhau bằng dấu phẩy: tuần sau, học, không có";
#     sug.innerHTML = "";
#   }
#   modeSel.onchange = updateMode;
#   updateMode();
#   function showSuggestions() {
#     sug.innerHTML = "";
#     if (modeSel.value !== "gloss") return;
#     const t = fold(tokenInfo().text);
#     if (!t || !labels.length) return;
#     const starts = [], inside = [];
#     for (let k = 0; k < labels.length && starts.length < 8; k++) {
#       const p = labelsF[k].indexOf(t);
#       if (p === 0) starts.push(labels[k]); else if (p > 0 && inside.length < 8) inside.push(labels[k]);
#     }
#     for (const lab of starts.concat(inside).slice(0, 8)) {
#       const el = document.createElement("span");
#       el.className = "chip"; el.textContent = lab;
#       el.onmousedown = (e) => {
#         e.preventDefault();
#         const i = tokenInfo().i;
#         q.value = (i >= 0 ? q.value.slice(0, i + 1) + " " : "") + lab + ", ";
#         q.focus(); updateClear(); showSuggestions();
#       };
#       sug.appendChild(el);
#     }
#   }
#   function setStatus(html, cls) { const st = $("status"); st.innerHTML = html; st.className = cls || ""; }
#   function refreshStatus() { setStatus(baseStatus + (modelNote ? "<br>" + modelNote : ""), modelNote ? "err" : ""); }
#   function runSentence() {
#     const text = q.value.trim();
#     if (!text) return;
#     sug.innerHTML = "";
#     const mode = modeSel.value;
#     setStatus(mode === "sentence" ? "Đang dịch câu thành gloss..." : "Đang xử lý...");
#     fetch("/api/sentence", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, mode }) })
#       .then((r) => r.json())
#       .then((res) => {
#         const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
#         const warn = (res.warnings || []).map((w) => '<span class="w"> ⚠ ' + esc(w) + "</span>").join("");
#         const head = res.glosses ? "<b>Gloss:</b> " + res.glosses.map(esc).join(" | ") +
#                      (res.translate_ms !== undefined ? " <i>(dịch " + res.translate_ms + " ms)</i>" : "") + "<br>" : "";
#         if (!res.ok || !res.timeline) { setStatus(head + "Không chạy được: " + esc(res.error || "không có từ nào hợp lệ") + warn, "err"); return; }
#         loadTimeline(res.timeline);
#         setStatus(head + res.picks.map((p) => esc(p.gloss) + " → " + esc(p.video)).join(" | ") +
#                   " &nbsp;(" + res.timeline.n + " khung, " + (res.timeline.n / res.timeline.fps).toFixed(1) + " s)" + warn);
#       })
#       .catch((e) => fail("Lỗi kết nối tới máy chủ: " + e));
#   }
#   q.addEventListener("input", showSuggestions);
#   q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); runSentence(); } });
#   $("run").onclick = runSentence;
#   // clear (x) button: wipes everything typed; Esc does the same
#   const qwrap = $("qwrap");
#   const updateClear = () => qwrap.classList.toggle("has", q.value.length > 0);
#   $("clear").onclick = () => { q.value = ""; sug.innerHTML = ""; updateClear(); q.focus(); };
#   q.addEventListener("input", updateClear);
#   q.addEventListener("keydown", (e) => { if (e.key === "Escape") $("clear").click(); });
#   if (APP_MODE) {
#     fetch("/api/glosses").then((r) => r.json()).then((a) => { labels = a; labelsF = a.map(fold); }).catch(() => {});
#     const poll = (k) => fetch("/api/info").then((r) => r.json()).then((info) => {      // is the sentence -> gloss model ready?
#       const opt = modeSel.querySelector('option[value="sentence"]');
#       if (info.model === "unavailable") {
#         opt.disabled = true; opt.textContent = "Câu (model chưa dùng được)"; opt.title = info.error || "";
#         modeSel.value = "gloss"; updateMode();
#         modelNote = "Model dịch câu chưa dùng được: " + String(info.error || "").replace(/[<>&]/g, "") + " — vẫn nhập gloss trực tiếp được.";
#         if (loaded) refreshStatus();
#       } else if (info.model === "loading") {
#         opt.textContent = "Đang nạp model";
#         if (k < 120) setTimeout(() => poll(k + 1), 1500);
#       } else { opt.textContent = "Câu"; }
#     }).catch(() => {});
#     poll(0);
#     q.focus();
#   }

#   // ---------- model ----------
#   const onModel = (gltf) => {
#     const model = gltf.scene;
#     model.traverse((o) => { if (o.isMesh) o.frustumCulled = false; });
#     scene.add(model);
#     const info = setupModel(model);
#     let ft = computeFit();                          // size the avatar from its skeleton: feet -> head bone = 1.55 m
#     model.scale.multiplyScalar(1.55 / Math.max(1e-6, ft.headY - ft.footY));
#     ft = computeFit();
#     model.position.y -= ft.footY;
#     if (ft.hips) { model.position.x -= ft.hips.x; model.position.z -= ft.hips.z; }
#     fit = computeFit();
#     applyView();
#     loaded = true;
#     baseStatus = "Xương: " + info.bones + " | xương ngón tay: " + info.fingerBases + "/10" +
#       (info.fingerBases < 10 ? " (mô hình thiếu xương ngón tay: ngón sẽ không cử động)" : "") +
#       (APP_MODE ? " | Gõ ở ô trên rồi nhấn Enter." : "");
#     refreshStatus();
#   };
#   const onModelError = (err) => fail("Không đọc được mô hình Xbot: " + (err && err.message ? err.message : err));
#   try {
#     if (GLB_URL) new THREE.GLTFLoader().load(GLB_URL, onModel, undefined, onModelError);
#     else {
#       const bin = atob(GLB_B64), buf = new Uint8Array(bin.length);
#       for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
#       new THREE.GLTFLoader().parse(buf.buffer, "", onModel, onModelError);
#     }
#   } catch (e) { fail("Lỗi nạp mô hình: " + e); }
#   if (DATA.n > 0) loadTimeline(DATA);               // static .html mode: the sentence is already inside the page

#   // ---------- render loop ----------
#   let last = performance.now();
#   function tick(now) {
#     const dt = Math.min(0.1, (now - last) / 1000);
#     last = now;
#     if (TL && mode === "play" && playing) {
#       tFrame += dt * TL.fps * opts.speed;
#       if (tFrame >= TL.n - 1) {
#         if (opts.loop) { startBlend(); tFrame = 0; }
#         else { tFrame = TL.n - 1; mode = "hold"; holdLeft = 0.5; setPlayLabel(); }
#       }
#     } else if (mode === "hold") {
#       holdLeft -= dt;
#       if (holdLeft <= 0 && opts.rest) { startBlend(); mode = "idle"; }
#     }
#     const target = (TL && (mode === "play" || mode === "hold")) ? rawAt(TL, tFrame) : IDLE_RAW;
#     if (blendLeft > 0) { blendLeft = Math.max(0, blendLeft - dt); cur = blendRaw(from, target, ease(1 - blendLeft / BLEND)); }
#     else cur = target;
#     if (loaded) applyRaw(cur, dt);

#     const fi = Math.floor(tFrame);
#     const showing = TL && (mode === "play" || mode === "hold");
#     const idx = showing ? TL.segments.findIndex((sg) => fi >= sg.s && fi < sg.e) : -1;
#     const ci = idx >= 0 ? idx : (showing ? TL.segments.length - 1 : -1);
#     $("caption").textContent = ci >= 0 ? TL.segments[ci].gloss : "";
#     segEls.forEach((el, i) => el.classList.toggle("on", i === ci));
#     if (TL) {
#       seek.value = fi;
#       $("time").textContent = (tFrame / TL.fps).toFixed(1) + " / " + (TL.n / TL.fps).toFixed(1) + " s";
#     }
#     controls.update();
#     renderer.render(scene, camera);
#     requestAnimationFrame(tick);
#   }
#   requestAnimationFrame(tick);
# })();
# </script>
# </body>
# </html>
# '''


# def render_app_page(title="Xbot - ngôn ngữ ký hiệu", scripts=None, caption_vh=15, caption_px=34):
#     """The interactive page served by sign_app.py (model loaded from /xbot.glb, sentences from /api/sentence)."""
#     empty = {"fps": 30, "n": 0, "body": [], "lh": [], "rh": [], "lv": [], "rv": [], "segments": []}
#     html = (HTML_TEMPLATE.replace("__TITLE__", title).replace("__DATA_JSON__", json.dumps(empty))
#             .replace("__GLB_B64__", "").replace("__GLB_URL__", "/xbot.glb").replace("__APP_MODE__", "true")
#             .replace("__CAP_VH__", str(caption_vh)).replace("__CAP_PX__", str(caption_px)))
#     return html.encode("utf-8")


# def write_html(timeline, xbot_path, out_path, title):
#     glb = Path(xbot_path).read_bytes()
#     data_json = json.dumps(timeline, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
#     html = (HTML_TEMPLATE
#             .replace("__TITLE__", title.replace("<", "&lt;"))
#             .replace("__DATA_JSON__", data_json)
#             .replace("__GLB_B64__", base64.b64encode(glb).decode("ascii"))
#             .replace("__GLB_URL__", "")
#             .replace("__APP_MODE__", "false")
#             .replace("__CAP_VH__", "3").replace("__CAP_PX__", "34"))
#     out = Path(out_path)
#     out.parent.mkdir(parents=True, exist_ok=True)
#     out.write_text(html, encoding="utf-8")
#     return out


# # =====================================================================
# # 7. Command line
# # =====================================================================
# def build_parser():
#     p = argparse.ArgumentParser(
#         description="Chuỗi gloss -> avatar Xbot chuyển động liên tục (file HTML độc lập).")
#     g = p.add_argument_group("đầu vào")
#     g.add_argument("--glosses", nargs="+", help='Danh sách gloss, ví dụ: --glosses "bạn" "đi học" "có không"')
#     g.add_argument("--sentence", help='Các gloss ngăn cách bằng dấu |, ví dụ: "bạn | đi học | có không"')
#     g.add_argument("--glosses-file", help="File .json (list) hoặc .txt (mỗi dòng 1 gloss)")
#     g = p.add_argument_group("đường dẫn")
#     g.add_argument("--labels", help="File ánh xạ VIDEO/LABEL (csv, tsv, txt, xlsx, json)")
#     g.add_argument("--videos", default=DEFAULT_VIDEOS, help="Thư mục chứa các video của dataset")
#     g.add_argument("--xbot", default=DEFAULT_XBOT, help="File Xbot.glb")
#     g.add_argument("--cache", default=DEFAULT_CACHE, help="Thư mục lưu tọa độ đã tính (.npz)")
#     g.add_argument("--out", default=DEFAULT_OUT, help="File HTML đầu ra")
#     g = p.add_argument_group("chọn video")
#     g.add_argument("--region", default="B,T,N", help="Thứ tự ưu tiên giọng vùng: B=Bắc, T=Trung, N=Nam")
#     g.add_argument("--search", help="Tìm nhãn chứa chuỗi này (không cần dấu) rồi thoát")
#     g.add_argument("--precompute-all", action="store_true",
#                    help="Tính trước tọa độ cho mọi gloss (lâu, chạy một lần)")
#     g = p.add_argument_group("chuyển động")
#     g.add_argument("--fps", type=float, default=30.0)
#     g.add_argument("--transition", type=float, default=0.25, help="Giây chuyển tiếp giữa 2 từ")
#     g.add_argument("--hold", type=float, default=0.2, help="Giây giữ tư thế đầu/cuối")
#     g.add_argument("--smooth-body", type=float, default=1.5, help="Độ mượt thân (khung hình, 0 = tắt)")
#     g.add_argument("--smooth-hands", type=float, default=1.0, help="Độ mượt ngón tay (0 = tắt)")
#     g.add_argument("--hand-gap", type=int, default=6, help="Nội suy khi mất tay tối đa N khung")
#     g.add_argument("--no-trim", action="store_true", help="Không cắt đoạn tay buông ở đầu/cuối video")
#     g.add_argument("--rest-threshold", type=float, default=0.10,
#                    help="Cổ tay phải cao hơn hông bao nhiêu mét để tính là đang ký")
#     g.add_argument("--complexity", type=int, default=1, choices=[0, 1, 2],
#                    help="Độ chính xác MediaPipe Pose (2 = chính xác nhất, chậm nhất)")
#     p.add_argument("--open", action="store_true", help="Mở file HTML sau khi tạo")
#     return p


# def get_glosses(args):
#     if args.glosses:
#         return [g for g in args.glosses if g.strip()]
#     if args.sentence:
#         return [g.strip() for g in args.sentence.split("|") if g.strip()]
#     if args.glosses_file:
#         txt = read_text_auto(args.glosses_file)
#         if args.glosses_file.lower().endswith(".json"):
#             return [str(g) for g in json.loads(txt)]
#         return [l.strip() for l in txt.splitlines() if l.strip()]
#     return []


# def main(argv=None, detector_factory=None):
#     args = build_parser().parse_args(argv)
#     videos_dir = Path(args.videos)

#     labels = args.labels or find_labels_file(videos_dir)
#     if not labels or not Path(labels).exists():
#         print("Không tìm thấy file nhãn. Hãy chỉ rõ bằng --labels \"đường\\dẫn\\file.csv\"")
#         return 2
#     records = load_records(labels)
#     index = GlossIndex(records, args.region.split(","))
#     print(f"Đã đọc {len(records)} video / {len(index.by_key)} khóa tra cứu từ: {labels}")

#     if args.search:
#         hits = index.search(args.search)
#         print(f'\nCác nhãn chứa "{args.search}" ({len(hits)} kết quả đầu):')
#         for r in hits:
#             print(f"  {r['video']:<14} {r['label']}")
#         return 0

#     if detector_factory is None:
#         detector_factory = lambda: MediaPipeDetector(args.complexity)

#     if args.precompute_all:
#         picks = {}
#         for rec in index.recs:
#             key = norm(rec["label"])
#             if key not in picks:
#                 picks[key] = index.choose(index.lookup(rec["label"]))[0]
#         todo = sorted(picks.values(), key=lambda r: natural_key(r["stem"]))
#         print(f"Tính trước {len(todo)} video (mỗi gloss một video)...")
#         for i, rec in enumerate(todo, 1):
#             vp = videos_dir / rec["video"]
#             try:
#                 _, hit = get_clip_data(vp, args.cache, detector_factory)
#                 print(f"[{i}/{len(todo)}] {rec['video']} {'(đã có)' if hit else 'xong'}")
#             except Exception as e:
#                 print(f"[{i}/{len(todo)}] {rec['video']} LỖI: {e}")
#         return 0

#     glosses = get_glosses(args)
#     if not glosses:
#         raw = input('Nhập các từ, ngăn cách bằng dấu | (ví dụ: bạn | đi học | có không): ')
#         glosses = [g.strip() for g in raw.split("|") if g.strip()]
#     if not glosses:
#         print("Chưa có gloss nào.")
#         return 2

#     # ---- gloss -> video ----
#     picks, problems = [], []
#     for g in glosses:
#         found, missing = index.resolve_one(g)
#         picks += found
#         for w in missing:
#             sug = index.suggest(w)
#             problems.append(f'Không có gloss "{w}"' + (f" (gần giống: {', '.join(sug)})" if sug else ""))
#     print("\nChuỗi gloss -> video:")
#     for g, rec, note in picks:
#         print(f"  {g:<18} -> {rec['video']:<14} [{rec['label']}]" + (f"  ({note})" if note else ""))
#     for p in problems:
#         print("  CẢNH BÁO:", p)
#     if not picks:
#         return 1

#     # ---- landmarks (cached) ----
#     clips = []
#     for i, (g, rec, _) in enumerate(picks, 1):
#         vp = videos_dir / rec["video"]
#         cache_file = Path(args.cache) / (rec["stem"] + ".npz")
#         if not vp.exists() and not cache_file.exists():
#             print(f"  CẢNH BÁO: không thấy video {vp}")
#             continue
#         try:
#             raw, hit = get_clip_data(vp, args.cache, detector_factory)
#         except Exception as e:
#             print(f"  CẢNH BÁO: lỗi với {rec['video']}: {e}")
#             continue
#         clip, ok = process_clip(raw, args.fps, args)
#         if clip is None:
#             print(f"  CẢNH BÁO: {rec['video']} chỉ nhận diện được {ok:.0%} khung hình, bỏ qua")
#             continue
#         hands_ok = [float((~np.isnan(clip[k].reshape(len(clip[k]), -1)).any(axis=1)).mean())
#                     for k in ("lh", "rh")]
#         print(f"  [{i}/{len(picks)}] {rec['video']}: {len(clip['body'])} khung ({len(clip['body'])/args.fps:.1f}s), "
#               f"có tay trái {hands_ok[0]:.0%} / tay phải {hands_ok[1]:.0%}" + ("" if hit else "  (vừa tính xong, đã lưu cache)"))
#         clip.update({"gloss": g, "video": rec["video"]})
#         clips.append(clip)
#     if not clips:
#         print("Không có video nào dùng được.")
#         return 1

#     # ---- one continuous timeline -> html ----
#     timeline = assemble(clips, args.fps, args.transition, args.hold)
#     if not Path(args.xbot).exists():
#         print(f"Không thấy file Xbot: {args.xbot}  (dùng --xbot để chỉ đường dẫn)")
#         return 2
#     out = write_html(timeline, args.xbot, args.out, "Avatar: " + " | ".join(c["gloss"] for c in clips))
#     print(f"\nXong: {timeline['n']} khung hình = {timeline['n']/args.fps:.1f} giây")
#     print(f"Mở file này (bấm đúp): {out.resolve()}")
#     if args.open:
#         webbrowser.open(out.resolve().as_uri())
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())




























































































































#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sign_to_avatar.py
=================
Gloss list  ->  videos of the dataset  ->  3D landmarks (cached .npz)
            ->  ONE continuous animation of the Xbot avatar (standalone .html).

Example:
    python sign_to_avatar.py --glosses "bạn" "đi học" "có không"
    python sign_to_avatar.py --sentence "bạn | đi học | có không" --open
    python sign_to_avatar.py --search "địa chỉ"

The output .html is a single file: double-click it, no server / localhost needed.
(It only needs Internet once per open, to load three.js from a CDN.)
"""
import argparse
import base64
import csv
import difflib
import io
import json
import os
import re
import sys
import unicodedata
import webbrowser
from pathlib import Path

import numpy as np

# =====================================================================
# DEFAULTS (edit these once, then you never need to type the paths)
# =====================================================================
DEFAULT_VIDEOS = r"C:\Users\ADMIN\qh\vsl-vietnamese-sign-languages\versions\5\Dataset\Videos"
DEFAULT_XBOT = os.path.join("frontend_dis", "models", "Xbot.glb")
DEFAULT_CACHE = "landmark_cache"
DEFAULT_OUT = os.path.join("output", "sentence.html")

CACHE_VERSION = 1
VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm")

BODY_NAMES = [
    "Hips", "Spine1", "Spine2", "Neck", "Head",
    "LeftArm", "LeftForeArm", "LeftHand",
    "RightArm", "RightForeArm", "RightHand",
    "LeftUpLeg", "LeftLeg", "LeftFoot",
    "RightUpLeg", "RightLeg", "RightFoot",
]

try:  # make Vietnamese text safe to print on any console
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass


# =====================================================================
# 1. Text helpers
# =====================================================================
def norm(s):
    """NFC + lower-case + collapsed spaces."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s)).strip().lower())


def strip_accents(s):
    s = norm(s).replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def without_parens(s):
    return norm(re.sub(r"\([^)]*\)", " ", str(s)))


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


VIDEO_RE = re.compile(r"^(?P<base>.*\d)(?P<reg>[NTBntb])?$")


def parse_video(name):
    """'D0001N.mp4' -> ('D0001', 'N');  'D0002.mp4' -> ('D0002', '')."""
    stem = Path(str(name).strip()).stem
    m = VIDEO_RE.match(stem)
    if m:
        return m.group("base"), (m.group("reg") or "").upper()
    return stem, ""


def label_keys(label):
    """All the lookup keys under which a dataset label can be found."""
    plain = without_parens(label)
    parts = {norm(label), plain}
    for p in re.split(r"\s*[;/,]\s*", plain):
        if p.strip():
            parts.add(norm(p))
    keys = set()
    for p in parts:
        if p:
            keys.add(p)
            keys.add(strip_accents(p))
    return keys


# =====================================================================
# 2. Reading the label file (csv / tsv / txt / xlsx / json)
# =====================================================================
def read_text_auto(path):
    raw = Path(path).read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:200]:
        return raw.decode("utf-16", errors="replace")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1258", errors="replace")


def _pick_columns(header):
    h = [norm(c) for c in header]
    vi = next((i for i, c in enumerate(h) if c in ("video", "file", "filename", "name")), None)
    li = next((i for i, c in enumerate(h) if c in ("label", "gloss", "nhan", "nhãn", "text")), None)
    return vi, li


def load_records(path):
    """Return [(video_name, label), ...] from any supported file type."""
    path = str(path)
    ext = Path(path).suffix.lower()

    if ext == ".json":
        data = json.loads(read_text_auto(path))
        recs = []
        if isinstance(data, dict):
            for gloss, vids in data.items():
                if isinstance(vids, (str, dict)):
                    vids = [vids]
                for v in vids:
                    recs.append((v["video"] if isinstance(v, dict) else v, gloss))
        else:
            for item in data:
                if isinstance(item, dict):
                    low = {norm(k): v for k, v in item.items()}
                    recs.append((low.get("video") or low.get("file"),
                                 low.get("label") or low.get("gloss")))
                else:
                    recs.append((item[0], item[1]))
        return [(str(v), str(l)) for v, l in recs if v and l]

    if ext in (".xlsx", ".xls", ".xlsm"):
        import pandas as pd  # needs openpyxl for .xlsx
        df = pd.read_excel(path, dtype=str).fillna("")
        rows = [list(df.columns)] + df.values.tolist()
    else:
        text = read_text_auto(path)
        first = text.splitlines()[0] if text else ""
        delim = max(["\t", ",", ";"], key=first.count)
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))

    rows = [r for r in rows if r and any(str(c).strip() for c in r)]
    if not rows:
        return []
    vi, li = _pick_columns(rows[0])
    start = 1
    if vi is None or li is None:  # no header: first two columns
        vi, li = 0, 1
        start = 0 if Path(str(rows[0][0])).suffix.lower() in VIDEO_EXTS else 1
    out = []
    for r in rows[start:]:
        if len(r) > max(vi, li) and str(r[vi]).strip() and str(r[li]).strip():
            out.append((str(r[vi]).strip(), str(r[li]).strip()))
    return out


def find_labels_file(videos_dir):
    vd = Path(videos_dir)
    exts = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json")
    cands = []
    for d in (vd, vd.parent, vd.parent.parent):
        if d.is_dir():
            cands += [p for p in d.iterdir() if p.suffix.lower() in exts]
    hits = [p for p in cands if "label" in p.name.lower()]
    if len(hits) >= 1:
        return str(sorted(hits, key=lambda p: len(str(p)))[0])
    return None


# =====================================================================
# 3. Gloss index: label -> video
# =====================================================================
class GlossIndex:
    def __init__(self, records, region_pref=("B", "T", "N")):
        self.region_pref = [r.upper() for r in region_pref]
        self.recs = []
        self.by_key = {}
        self.by_stem = {}
        for video, label in records:
            base, reg = parse_video(video)
            rec = {"video": Path(video).name, "stem": Path(video).stem,
                   "base": base, "region": reg, "label": label}
            self.recs.append(rec)
            self.by_stem[norm(rec["stem"])] = rec
            for k in label_keys(label):
                self.by_key.setdefault(k, []).append(rec)

    def lookup(self, text):
        for v in (norm(text), without_parens(text),
                  strip_accents(text), strip_accents(without_parens(text))):
            if v and v in self.by_key:
                return self.by_key[v]
        return []

    def choose(self, recs):
        """One video for a gloss: first sign (lowest id), preferred region."""
        groups = {}
        for r in recs:
            groups.setdefault(r["base"], []).append(r)
        bases = sorted(groups, key=natural_key)
        group = groups[bases[0]]
        group.sort(key=lambda r: (self.region_pref.index(r["region"])
                                  if r["region"] in self.region_pref else 99,
                                  natural_key(r["stem"])))
        return group[0], len(bases) - 1

    def resolve_one(self, gloss):
        """Return (list of (gloss_text, rec, note), list of missing words)."""
        g = str(gloss).strip()
        if not g:
            return [], []
        # a video id typed directly, e.g. "D0001T"
        rec = self.by_stem.get(norm(Path(g).stem))
        if rec is not None and re.fullmatch(r"[dD]\d+[NTBntb]?(\.\w+)?", g):
            return [(g, rec, "")], []

        recs = self.lookup(g)
        if recs:
            rec, extra = self.choose(recs)
            note = f"còn {extra} cách ký khác" if extra > 0 else ""
            return [(g, rec, note)], []

        # not a known gloss: split into the longest known pieces
        words = norm(g).split()
        found, missing, i = [], [], 0
        while i < len(words):
            for j in range(len(words), i, -1):
                phrase = " ".join(words[i:j])
                recs = self.lookup(phrase)
                if recs:
                    rec, extra = self.choose(recs)
                    found.append((phrase, rec, f'tách từ "{g}"'))
                    i = j
                    break
            else:
                missing.append(words[i])
                i += 1
        if not found:
            return [], [g]
        return found, missing

    def suggest(self, text, n=4):
        pool = {}
        for k, recs in self.by_key.items():
            if strip_accents(k) == k:
                pool[k] = recs[0]["label"]
        close = difflib.get_close_matches(strip_accents(text), list(pool), n=n, cutoff=0.6)
        return [pool[c] for c in close]

    def search(self, text, limit=30):
        t = strip_accents(text)
        hits = [r for r in self.recs if t in strip_accents(r["label"])]
        return sorted(hits, key=lambda r: natural_key(r["stem"]))[:limit]


# =====================================================================
# 4. Landmark extraction (MediaPipe) + cache
# =====================================================================
def assign_hands(hands, left_wrist, right_wrist):
    """
    hands: [(image_wrist_xy, world_21x3, label)], wrists in normalised image coords.
    Decide which detected hand is the person's LEFT / RIGHT by comparing with the
    body-pose wrists (more reliable than the handedness label for un-mirrored video).
    """
    res = {"L": None, "R": None}
    if not hands:
        return res

    def d(a, b):
        return float(np.hypot(a[0] - b[0], a[1] - b[1]))

    if left_wrist is not None and right_wrist is not None:
        if len(hands) == 1:
            h = hands[0]
            res["L" if d(h[0], left_wrist) <= d(h[0], right_wrist) else "R"] = h[1]
        else:
            h0, h1 = hands[0], hands[1]
            a = d(h0[0], left_wrist) + d(h1[0], right_wrist)
            b = d(h0[0], right_wrist) + d(h1[0], left_wrist)
            if a <= b:
                res["L"], res["R"] = h0[1], h1[1]
            else:
                res["L"], res["R"] = h1[1], h0[1]
    else:  # no body wrists: use the label (MediaPipe assumes a mirrored image -> swap)
        for h in hands:
            res["R" if h[2] == "Left" else "L"] = h[1]
    return res


class MediaPipeDetector:
    """Pose (33 world landmarks) + Hands (21 world landmarks each), one video at a time."""

    def __init__(self, complexity=1):
        import mediapipe as mp
        self.pose = mp.solutions.pose.Pose(
            static_image_mode=False, model_complexity=complexity, smooth_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.hands = mp.solutions.hands.Hands(
            static_image_mode=False, max_num_hands=2, model_complexity=1,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.pose.close()
        self.hands.close()
        return False

    def process(self, rgb):
        pr = self.pose.process(rgb)
        hr = self.hands.process(rgb)
        pose_world = left_w = right_w = None
        if pr.pose_world_landmarks:
            pose_world = np.array([[l.x, l.y, l.z] for l in pr.pose_world_landmarks.landmark],
                                  dtype=np.float32)
        if pr.pose_landmarks:
            lm = pr.pose_landmarks.landmark
            left_w, right_w = (lm[15].x, lm[15].y), (lm[16].x, lm[16].y)
        hands = []
        if hr.multi_hand_world_landmarks and hr.multi_hand_landmarks:
            for wl, il, hd in zip(hr.multi_hand_world_landmarks,
                                  hr.multi_hand_landmarks, hr.multi_handedness):
                world = np.array([[l.x, l.y, l.z] for l in wl.landmark], dtype=np.float32)
                hands.append(((il.landmark[0].x, il.landmark[0].y), world,
                              hd.classification[0].label))
        return {"pose": pose_world, "left_wrist": left_w, "right_wrist": right_w, "hands": hands}


def extract_video(video_path, detector_factory, target_width=640):
    """Run the detector on every frame. Returns dict of arrays (NaN = not detected)."""
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise IOError(f"Không mở được video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps != fps or fps <= 1:
        fps = 30.0
    pose_l, lh_l, rh_l = [], [], []
    nan_pose = np.full((33, 3), np.nan, np.float32)
    nan_hand = np.full((21, 3), np.nan, np.float32)
    with detector_factory() as det:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            h, w = frame.shape[:2]
            if w != target_width and w > 0:
                frame = cv2.resize(frame, (target_width, int(h * target_width / w)))
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            r = det.process(rgb)
            pose_l.append(r["pose"] if r["pose"] is not None else nan_pose)
            a = assign_hands(r["hands"], r["left_wrist"], r["right_wrist"])
            lh_l.append(a["L"] if a["L"] is not None else nan_hand)
            rh_l.append(a["R"] if a["R"] is not None else nan_hand)
    cap.release()
    if not pose_l:
        raise IOError(f"Video rỗng: {video_path}")
    return {"pose": np.stack(pose_l).astype(np.float32),
            "lhand": np.stack(lh_l).astype(np.float32),
            "rhand": np.stack(rh_l).astype(np.float32),
            "fps": float(fps)}


def get_clip_data(video_path, cache_dir, detector_factory):
    cache_path = Path(cache_dir) / (Path(video_path).stem + ".npz")
    if cache_path.exists():
        try:
            d = np.load(cache_path)
            if int(d["version"]) == CACHE_VERSION:
                data = {k: d[k] for k in ("pose", "lhand", "rhand")}
                data["fps"] = float(d["fps"])
                return data, True
        except Exception:
            pass
    data = extract_video(video_path, detector_factory)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_path, pose=data["pose"], lhand=data["lhand"],
                        rhand=data["rhand"], fps=data["fps"], version=CACHE_VERSION)
    return data, False


# =====================================================================
# 5. Clean-up: resample, fill gaps, smooth, trim, join
# =====================================================================
def resample(arr, src_fps, dst_fps):
    T = len(arr)
    if T < 2 or abs(src_fps - dst_fps) < 1e-3:
        return arr
    new_T = max(2, int(round((T - 1) * dst_fps / src_fps)) + 1)
    t = np.linspace(0, T - 1, new_T)
    i0 = np.floor(t).astype(int)
    i1 = np.minimum(i0 + 1, T - 1)
    a = (t - i0).reshape((-1,) + (1,) * (arr.ndim - 1))
    return arr[i0] * (1 - a) + arr[i1] * a   # NaN stays NaN if either neighbour is missing


def fill_gaps(arr, max_gap, hold_edges):
    T = len(arr)
    flat = arr.reshape(T, -1).astype(np.float64)
    valid = ~np.isnan(flat).any(axis=1)
    idx = np.where(valid)[0]
    if len(idx) == 0:
        return arr
    out = flat.copy()
    for a, b in zip(idx[:-1], idx[1:]):
        gap = b - a - 1
        if 0 < gap <= max_gap:
            for k in range(1, gap + 1):
                w = k / (gap + 1)
                out[a + k] = flat[a] * (1 - w) + flat[b] * w
    if hold_edges:
        out[:idx[0]] = flat[idx[0]]
        out[idx[-1] + 1:] = flat[idx[-1]]
    return out.reshape(arr.shape).astype(np.float32)


def hold_last_valid(arr):
    """Replace remaining NaN frames by the previous (or next) valid frame."""
    T = len(arr)
    flat = arr.reshape(T, -1).copy()
    valid = ~np.isnan(flat).any(axis=1)
    if not valid.any():
        return arr
    last = None
    for i in range(T):
        if valid[i]:
            last = flat[i].copy()
        elif last is not None:
            flat[i] = last
    first = np.where(valid)[0][0]
    flat[:first] = flat[first]
    return flat.reshape(arr.shape)


def smooth_nan(arr, sigma):
    """Gaussian smoothing along time; invalid (NaN) frames stay invalid."""
    T = len(arr)
    if sigma <= 0 or T < 2:
        return arr
    flat = arr.reshape(T, -1).astype(np.float64)
    valid = ~np.isnan(flat).any(axis=1)
    if not valid.any():
        return arr
    i = np.arange(T)
    W = np.exp(-0.5 * ((i[:, None] - i[None, :]) / sigma) ** 2) * valid[None, :]
    num = W @ np.where(valid[:, None], flat, 0.0)
    den = np.maximum(W.sum(axis=1, keepdims=True), 1e-9)
    out = num / den
    out[~valid] = np.nan
    return out.reshape(arr.shape).astype(np.float32)


def body_keypoints(pose):
    """(T,33,3) MediaPipe pose -> (T,17,3) avatar keypoints (order = BODY_NAMES)."""
    hips = (pose[:, 23] + pose[:, 24]) / 2
    neck = (pose[:, 11] + pose[:, 12]) / 2
    head = (pose[:, 7] + pose[:, 8]) / 2
    spine1 = hips + (neck - hips) / 3
    spine2 = hips + (neck - hips) * 2 / 3
    kp = [hips, spine1, spine2, neck, head,
          pose[:, 11], pose[:, 13], pose[:, 15],
          pose[:, 12], pose[:, 14], pose[:, 16],
          pose[:, 23], pose[:, 25], pose[:, 27],
          pose[:, 24], pose[:, 26], pose[:, 28]]
    return np.stack(kp, axis=1).astype(np.float32)


def active_range(pose, threshold, pad):
    """Frames where at least one wrist is clearly above the hips (= signing)."""
    T = len(pose)
    hips_y = (pose[:, 23, 1] + pose[:, 24, 1]) / 2
    wrist_y = np.minimum(pose[:, 15, 1], pose[:, 16, 1])   # MediaPipe y points DOWN
    idx = np.where(wrist_y < hips_y - threshold)[0]
    if len(idx) == 0:
        return 0, T
    return max(0, int(idx[0]) - pad), min(T, int(idx[-1]) + pad + 1)


def process_clip(raw, fps, args):
    pose = resample(raw["pose"], raw["fps"], fps)
    lh = resample(raw["lhand"], raw["fps"], fps)
    rh = resample(raw["rhand"], raw["fps"], fps)

    ok_ratio = float((~np.isnan(pose.reshape(len(pose), -1)).any(axis=1)).mean())
    if ok_ratio < 0.3:
        return None, ok_ratio

    pose = fill_gaps(pose, max_gap=int(fps * 0.6), hold_edges=True)
    pose = hold_last_valid(pose)
    pose = smooth_nan(pose, args.smooth_body)
    lh = smooth_nan(fill_gaps(lh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)
    rh = smooth_nan(fill_gaps(rh, max_gap=int(args.hand_gap), hold_edges=False), args.smooth_hands)

    if not args.no_trim:
        a, b = active_range(pose, args.rest_threshold, int(round(fps * 0.12)))
        pose, lh, rh = pose[a:b], lh[a:b], rh[a:b]
    return {"body": body_keypoints(pose), "lh": lh, "rh": rh}, ok_ratio


def _ease(w):
    return 0.5 - 0.5 * np.cos(np.pi * w)


def assemble(clips, fps, transition_s, hold_s):
    """clips: [{gloss, video, body, lh, rh}] -> one timeline."""
    ntr = max(0, int(round(transition_s * fps)))
    hold = max(0, int(round(hold_s * fps)))
    B, LH, RH, segs = [], [], [], []
    cursor = 0

    def add(body, lh, rh):
        nonlocal cursor
        B.append(body)
        LH.append(lh)
        RH.append(rh)
        cursor += len(body)

    for i, c in enumerate(clips):
        seg_start = cursor
        if i == 0 and hold:
            add(np.repeat(c["body"][:1], hold, 0), np.repeat(c["lh"][:1], hold, 0),
                np.repeat(c["rh"][:1], hold, 0))
        if i > 0 and ntr:
            p = clips[i - 1]
            w = _ease(np.arange(1, ntr + 1) / (ntr + 1)).reshape(-1, 1, 1)
            body = p["body"][-1][None] * (1 - w) + c["body"][0][None] * w
            lh = p["lh"][-1][None] * (1 - w) + c["lh"][0][None] * w     # NaN if either is missing
            rh = p["rh"][-1][None] * (1 - w) + c["rh"][0][None] * w
            add(body, lh, rh)
        add(c["body"], c["lh"], c["rh"])
        if i == len(clips) - 1 and hold:
            add(np.repeat(c["body"][-1:], hold, 0), np.repeat(c["lh"][-1:], hold, 0),
                np.repeat(c["rh"][-1:], hold, 0))
        segs.append({"s": seg_start, "e": cursor, "gloss": c["gloss"], "video": c["video"]})

    body = np.concatenate(B).astype(np.float64)
    lh = np.concatenate(LH).astype(np.float64)
    rh = np.concatenate(RH).astype(np.float64)
    lv = (~np.isnan(lh.reshape(len(lh), -1)).any(axis=1)).astype(int)
    rv = (~np.isnan(rh.reshape(len(rh), -1)).any(axis=1)).astype(int)
    lh = np.nan_to_num(lh, nan=0.0)
    rh = np.nan_to_num(rh, nan=0.0)
    return {"fps": fps, "n": int(len(body)),
            "body": np.round(body, 4).ravel().tolist(),
            "lh": np.round(lh, 4).ravel().tolist(),
            "rh": np.round(rh, 4).ravel().tolist(),
            "lv": lv.tolist(), "rv": rv.tolist(), "segments": segs}


# =====================================================================
# 6. The standalone player (HTML + JavaScript, three.js r128 from a CDN)
# =====================================================================
HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { color-scheme: dark; }
  html, body { margin: 0; height: 100%; overflow: hidden; background: #0b1220; color: #e5e7eb;
               font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  #stage { position: fixed; inset: 0; }
  #stage canvas { display: block; }
  body:not(.app) #bar, body:not(.app) #sug { display: none; }
  #bar { position: fixed; top: 12px; left: 50%; transform: translateX(-50%); width: min(720px, 92vw); display: flex; gap: 8px; z-index: 6; }
  #qwrap { position: relative; flex: 1; display: flex; }
  #qwrap #clear { display: none; position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
                  background: transparent; border: none; color: #94a3b8; font-size: 16px; padding: 4px 9px; }
  #qwrap #clear:hover { color: #e5e7eb; }
  #qwrap.has #clear { display: block; }
  #q { flex: 1; padding: 10px 38px 10px 14px; font-size: 16px; border-radius: 10px; border: 1px solid #475569; background: #0f172a; color: #e5e7eb; }
  #sug { position: fixed; top: 58px; left: 50%; transform: translateX(-50%); width: min(720px, 92vw); display: flex; flex-wrap: wrap; gap: 6px; z-index: 6; }
  #status .w { color: #fbbf24; }
  #mode { max-width: 190px; }
  #region { max-width: 120px; }
  #caption { position: fixed; top: __CAP_VH__vh; left: 0; right: 0; text-align: center; pointer-events: none;
             font-size: __CAP_PX__px; font-weight: 700; text-shadow: 0 2px 12px #000; min-height: 46px; }
  #panel { position: fixed; left: 12px; right: 12px; bottom: 12px; padding: 10px 14px;
           background: rgba(15, 23, 42, .90); border: 1px solid #334155; border-radius: 12px; }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 5px 0; }
  button, select { background: #1e293b; color: #e5e7eb; border: 1px solid #475569; border-radius: 8px;
                   padding: 6px 12px; font-size: 14px; cursor: pointer; }
  button:hover { background: #334155; }
  button.rec { border-color: #ef4444; }
  input[type=range] { flex: 1; min-width: 160px; }
  label { font-size: 13px; color: #cbd5e1; display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
  .chip { padding: 3px 10px; border-radius: 999px; border: 1px solid #475569; font-size: 13px; cursor: pointer; }
  .chip.on { background: #3b82f6; border-color: #3b82f6; color: #fff; }
  #status { font-size: 12px; color: #94a3b8; }
  #status.err { color: #fca5a5; font-size: 14px; }
</style>
</head>
<body>
<div id="stage"></div>
<div id="bar"><select id="mode" title="Cách nhập"><option value="sentence">Câu</option><option value="gloss">Từ</option></select><select id="region" title="Giọng vùng miền (chỉ áp dụng cho các từ có nhiều giọng)"><option value="B">Bắc</option><option value="T">Trung</option><option value="N">Nam</option></select><div id="qwrap"><input id="q" type="text" autocomplete="off" placeholder=""><button id="clear" type="button" title="Xóa hết (Esc)" aria-label="Xóa hết">✕</button></div><button id="run">Chạy</button></div>
<div id="sug"></div>
<div id="caption"></div>
<div id="panel">
  <div class="row">
    <button id="play">Tạm dừng</button>
    <button id="restart">Phát lại</button>
    <input type="range" id="seek" min="0" max="1" step="1" value="0">
    <span id="time">0.0 / 0.0 s</span>
    <select id="speed" title="Tốc độ">
      <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
      <option value="1" selected>1x</option><option value="1.5">1.5x</option>
    </select>
    <select id="view" title="Khung nhìn">
      <option value="upper" selected>Thân trên</option>
      <option value="hands">Cận tay</option>
      <option value="full">Toàn thân</option>
    </select>
  </div>
  <div class="row" id="chips"></div>
  <div class="row">
    <label><input type="checkbox" id="o_loop" checked> Lặp lại</label>
    <label><input type="checkbox" id="o_fingers" checked> Ngón tay</label>
    <label><input type="checkbox" id="o_rest" checked> Về tư thế nghỉ khi xong</label>
  </div>
  <div id="status">Đang tải mô hình...</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
"use strict";
const DATA = __DATA_JSON__;
const GLB_B64 = "__GLB_B64__";
const GLB_URL = "__GLB_URL__";
const APP_MODE = __APP_MODE__;
const REGION_DEFAULT = "__REGION__";
const $ = (id) => document.getElementById(id);

function fail(msg) { const s = $("status"); s.textContent = msg; s.className = "err"; }

const opts = { mirror: false, flipZ: false, swapHands: false, legs: false,
               fingers: true, loop: !APP_MODE, speed: 1, rest: true };

// ==== RETARGET START ====
// Turns MediaPipe 3D points into bone rotations of the Mixamo-style Xbot skeleton.
const BODY = ["Hips","Spine1","Spine2","Neck","Head","LeftArm","LeftForeArm","LeftHand",
  "RightArm","RightForeArm","RightHand","LeftUpLeg","LeftLeg","LeftFoot","RightUpLeg","RightLeg","RightFoot"];
const FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"];
// [bone, bone it must point to] - parents first
const AIM_PAIRS = [
  ["Hips","Spine1"], ["Spine1","Spine2"], ["Spine2","Neck"], ["Neck","Head"],
  ["LeftArm","LeftForeArm"], ["LeftForeArm","LeftHand"],
  ["RightArm","RightForeArm"], ["RightForeArm","RightHand"],
  ["LeftUpLeg","LeftLeg"], ["LeftLeg","LeftFoot"],
  ["RightUpLeg","RightLeg"], ["RightLeg","RightFoot"],
];
const LEG_BONES = ["LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"];

const bones = {};      // clean name -> bone
const restQ = {};      // clean name -> rest-pose rotation
let rootObj = null;
const handState = { Left: { w: 0, last: null }, Right: { w: 0, last: null } };

function cleanName(n) { return n.replace(/^mixamorig:?/, ""); }

function setupModel(model) {
  rootObj = model;
  model.traverse((o) => {
    if (o.isBone) { const c = cleanName(o.name); bones[c] = o; restQ[c] = o.quaternion.clone(); }
  });
  let fingerBases = 0;
  for (const s of ["Left", "Right"]) for (const f of FINGERS) if (bones[s + "Hand" + f + "1"]) fingerBases++;
  return { bones: Object.keys(bones).length, fingerBases };
}

function resetPose() {
  for (const k in bones) bones[k].quaternion.copy(restQ[k]);
  if (rootObj) rootObj.updateMatrixWorld(true);
}

// Rotate a bone by a rotation given in WORLD space.
function applyWorldRotation(bone, qWorld) {
  if (!bone || !bone.parent) return;
  bone.parent.updateWorldMatrix(true, false);
  const pq = bone.parent.getWorldQuaternion(new THREE.Quaternion());
  const adj = pq.clone().invert().multiply(qWorld).multiply(pq);
  bone.quaternion.premultiply(adj);
  bone.updateMatrixWorld(true);
}

// Make the direction  bone -> child  point along `dir` (world space).
function aimBone(bone, child, dir) {
  if (!bone || !child || dir.lengthSq() < 1e-10) return;
  bone.updateWorldMatrix(true, true);
  const p = bone.getWorldPosition(new THREE.Vector3());
  const c = child.getWorldPosition(new THREE.Vector3());
  const cur = c.sub(p);
  if (cur.lengthSq() < 1e-12) return;
  cur.normalize();
  applyWorldRotation(bone, new THREE.Quaternion().setFromUnitVectors(cur, dir.clone().normalize()));
}

// Twist a bone around `axisDir` so that curSide lines up with tgtSide (palm orientation).
function rollBoneAround(bone, axisDir, curSide, tgtSide) {
  const a = axisDir.clone().normalize();
  const c = curSide.clone().sub(a.clone().multiplyScalar(curSide.dot(a)));
  const t = tgtSide.clone().sub(a.clone().multiplyScalar(tgtSide.dot(a)));
  if (c.lengthSq() < 1e-10 || t.lengthSq() < 1e-10) return;
  c.normalize(); t.normalize();
  let angle = Math.acos(THREE.MathUtils.clamp(c.dot(t), -1, 1));
  if (new THREE.Vector3().crossVectors(c, t).dot(a) < 0) angle = -angle;
  applyWorldRotation(bone, new THREE.Quaternion().setFromAxisAngle(a, angle));
}

function blendToRest(name, w) {
  if (w >= 0.999 || !bones[name]) return;
  const q = bones[name].quaternion.clone();
  bones[name].quaternion.copy(restQ[name]).slerp(q, w);
  bones[name].updateMatrixWorld(true);
}

function applyBody(P) {
  for (const [a, b] of AIM_PAIRS) {
    if (!opts.legs && LEG_BONES.includes(a)) continue;
    if (!bones[a] || !bones[b] || !P[a] || !P[b]) continue;
    aimBone(bones[a], bones[b], P[b].clone().sub(P[a]));
  }
}

// H: {Wrist, Thumb1..Pinky4} -> Vector3 ; w: 0..1 blend weight (0 = rest pose)
function applyHand(side, H, w) {
  if (!H || w <= 0.001) return;
  const wrist = bones[side + "Hand"], mid1 = bones[side + "HandMiddle1"];
  const idx1 = bones[side + "HandIndex1"], pky1 = bones[side + "HandPinky1"];
  if (wrist && mid1 && H.Wrist && H.Middle1) {
    const axis = H.Middle1.clone().sub(H.Wrist);
    aimBone(wrist, mid1, axis);
    if (idx1 && pky1 && H.Index1 && H.Pinky1) {
      const a = idx1.getWorldPosition(new THREE.Vector3());
      const b = pky1.getWorldPosition(new THREE.Vector3());
      rollBoneAround(wrist, axis, a.sub(b), H.Index1.clone().sub(H.Pinky1));
    }
    blendToRest(side + "Hand", w);
  }
  for (const f of FINGERS) {
    for (let n = 1; n <= 3; n++) {
      const name = side + "Hand" + f + n;
      const bone = bones[name], child = bones[side + "Hand" + f + (n + 1)];
      const p0 = H[f + n], p1 = H[f + (n + 1)];
      if (bone && child && p0 && p1) {
        aimBone(bone, child, p1.clone().sub(p0));
        blendToRest(name, w);
      }
    }
  }
}

// MediaPipe camera frame (x right, y down, z away) -> model frame (x right, y up, z towards viewer)
function toModel(x, y, z) {
  return new THREE.Vector3((opts.mirror ? -1 : 1) * x, -y, -(opts.flipZ ? -1 : 1) * z);
}

let TL = null;   // current timeline {n, fps, body, lh, rh, lv, rv, segments}
function setTimeline(D) { TL = D; }
const lerp1 = (u, v, a) => u + (v - u) * a;

// raw pose = {b: Float64Array(51), l: Float64Array(63) | null, r: ...} in MediaPipe camera coordinates
function rawAt(T, f) {
  const n = T.n, f0 = Math.max(0, Math.min(n - 1, Math.floor(f))), f1 = Math.min(f0 + 1, n - 1);
  const a = Math.max(0, Math.min(1, f - f0));
  const b = new Float64Array(51);
  for (let i = 0; i < 51; i++) b[i] = lerp1(T.body[f0 * 51 + i], T.body[f1 * 51 + i], a);
  const hand = (arr, val) => {
    if (!(val[f0] && val[f1])) return null;
    const h = new Float64Array(63);
    for (let i = 0; i < 63; i++) h[i] = lerp1(arr[f0 * 63 + i], arr[f1 * 63 + i], a);
    return h;
  };
  return { b, l: hand(T.lh, T.lv), r: hand(T.rh, T.rv) };
}
function blendRaw(A, B, w) {
  const mix = (x, y) => {
    if (!y) return null;
    if (!x) return y;
    const o = new Float64Array(y.length);
    for (let i = 0; i < y.length; i++) o[i] = lerp1(x[i], y[i], w);
    return o;
  };
  const b = new Float64Array(51);
  for (let i = 0; i < 51; i++) b[i] = lerp1(A.b[i], B.b[i], w);
  return { b, l: mix(A.l, B.l), r: mix(A.r, B.r) };
}
// standing, arms hanging down (camera coordinates: y points down)
const IDLE_RAW = { l: null, r: null, b: Float64Array.from([
  0,0,0,  0,-.15,0,  0,-.30,0,  0,-.45,0,  0,-.62,0,
  .18,-.42,0,  .21,-.16,-.02,  .22,.08,-.04,
  -.18,-.42,0,  -.21,-.16,-.02,  -.22,.08,-.04,
  .09,0,0,  .09,.45,0,  .09,.90,0,   -.09,0,0,  -.09,.45,0,  -.09,.90,0]) };

function rawToPoints(raw) {
  const P = {};
  for (let j = 0; j < BODY.length; j++) P[BODY[j]] = toModel(raw.b[j * 3], raw.b[j * 3 + 1], raw.b[j * 3 + 2]);
  const hands = { Left: null, Right: null };
  const [L, R] = opts.swapHands ? [raw.r, raw.l] : [raw.l, raw.r];
  for (const [side, h] of [["Left", L], ["Right", R]]) {
    if (!h) continue;
    const pt = (k) => toModel(h[k * 3], h[k * 3 + 1], h[k * 3 + 2]);
    const H = { Wrist: pt(0) };
    FINGERS.forEach((fn, fi) => { for (let n = 1; n <= 4; n++) H[fn + n] = pt(1 + 4 * fi + (n - 1)); });
    hands[side] = H;
  }
  return { P, hands };
}

// Pose the whole avatar from a raw pose. dt = seconds since last call.
function applyRaw(raw, dt) {
  if (!rootObj) return;
  const { P, hands } = rawToPoints(raw);
  resetPose();                      // always start from the rest pose: no drift, no accumulated twist
  applyBody(P);
  for (const side of ["Left", "Right"]) {
    const st = handState[side], H = hands[side];
    if (H && opts.fingers) { st.last = H; st.w = Math.min(1, st.w + dt / 0.12); }
    else { st.w = Math.max(0, st.w - dt / 0.12); }
    if (st.last && st.w > 0) applyHand(side, H && opts.fingers ? H : st.last, st.w);
  }
  rootObj.updateMatrixWorld(true);
}
function sampleFrame(f) { return rawToPoints(rawAt(TL, f)); }
function applyFrame(f, dt) { if (TL) applyRaw(rawAt(TL, f), dt); }

// ---- size and camera: measured from the SKELETON (the mesh bounding box is unreliable for skinned models) ----
function computeFit() {
  rootObj.updateMatrixWorld(true);
  let minY = Infinity, maxY = -Infinity;
  for (const k in bones) {
    const y = bones[k].getWorldPosition(new THREE.Vector3()).y;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  const hips = bones.Hips ? bones.Hips.getWorldPosition(new THREE.Vector3()) : null;
  const head = bones.Head ? bones.Head.getWorldPosition(new THREE.Vector3()) : null;
  return { hips, footY: minY, topY: maxY,
           hipsY: hips ? hips.y : (minY + maxY) / 2, headY: head ? head.y : maxY };
}

// view: "upper" | "hands" | "full".  H = window height (px), panelH / captionH = UI that covers the scene (px)
function computeView(fit, view, aspect, fovDeg, H, panelH, captionH) {
  const bodyH = fit.headY - fit.hipsY;
  let lo, hi, halfW;
  if (view === "full") { lo = fit.footY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
  else if (view === "hands") { lo = fit.hipsY + 0.45 * bodyH; hi = fit.headY + 0.25; halfW = 0.60; }
  else { lo = fit.hipsY - 0.05; hi = fit.headY + 0.30; halfW = 0.85; }
  const avail = Math.max(0.3, (H - panelH - captionH) / H);      // share of the screen that is free
  const t = Math.tan(fovDeg * Math.PI / 360);
  const dV = ((hi - lo) / avail) / (2 * t);
  const dH = halfW / (t * aspect);
  const d = Math.max(dV, dH) * 1.05;
  const visH = 2 * d * t;
  const centerY = (lo + hi) / 2;
  const ty = centerY + ((captionH - panelH) / 2) * (visH / H);   // put the avatar in the free part of the screen
  return { target: [0, ty, 0], position: [0, ty, d] };
}

const RETARGET = { bones, restQ, setupModel, applyFrame, applyRaw, sampleFrame, rawAt, blendRaw, IDLE_RAW,
                   setTimeline, handState, opts, resetPose, computeFit, computeView };
// ==== RETARGET END ====

(function main() {
  if (APP_MODE) document.body.classList.add("app");
  if (typeof THREE === "undefined" || !THREE.GLTFLoader || !THREE.OrbitControls) {
    fail("Không tải được three.js (cần Internet lần đầu). Hãy kiểm tra kết nối rồi tải lại trang.");
    return;
  }
  // ---------- scene ----------
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputEncoding = THREE.sRGBEncoding;
  $("stage").appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b1220);
  const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
  camera.position.set(0, 1.0, 2.6);
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0.9, 0);
  controls.minDistance = 0.5;
  controls.maxDistance = 10;
  controls.update();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 0.95));
  const sun = new THREE.DirectionalLight(0xffffff, 0.8);
  sun.position.set(2, 4, 3);
  scene.add(sun);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(3, 48), new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 1 }));
  ground.rotation.x = -Math.PI / 2;
  scene.add(ground);
  scene.add(new THREE.GridHelper(6, 24, 0x334155, 0x1f2937));

  let fit = null;                                   // skeleton measurements, set when the model is loaded
  const TOP_H = APP_MODE ? 150 : 70;                // screen space covered by the input bar / caption
  function applyView() {
    if (!fit) return;
    const v = computeView(fit, $("view").value, camera.aspect, camera.fov, window.innerHeight, $("panel").offsetHeight + 12, TOP_H);
    camera.position.set(v.position[0], v.position[1], v.position[2]);
    controls.target.set(v.target[0], v.target[1], v.target[2]);
    controls.update();
  }
  function resize() {
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    applyView();
  }
  window.addEventListener("resize", resize);
  resize();

  // ---------- playback state: idle -> play -> hold -> idle, always blended so nothing ever jumps ----------
  const seek = $("seek"), chips = $("chips");
  let mode = "idle", playing = true, tFrame = 0, holdLeft = 0, loaded = false;
  let cur = IDLE_RAW, from = IDLE_RAW, blendLeft = 0, segEls = [];
  const BLEND = 0.35;
  const ease = (x) => 0.5 - 0.5 * Math.cos(Math.PI * x);
  const startBlend = () => { from = cur; blendLeft = BLEND; };
  const setPlayLabel = () => { $("play").textContent = (mode === "play" && playing) ? "Tạm dừng" : "Phát"; };

  function loadTimeline(D) {
    startBlend();
    setTimeline(D);
    tFrame = 0; mode = "play"; playing = true; setPlayLabel();
    seek.max = Math.max(1, D.n - 1);
    chips.innerHTML = "";
    segEls = D.segments.map((sg) => {
      const el = document.createElement("span");
      el.className = "chip"; el.textContent = sg.gloss; el.title = sg.video;
      el.onclick = () => { tFrame = sg.s; mode = "play"; };
      chips.appendChild(el);
      return el;
    });
  }
  window.loadTimeline = loadTimeline;
  window.__dbg = () => ({ mode, tFrame, playing, blendLeft, n: TL ? TL.n : 0, loaded });

  $("play").onclick = () => {
    if (TL && mode !== "play") { startBlend(); tFrame = 0; mode = "play"; playing = true; }
    else playing = !playing;
    setPlayLabel();
  };
  $("restart").onclick = () => { if (TL) { startBlend(); tFrame = 0; mode = "play"; playing = true; setPlayLabel(); } };
  seek.oninput = () => { if (TL) { tFrame = +seek.value; mode = "play"; playing = false; setPlayLabel(); } };
  $("speed").onchange = (e) => { opts.speed = +e.target.value; };
  $("view").onchange = applyView;
  for (const [id, key] of [["o_loop","loop"],["o_fingers","fingers"],["o_rest","rest"]]) {
    $(id).checked = !!opts[key];
    $(id).onchange = (e) => { opts[key] = e.target.checked; };
  }
  window.addEventListener("keydown", (e) => {
    if (e.code === "Space" && e.target.tagName !== "INPUT") { e.preventDefault(); $("play").click(); }
  });

  // ---------- typing words ----------
  const q = $("q"), sug = $("sug");
  let labels = [], labelsF = [], modelNote = "", baseStatus = "";
  const fold = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").toLowerCase();
  const tokenInfo = () => {
    const i = Math.max(q.value.lastIndexOf(","), q.value.lastIndexOf("|"), q.value.lastIndexOf(";"));
    return { i, text: q.value.slice(i + 1).trim() };
  };
  const modeSel = $("mode");
  function updateMode() {
    q.placeholder = modeSel.value === "sentence" ? "Nhập một câu tiếng Việt, ví dụ: ngày mai tôi đi học"
                                                  : "Nhập các từ, cách nhau bằng dấu phẩy: tuần sau, học, không có";
    sug.innerHTML = "";
  }
  modeSel.onchange = updateMode;
  updateMode();
  $("region").value = REGION_DEFAULT;
  function showSuggestions() {
    sug.innerHTML = "";
    if (modeSel.value !== "gloss") return;
    const t = fold(tokenInfo().text);
    if (!t || !labels.length) return;
    const starts = [], inside = [];
    for (let k = 0; k < labels.length && starts.length < 8; k++) {
      const p = labelsF[k].indexOf(t);
      if (p === 0) starts.push(labels[k]); else if (p > 0 && inside.length < 8) inside.push(labels[k]);
    }
    for (const lab of starts.concat(inside).slice(0, 8)) {
      const el = document.createElement("span");
      el.className = "chip"; el.textContent = lab;
      el.onmousedown = (e) => {
        e.preventDefault();
        const i = tokenInfo().i;
        q.value = (i >= 0 ? q.value.slice(0, i + 1) + " " : "") + lab + ", ";
        q.focus(); updateClear(); showSuggestions();
      };
      sug.appendChild(el);
    }
  }
  function setStatus(html, cls) { const st = $("status"); st.innerHTML = html; st.className = cls || ""; }
  function refreshStatus() { setStatus(baseStatus + (modelNote ? "<br>" + modelNote : ""), modelNote ? "err" : ""); }
  function runSentence() {
    const text = q.value.trim();
    if (!text) return;
    sug.innerHTML = "";
    const mode = modeSel.value;
    setStatus(mode === "sentence" ? "Đang dịch câu thành gloss..." : "Đang xử lý...");
    fetch("/api/sentence", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, mode, region: $("region").value }) })
      .then((r) => r.json())
      .then((res) => {
        const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
        const warn = (res.warnings || []).map((w) => '<span class="w"> ⚠ ' + esc(w) + "</span>").join("");
        const head = res.glosses ? "<b>Gloss:</b> " + res.glosses.map(esc).join(" | ") +
                     (res.translate_ms !== undefined ? " <i>(dịch " + res.translate_ms + " ms)</i>" : "") + "<br>" : "";
        if (!res.ok || !res.timeline) { setStatus(head + "Không chạy được: " + esc(res.error || "không có từ nào hợp lệ") + warn, "err"); return; }
        loadTimeline(res.timeline);
        setStatus(head + res.picks.map((p) => esc(p.gloss) + " → " + esc(p.video)).join(" | ") +
                  " &nbsp;(" + res.timeline.n + " khung, " + (res.timeline.n / res.timeline.fps).toFixed(1) + " s)" + warn);
      })
      .catch((e) => fail("Lỗi kết nối tới máy chủ: " + e));
  }
  q.addEventListener("input", showSuggestions);
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); runSentence(); } });
  $("run").onclick = runSentence;
  // clear (x) button: wipes everything typed; Esc does the same
  const qwrap = $("qwrap");
  const updateClear = () => qwrap.classList.toggle("has", q.value.length > 0);
  $("clear").onclick = () => { q.value = ""; sug.innerHTML = ""; updateClear(); q.focus(); };
  q.addEventListener("input", updateClear);
  q.addEventListener("keydown", (e) => { if (e.key === "Escape") $("clear").click(); });
  if (APP_MODE) {
    fetch("/api/glosses").then((r) => r.json()).then((a) => { labels = a; labelsF = a.map(fold); }).catch(() => {});
    const poll = (k) => fetch("/api/info").then((r) => r.json()).then((info) => {      // is the sentence -> gloss model ready?
      const opt = modeSel.querySelector('option[value="sentence"]');
      if (info.model === "unavailable") {
        opt.disabled = true; opt.textContent = "Câu (model chưa dùng được)"; opt.title = info.error || "";
        modeSel.value = "gloss"; updateMode();
        modelNote = "Model dịch câu chưa dùng được: " + String(info.error || "").replace(/[<>&]/g, "") + " — vẫn nhập gloss trực tiếp được.";
        if (loaded) refreshStatus();
      } else if (info.model === "loading") {
        opt.textContent = "Đang nạp model...";
        if (k < 120) setTimeout(() => poll(k + 1), 1500);
      } else { opt.textContent = "Câu"; }
    }).catch(() => {});
    poll(0);
    q.focus();
  }

  // ---------- model ----------
  const onModel = (gltf) => {
    const model = gltf.scene;
    model.traverse((o) => { if (o.isMesh) o.frustumCulled = false; });
    scene.add(model);
    const info = setupModel(model);
    let ft = computeFit();                          // size the avatar from its skeleton: feet -> head bone = 1.55 m
    model.scale.multiplyScalar(1.55 / Math.max(1e-6, ft.headY - ft.footY));
    ft = computeFit();
    model.position.y -= ft.footY;
    if (ft.hips) { model.position.x -= ft.hips.x; model.position.z -= ft.hips.z; }
    fit = computeFit();
    applyView();
    loaded = true;
    baseStatus = "Xương: " + info.bones + " | xương ngón tay: " + info.fingerBases + "/10" +
      (info.fingerBases < 10 ? " (mô hình thiếu xương ngón tay: ngón sẽ không cử động)" : "") +
      (APP_MODE ? " | Gõ ở ô trên rồi nhấn Enter." : "");
    refreshStatus();
  };
  const onModelError = (err) => fail("Không đọc được mô hình Xbot: " + (err && err.message ? err.message : err));
  try {
    if (GLB_URL) new THREE.GLTFLoader().load(GLB_URL, onModel, undefined, onModelError);
    else {
      const bin = atob(GLB_B64), buf = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
      new THREE.GLTFLoader().parse(buf.buffer, "", onModel, onModelError);
    }
  } catch (e) { fail("Lỗi nạp mô hình: " + e); }
  if (DATA.n > 0) loadTimeline(DATA);               // static .html mode: the sentence is already inside the page

  // ---------- render loop ----------
  let last = performance.now();
  function tick(now) {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    if (TL && mode === "play" && playing) {
      tFrame += dt * TL.fps * opts.speed;
      if (tFrame >= TL.n - 1) {
        if (opts.loop) { startBlend(); tFrame = 0; }
        else { tFrame = TL.n - 1; mode = "hold"; holdLeft = 0.5; setPlayLabel(); }
      }
    } else if (mode === "hold") {
      holdLeft -= dt;
      if (holdLeft <= 0 && opts.rest) { startBlend(); mode = "idle"; }
    }
    const target = (TL && (mode === "play" || mode === "hold")) ? rawAt(TL, tFrame) : IDLE_RAW;
    if (blendLeft > 0) { blendLeft = Math.max(0, blendLeft - dt); cur = blendRaw(from, target, ease(1 - blendLeft / BLEND)); }
    else cur = target;
    if (loaded) applyRaw(cur, dt);

    const fi = Math.floor(tFrame);
    const showing = TL && (mode === "play" || mode === "hold");
    const idx = showing ? TL.segments.findIndex((sg) => fi >= sg.s && fi < sg.e) : -1;
    const ci = idx >= 0 ? idx : (showing ? TL.segments.length - 1 : -1);
    $("caption").textContent = ci >= 0 ? TL.segments[ci].gloss : "";
    segEls.forEach((el, i) => el.classList.toggle("on", i === ci));
    if (TL) {
      seek.value = fi;
      $("time").textContent = (tFrame / TL.fps).toFixed(1) + " / " + (TL.n / TL.fps).toFixed(1) + " s";
    }
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
</script>
</body>
</html>
'''


def render_app_page(title="Xbot - ngôn ngữ ký hiệu", scripts=None, caption_vh=15, caption_px=34, region="B"):
    """The interactive page served by sign_app.py (model loaded from /xbot.glb, sentences from /api/sentence)."""
    empty = {"fps": 30, "n": 0, "body": [], "lh": [], "rh": [], "lv": [], "rv": [], "segments": []}
    html = (HTML_TEMPLATE.replace("__TITLE__", title).replace("__DATA_JSON__", json.dumps(empty))
            .replace("__GLB_B64__", "").replace("__GLB_URL__", "/xbot.glb").replace("__APP_MODE__", "true")
            .replace("__CAP_VH__", str(caption_vh)).replace("__CAP_PX__", str(caption_px)).replace("__REGION__", str(region)))
    return html.encode("utf-8")


def write_html(timeline, xbot_path, out_path, title):
    glb = Path(xbot_path).read_bytes()
    data_json = json.dumps(timeline, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (HTML_TEMPLATE
            .replace("__TITLE__", title.replace("<", "&lt;"))
            .replace("__DATA_JSON__", data_json)
            .replace("__GLB_B64__", base64.b64encode(glb).decode("ascii"))
            .replace("__GLB_URL__", "")
            .replace("__APP_MODE__", "false")
            .replace("__CAP_VH__", "3").replace("__CAP_PX__", "34").replace("__REGION__", "B"))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


# =====================================================================
# 7. Command line
# =====================================================================
def build_parser():
    p = argparse.ArgumentParser(
        description="Chuỗi gloss -> avatar Xbot chuyển động liên tục (file HTML độc lập).")
    g = p.add_argument_group("đầu vào")
    g.add_argument("--glosses", nargs="+", help='Danh sách gloss, ví dụ: --glosses "bạn" "đi học" "có không"')
    g.add_argument("--sentence", help='Các gloss ngăn cách bằng dấu |, ví dụ: "bạn | đi học | có không"')
    g.add_argument("--glosses-file", help="File .json (list) hoặc .txt (mỗi dòng 1 gloss)")
    g = p.add_argument_group("đường dẫn")
    g.add_argument("--labels", help="File ánh xạ VIDEO/LABEL (csv, tsv, txt, xlsx, json)")
    g.add_argument("--videos", default=DEFAULT_VIDEOS, help="Thư mục chứa các video của dataset")
    g.add_argument("--xbot", default=DEFAULT_XBOT, help="File Xbot.glb")
    g.add_argument("--cache", default=DEFAULT_CACHE, help="Thư mục lưu tọa độ đã tính (.npz)")
    g.add_argument("--out", default=DEFAULT_OUT, help="File HTML đầu ra")
    g = p.add_argument_group("chọn video")
    g.add_argument("--region", default="B,T,N", help="Thứ tự ưu tiên giọng vùng: B=Bắc, T=Trung, N=Nam")
    g.add_argument("--search", help="Tìm nhãn chứa chuỗi này (không cần dấu) rồi thoát")
    g.add_argument("--precompute-all", action="store_true",
                   help="Tính trước tọa độ cho mọi gloss (lâu, chạy một lần)")
    g = p.add_argument_group("chuyển động")
    g.add_argument("--fps", type=float, default=30.0)
    g.add_argument("--transition", type=float, default=0.25, help="Giây chuyển tiếp giữa 2 từ")
    g.add_argument("--hold", type=float, default=0.2, help="Giây giữ tư thế đầu/cuối")
    g.add_argument("--smooth-body", type=float, default=1.5, help="Độ mượt thân (khung hình, 0 = tắt)")
    g.add_argument("--smooth-hands", type=float, default=1.0, help="Độ mượt ngón tay (0 = tắt)")
    g.add_argument("--hand-gap", type=int, default=6, help="Nội suy khi mất tay tối đa N khung")
    g.add_argument("--no-trim", action="store_true", help="Không cắt đoạn tay buông ở đầu/cuối video")
    g.add_argument("--rest-threshold", type=float, default=0.10,
                   help="Cổ tay phải cao hơn hông bao nhiêu mét để tính là đang ký")
    g.add_argument("--complexity", type=int, default=1, choices=[0, 1, 2],
                   help="Độ chính xác MediaPipe Pose (2 = chính xác nhất, chậm nhất)")
    p.add_argument("--open", action="store_true", help="Mở file HTML sau khi tạo")
    return p


def get_glosses(args):
    if args.glosses:
        return [g for g in args.glosses if g.strip()]
    if args.sentence:
        return [g.strip() for g in args.sentence.split("|") if g.strip()]
    if args.glosses_file:
        txt = read_text_auto(args.glosses_file)
        if args.glosses_file.lower().endswith(".json"):
            return [str(g) for g in json.loads(txt)]
        return [l.strip() for l in txt.splitlines() if l.strip()]
    return []


def main(argv=None, detector_factory=None):
    args = build_parser().parse_args(argv)
    videos_dir = Path(args.videos)

    labels = args.labels or find_labels_file(videos_dir)
    if not labels or not Path(labels).exists():
        print("Không tìm thấy file nhãn. Hãy chỉ rõ bằng --labels \"đường\\dẫn\\file.csv\"")
        return 2
    records = load_records(labels)
    index = GlossIndex(records, args.region.split(","))
    print(f"Đã đọc {len(records)} video / {len(index.by_key)} khóa tra cứu từ: {labels}")

    if args.search:
        hits = index.search(args.search)
        print(f'\nCác nhãn chứa "{args.search}" ({len(hits)} kết quả đầu):')
        for r in hits:
            print(f"  {r['video']:<14} {r['label']}")
        return 0

    if detector_factory is None:
        detector_factory = lambda: MediaPipeDetector(args.complexity)

    if args.precompute_all:
        picks = {}
        for rec in index.recs:
            key = norm(rec["label"])
            if key not in picks:
                picks[key] = index.choose(index.lookup(rec["label"]))[0]
        todo = sorted(picks.values(), key=lambda r: natural_key(r["stem"]))
        print(f"Tính trước {len(todo)} video (mỗi gloss một video)...")
        for i, rec in enumerate(todo, 1):
            vp = videos_dir / rec["video"]
            try:
                _, hit = get_clip_data(vp, args.cache, detector_factory)
                print(f"[{i}/{len(todo)}] {rec['video']} {'(đã có)' if hit else 'xong'}")
            except Exception as e:
                print(f"[{i}/{len(todo)}] {rec['video']} LỖI: {e}")
        return 0

    glosses = get_glosses(args)
    if not glosses:
        raw = input('Nhập các gloss, ngăn cách bằng dấu | (ví dụ: bạn | đi học | có không): ')
        glosses = [g.strip() for g in raw.split("|") if g.strip()]
    if not glosses:
        print("Chưa có gloss nào.")
        return 2

    # ---- gloss -> video ----
    picks, problems = [], []
    for g in glosses:
        found, missing = index.resolve_one(g)
        picks += found
        for w in missing:
            sug = index.suggest(w)
            problems.append(f'Không có gloss "{w}"' + (f" (gần giống: {', '.join(sug)})" if sug else ""))
    print("\nChuỗi gloss -> video:")
    for g, rec, note in picks:
        print(f"  {g:<18} -> {rec['video']:<14} [{rec['label']}]" + (f"  ({note})" if note else ""))
    for p in problems:
        print("  CẢNH BÁO:", p)
    if not picks:
        return 1

    # ---- landmarks (cached) ----
    clips = []
    for i, (g, rec, _) in enumerate(picks, 1):
        vp = videos_dir / rec["video"]
        cache_file = Path(args.cache) / (rec["stem"] + ".npz")
        if not vp.exists() and not cache_file.exists():
            print(f"  CẢNH BÁO: không thấy video {vp}")
            continue
        try:
            raw, hit = get_clip_data(vp, args.cache, detector_factory)
        except Exception as e:
            print(f"  CẢNH BÁO: lỗi với {rec['video']}: {e}")
            continue
        clip, ok = process_clip(raw, args.fps, args)
        if clip is None:
            print(f"  CẢNH BÁO: {rec['video']} chỉ nhận diện được {ok:.0%} khung hình, bỏ qua")
            continue
        hands_ok = [float((~np.isnan(clip[k].reshape(len(clip[k]), -1)).any(axis=1)).mean())
                    for k in ("lh", "rh")]
        print(f"  [{i}/{len(picks)}] {rec['video']}: {len(clip['body'])} khung ({len(clip['body'])/args.fps:.1f}s), "
              f"có tay trái {hands_ok[0]:.0%} / tay phải {hands_ok[1]:.0%}" + ("" if hit else "  (vừa tính xong, đã lưu cache)"))
        clip.update({"gloss": g, "video": rec["video"]})
        clips.append(clip)
    if not clips:
        print("Không có video nào dùng được.")
        return 1

    # ---- one continuous timeline -> html ----
    timeline = assemble(clips, args.fps, args.transition, args.hold)
    if not Path(args.xbot).exists():
        print(f"Không thấy file Xbot: {args.xbot}  (dùng --xbot để chỉ đường dẫn)")
        return 2
    out = write_html(timeline, args.xbot, args.out, "Avatar: " + " | ".join(c["gloss"] for c in clips))
    print(f"\nXong: {timeline['n']} khung hình = {timeline['n']/args.fps:.1f} giây")
    print(f"Mở file này (bấm đúp): {out.resolve()}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())