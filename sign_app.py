
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sign_app.py  -  Giao diện Xbot chạy trên localhost.

Chạy:  python sign_app.py      (hoặc bấm Run trong VS Code)
Trình duyệt tự mở. Gõ các từ (cách nhau bằng dấu phẩy) rồi Enter -> Xbot ký ngay,
không tải lại trang, không nạp lại mô hình.

Cần cùng thư mục:  sign_to_avatar.py, npz_to_xbot.py
"""
import collections
import json
import os
import re
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd

import npz_to_xbot as N
import sign_to_avatar as S

# =====================================================================
#  CẤU HÌNH - SỬA Ở ĐÂY
# =====================================================================
MAPPING_FILE = "anhxa.json"
NPZ_DIR = "npz"
XBOT_FILE = os.path.join("frontend_dis", "models", "Xbot.glb")
PORT = 8123
AUTO_OPEN = True

FPS = 30.0
TRANSITION_SECONDS = 0.25
HOLD_SECONDS = 0.2
TRIM_REST = True
FLIP_Y = False
CACHE_CLIPS = 500          # số clip đã xử lý giữ trong RAM
USE_GLOSS_MODEL = True     # bật model dịch câu -> gloss (file gloss_model.py)
DEFAULT_REGION = "B"       # giọng mặc định cho các từ có nhiều giọng: B = Bắc, T = Trung, N = Nam (đổi được trên giao diện)
STRICT_MODEL_GLOSS = True  # True: gloss của model KHÔNG có trong anhxa.json thì BỎ QUA (không đoán từ gần giống)
                           # False: tự thử bỏ dấu / tách cụm thành các từ nhỏ có sẵn

# Chữ hiện ra khi một từ đang được ký:
CAPTION_TOP_PERCENT = 15   # độ cao: % chiều cao cửa sổ, tính từ mép trên (0 = sát mép trên, 50 = giữa màn hình)
CAPTION_SIZE_PX = 34       # cỡ chữ (px)
# =====================================================================


HERE = Path(__file__).resolve().parent
REGION_NAMES = {"B": "Bắc", "T": "Trung", "N": "Nam"}


class Translator:
    """Nạp gloss_model.py (code model của bạn, giữ nguyên) ở luồng nền: trang mở ngay, model nạp xong là dùng được."""

    def __init__(self):
        self.ready = threading.Event()
        self.mod = None
        self.error = None
        self.lock = threading.Lock()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        t0 = time.time()
        print("Đang nạp model dịch câu -> gloss (chạy nền)...")
        try:
            try:
                import gloss_model
            except Exception as first:                   # đường dẫn tương đối: thử lại từ thư mục của file này
                if Path.cwd().resolve() == HERE:
                    raise
                sys.modules.pop("gloss_model", None)
                os.chdir(HERE)
                try:
                    import gloss_model
                except Exception:
                    raise first
            self.mod = gloss_model
            print(f"Đã nạp model dịch ({time.time() - t0:.1f}s).")
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            print("Không nạp được model dịch:", self.error)
        finally:
            self.ready.set()

    def state(self):
        if not self.ready.is_set():
            return "loading", None
        return ("ready", None) if self.mod else ("unavailable", self.error)

    def translate(self, text):
        self.ready.wait()
        if self.mod is None:
            raise RuntimeError("model dịch chưa dùng được: " + str(self.error))
        with self.lock:                                   # một câu một lần
            r = self.mod.predict_json(text)[0]
        return [g for g in r["Gloss"] if str(g).strip()], r.get("unknown_signs", [])


class Engine:
    """gloss -> file .npz -> timeline. Mọi clip đã xử lý được giữ trong RAM nên lần sau gần như tức thì."""

    def __init__(self, mapping_file, npz_dir, fps=FPS, transition=TRANSITION_SECONDS,
                 hold=HOLD_SECONDS, trim=TRIM_REST, flip_y=FLIP_Y):
        self.mapping_file = Path(mapping_file)
        self.npz_dir, self.fps, self.transition, self.hold, self.flip_y = Path(npz_dir), fps, transition, hold, flip_y
        self.ns = S.build_parser().parse_args([])
        self.ns.no_trim = not trim
        self.cache = collections.OrderedDict()
        self.lock = threading.Lock()
        self._load_mapping()

    def _load_mapping(self):
        df = pd.read_json(self.mapping_file)
        df = df.dropna(subset=["LABEL", "VIDEO"])
        self.exact = {str(l): str(v) for l, v in zip(df["LABEL"], df["VIDEO"])}      # như cell 1 của bạn
        self.index = S.GlossIndex([(str(v), str(l)) for v, l in zip(df["VIDEO"], df["LABEL"])])
        self.labels = sorted(self.exact, key=S.natural_key)
        # các giọng vùng miền của cùng một ký hiệu: W01177 -> {"B": "W01177B", "N": "W01177N", "T": "W01177T"}
        self.variants = {}
        for v in df["VIDEO"]:
            base, reg = S.parse_video(str(v))
            self.variants.setdefault(base, {})[reg] = Path(str(v)).stem
        # khớp "chặt": chỉ bỏ qua khác biệt hoa/thường, khoảng trắng, kiểu Unicode và phần trong ngoặc
        self.norm_map = {}
        for l, v in self.exact.items():
            self.norm_map[S.norm(l)] = v
        for l, v in self.exact.items():
            self.norm_map.setdefault(S.without_parens(l), v)
        self._mtime = self.mapping_file.stat().st_mtime

    def maybe_reload(self):
        """Sửa anhxa.json khi app đang chạy cũng được: lần gõ tiếp theo tự đọc lại."""
        try:
            if self.mapping_file.stat().st_mtime != self._mtime:
                with self.lock:
                    self._load_mapping()
                print(f"Đã nạp lại {self.mapping_file.name}: {len(self.labels)} gloss")
        except Exception as e:                             # file đang sửa dở / JSON lỗi: giữ bản cũ
            print(f"Không đọc lại được {self.mapping_file.name} (giữ bản cũ): {e}")

    # ---- text -> [(gloss, npz stem, note)] ----
    def npz_stems(self):
        try:
            return [Path(e.name).stem for e in os.scandir(self.npz_dir) if e.name.lower().endswith(".npz")]
        except OSError:
            return []

    def pick_available(self, gloss, stem):
        """Nếu <stem>.npz không có, thử: cùng mã ký hiệu khác giọng vùng (D0064 -> D0064B), rồi video khác cùng nhãn."""
        if (self.npz_dir / f"{stem}.npz").exists():
            return stem, ""
        base = S.parse_video(stem)[0].lower()
        near = [t for t in self.npz_stems() if S.parse_video(t)[0].lower() == base]
        if near:
            near.sort(key=lambda t: (self.index.region_pref.index(S.parse_video(t)[1])
                                     if S.parse_video(t)[1] in self.index.region_pref else 99, t))
            return near[0], f"dùng {near[0]}.npz thay cho {stem}.npz"
        have = set(self.npz_stems())
        for r in sorted(self.index.lookup(gloss), key=lambda r: S.natural_key(r["stem"])):
            if r["stem"] in have:
                return r["stem"], f"dùng video khác cùng nhãn: {r['stem']}"
        return stem, ""

    def regional(self, stem, region):
        """Từ có nhiều giọng (đuôi B/T/N) -> lấy giọng đã chọn; không có giọng đó thì lấy giọng khác. Từ chỉ có 1 video: giữ nguyên."""
        regs = {r: s for r, s in self.variants.get(S.parse_video(stem)[0], {}).items() if r}
        if len(regs) < 2:
            return stem, ""
        order = [region] + [r for r in "BTN" if r != region]
        for r in order:
            if r in regs and (self.npz_dir / f"{regs[r]}.npz").exists():
                return regs[r], "" if r == region else f"không có giọng {REGION_NAMES[region]}, dùng giọng {REGION_NAMES[r]}"
        return regs[next(r for r in order if r in regs)], ""

    def resolve(self, part, strict=False, region="B"):
        fname = self.exact.get(part)
        if not fname and strict:
            fname = self.norm_map.get(S.norm(part))
        if fname:
            found, missing = [(part, Path(fname).stem, "")], []
        elif strict:
            found, missing = [], [part]                  # không có nhãn này -> bỏ qua, không đoán
        else:
            f, missing = self.index.resolve_one(part)
            found = [(g, Path(rec["video"]).stem, note) for g, rec, note in f]
        out = []
        for g, stem, note in found:
            stem, rnote = self.regional(stem, region)
            stem2, note2 = self.pick_available(g, stem)
            out.append((g, stem2, "; ".join(x for x in (note, rnote, note2) if x)))
        return out, missing

    def parts(self, text):
        return [p.strip() for p in re.split(r"[,;|\n]+", text) if p.strip()]

    # ---- one processed clip (cached) ----
    def clip(self, stem):
        with self.lock:
            if stem in self.cache:
                self.cache.move_to_end(stem)
                return self.cache[stem], []
        path = self.npz_dir / f"{stem}.npz"
        if not path.exists():
            return None, [f"không thấy {path.name} trong thư mục {self.npz_dir.resolve()} "
                          f"(thư mục đang có {len(self.npz_stems())} file .npz)"]
        raw = N.load_npz(path)
        if self.flip_y:
            for k in ("pose", "lhand", "rhand"):
                raw[k][..., 1] *= -1
        warns = [f"{path.name}: {m}" for m in N.sanity_check(path.name, raw["pose"])]
        clip, ok = S.process_clip(raw, self.fps, self.ns)
        if clip is None:
            return None, warns + [f"{path.name}: chỉ có pose ở {ok:.0%} khung hình"]
        with self.lock:
            self.cache[stem] = clip
            while len(self.cache) > CACHE_CLIPS:
                self.cache.popitem(last=False)
        return clip, warns

    def build(self, text, mode="gloss", translator=None, region=None):
        """mode 'gloss': text là các gloss cách nhau bằng dấu phẩy. mode 'sentence': text là câu, model dịch ra gloss."""
        self.maybe_reload()
        region = str(region or DEFAULT_REGION).upper()[:1]
        region = region if region in REGION_NAMES else DEFAULT_REGION
        extra = {}
        if mode == "sentence":
            if translator is None:
                return {"ok": False, "error": "model dịch câu chưa được bật (USE_GLOSS_MODEL)"}
            t0 = time.perf_counter()
            glosses, _unknown = translator.translate(text)
            extra = {"sentence": text, "glosses": glosses, "translate_ms": round((time.perf_counter() - t0) * 1000)}
            if not glosses:
                return dict(extra, ok=False, error="model không trả về gloss nào")
            parts = glosses
        else:
            parts = self.parts(text)
        return dict(self.build_parts(parts, strict=(mode == "sentence" and STRICT_MODEL_GLOSS), region=region), **extra)

    def build_parts(self, parts, strict=False, region="B"):
        picks, warns = [], []
        for part in parts:
            found, missing = self.resolve(part, strict, region)
            picks += found
            for w in missing:
                if strict:
                    warns.append(f'Bỏ qua "{w}": không có trong {self.mapping_file.name}')
                else:
                    sug = self.index.suggest(w)
                    warns.append(f'Không có từ "{w}"' + (f" (gần giống: {', '.join(sug)})" if sug else ""))
        clips, used = [], []
        for gloss, stem, note in picks:
            clip, w = self.clip(stem)
            warns += w
            if clip is not None:
                clips.append(dict(clip, gloss=gloss, video=stem))
                used.append({"gloss": gloss, "video": stem, "note": note})
        for w in warns:
            print("  CẢNH BÁO:", w)
        if not clips:
            return {"ok": False, "error": "không có từ nào dùng được", "warnings": warns}
        timeline = S.assemble(clips, self.fps, self.transition, self.hold)
        return {"ok": True, "timeline": timeline, "picks": used, "warnings": warns}


def make_server(engine, xbot_file, port, translator=None):
    page = S.render_app_page(caption_vh=CAPTION_TOP_PERCENT, caption_px=CAPTION_SIZE_PX, region=DEFAULT_REGION)
    glb = Path(xbot_file).read_bytes()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"        # giữ kết nối: mỗi lần gõ từ không phải mở lại

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype, cache=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if cache:
                self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, page, "text/html; charset=utf-8", "no-store")
            elif path == "/xbot.glb":
                self._send(200, glb, "model/gltf-binary", "max-age=86400")
            elif path == "/api/glosses":
                engine.maybe_reload()
                self._send(200, json.dumps(engine.labels, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8", "no-store")
            elif path == "/api/info":
                st, err = translator.state() if translator else ("unavailable", "chưa bật (USE_GLOSS_MODEL = False)")
                self._send(200, json.dumps({"model": st, "error": err}, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8", "no-store")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path.split("?")[0] != "/api/sentence":
                return self._send(404, b"not found", "text/plain")
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n) or b"{}")
                res = engine.build(str(req.get("text", "")), req.get("mode", "gloss"), translator, req.get("region"))
            except Exception as e:                      # never kill the server
                res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            body = json.dumps(res, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")

    for p in range(port, port + 20):
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), Handler), p
        except OSError:
            continue
    raise OSError("không mở được cổng nào")


def main():
    here = Path(__file__).resolve().parent
    find = lambda p: Path(p) if Path(p).exists() or Path(p).is_absolute() else (here / p if (here / p).exists() else Path(p))
    mapping, npz_dir, xbot = find(MAPPING_FILE), find(NPZ_DIR), find(XBOT_FILE)
    for label, p in (("file ánh xạ (MAPPING_FILE)", mapping), ("thư mục npz (NPZ_DIR)", npz_dir), ("Xbot.glb (XBOT_FILE)", xbot)):
        if not p.exists():
            print(f"Không thấy {label}: {p}")
            return 2
    engine = Engine(mapping, npz_dir)
    translator = Translator() if USE_GLOSS_MODEL else None
    server, port = make_server(engine, xbot, PORT, translator)
    url = f"http://127.0.0.1:{port}/"
    print(f"Đã đọc {len(engine.labels)} gloss. Mở {url}   (Ctrl+C để dừng)")
    if AUTO_OPEN:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng.")
    return 0


if __name__ == "__main__":
    sys.exit(main())