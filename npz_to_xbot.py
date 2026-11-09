# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-
# """
# npz_to_xbot.py
# ==============
# Bước tiếp theo sau 2 cell của bạn:

#     gloss  --(anhxa.json)-->  tên file .npz  --(đọc pose / lhand / rhand / fps)-->
#     ghép liên tục + làm mượt  -->  1 file HTML: Xbot ký cả câu liên tục.

# Cần cùng thư mục với file này:  sign_to_avatar.py  (đã gửi trước đó, dùng lại phần player).

# Ví dụ:
#     python npz_to_xbot.py --words "tuần sau" "học" "không có" --mapping anhxa.json --npz-dir npz --open
# """
# import argparse
# import os
# import sys
# from pathlib import Path

# import numpy as np
# import pandas as pd

# import sign_to_avatar as S


# # ---------------------------------------------------------------------------
# # Cell 1 của bạn (giữ nguyên logic): gloss -> tên file
# # ---------------------------------------------------------------------------
# def map_words_to_files(input_words, mapping_file, output_ext=None):
#     df = pd.read_json(mapping_file)
#     mapping_dict = dict(zip(df['LABEL'], df['VIDEO']))
#     results = {}
#     for word in input_words:
#         file_name = mapping_dict.get(word)
#         if file_name and output_ext:
#             file_name = f"{os.path.splitext(file_name)[0]}{output_ext}"
#         results[word] = file_name
#     return results


# # ---------------------------------------------------------------------------
# # Đọc .npz theo định dạng của bạn: pose (F,33,3), lhand (F,21,3), rhand (F,21,3), fps
# # ---------------------------------------------------------------------------
# def load_npz(path):
#     d = np.load(path)
#     pose = d["pose"].astype(np.float32)
#     lh = d["lhand"].astype(np.float32)
#     rh = d["rhand"].astype(np.float32)
#     fps = float(d["fps"]) if "fps" in d.files else 30.0
#     # khung hình "không phát hiện" có thể được lưu bằng 0 thay vì NaN -> đổi thành NaN
#     for arr in (pose, lh, rh):
#         arr[(arr == 0).reshape(len(arr), -1).all(axis=1)] = np.nan
#     return {"pose": pose, "lhand": lh, "rhand": rh, "fps": fps}


# def sanity_check(name, pose):
#     """In cảnh báo nếu tọa độ không giống 'world landmarks' của MediaPipe (mét, gốc ở hông, y hướng xuống)."""
#     ok = ~np.isnan(pose.reshape(len(pose), -1)).any(axis=1)
#     if not ok.any():
#         return ["không có khung hình nào có pose"]
#     p = pose[ok]
#     warn = []
#     shoulder = float(np.nanmedian(np.linalg.norm(p[:, 11] - p[:, 12], axis=1)))
#     hip_x = float(np.nanmean((p[:, 23, 0] + p[:, 24, 0]) / 2))
#     sh_y = float(np.nanmean((p[:, 11, 1] + p[:, 12, 1]) / 2))
#     hp_y = float(np.nanmean((p[:, 23, 1] + p[:, 24, 1]) / 2))
#     if abs(hip_x) > 0.3:
#         warn.append(f"hông lệch x={hip_x:.2f}: có vẻ đây là tọa độ ẢNH (0..1), không phải tọa độ world (mét) -> Xbot sẽ cử động sai")
#     if not 0.15 <= shoulder <= 0.7:
#         warn.append(f"bề rộng vai = {shoulder:.2f} (world thường ~0.3-0.45 m)")
#     if sh_y > hp_y:
#         warn.append("vai nằm DƯỚI hông theo trục y: dữ liệu có vẻ y hướng lên. Thử thêm --flip-y")
#     return warn


# def main(argv=None):
#     ap = argparse.ArgumentParser(description="Chuỗi gloss -> .npz -> Xbot chuyển động liên tục (HTML).")
#     ap.add_argument("--words", nargs="+", required=True, help='Ví dụ: --words "tuần sau" "học" "không có"')
#     ap.add_argument("--mapping", default="anhxa.json", help="File JSON có cột VIDEO và LABEL")
#     ap.add_argument("--npz-dir", default=".", help="Thư mục chứa các file .npz")
#     ap.add_argument("--xbot", default=S.DEFAULT_XBOT, help="File Xbot.glb")
#     ap.add_argument("--out", default=os.path.join("output", "sentence.html"))
#     ap.add_argument("--fps", type=float, default=30.0)
#     ap.add_argument("--transition", type=float, default=0.25, help="Giây chuyển tiếp giữa 2 từ")
#     ap.add_argument("--hold", type=float, default=0.2, help="Giây giữ tư thế đầu/cuối")
#     ap.add_argument("--no-trim", action="store_true", help="Không cắt đoạn tay buông ở đầu/cuối")
#     ap.add_argument("--flip-y", action="store_true", help="Nếu dữ liệu .npz có trục y hướng lên")
#     ap.add_argument("--open", action="store_true", help="Mở file HTML sau khi tạo")
#     a = ap.parse_args(argv)

#     # ---- gloss -> tên .npz (đúng như cell 1 của bạn) ----
#     npz_names = map_words_to_files(a.words, a.mapping, output_ext=".npz")

#     # chỗ không khớp tuyệt đối: thử tra không phân biệt hoa/thường/dấu
#     fallback = None
#     for word, fname in list(npz_names.items()):
#         if fname:
#             continue
#         if fallback is None:
#             fallback = S.GlossIndex(S.load_records(a.mapping))
#         found, _ = fallback.resolve_one(word)
#         if found:
#             npz_names[word] = Path(found[0][1]["video"]).with_suffix(".npz").name
#             print(f'  (gần đúng) "{word}" -> {npz_names[word]}')

#     print("\nGloss -> file:")
#     for w, f in npz_names.items():
#         print(f"  {w:<18} -> {f}")

#     # ---- ns: các thông số xử lý mặc định của sign_to_avatar ----
#     ns = S.build_parser().parse_args([])
#     ns.no_trim = a.no_trim

#     clips = []
#     for word, fname in npz_names.items():
#         if not fname:
#             print(f'  CẢNH BÁO: không có gloss "{word}" trong {a.mapping}')
#             continue
#         path = Path(a.npz_dir) / fname
#         if not path.exists():
#             print(f"  CẢNH BÁO: không thấy file {path}")
#             continue
#         raw = load_npz(path)
#         if a.flip_y:
#             for k in ("pose", "lhand", "rhand"):
#                 raw[k][..., 1] *= -1
#         for msg in sanity_check(fname, raw["pose"]):
#             print(f"  CẢNH BÁO [{fname}]: {msg}")
#         clip, ok = S.process_clip(raw, a.fps, ns)
#         if clip is None:
#             print(f"  CẢNH BÁO: {fname} chỉ có pose ở {ok:.0%} khung hình, bỏ qua")
#             continue
#         n = len(clip["body"])
#         frac = [float((~np.isnan(clip[k].reshape(n, -1)).any(axis=1)).mean()) for k in ("lh", "rh")]
#         print(f"  {fname}: {n} khung ({n / a.fps:.1f}s), có tay trái {frac[0]:.0%} / tay phải {frac[1]:.0%}")
#         clip.update({"gloss": word, "video": fname})
#         clips.append(clip)

#     if not clips:
#         print("Không có clip nào dùng được.")
#         return 1
#     if not Path(a.xbot).exists():
#         print(f"Không thấy file Xbot: {a.xbot}  (dùng --xbot để chỉ đường dẫn)")
#         return 2

#     timeline = S.assemble(clips, a.fps, a.transition, a.hold)
#     out = S.write_html(timeline, a.xbot, a.out, "Avatar: " + " | ".join(c["gloss"] for c in clips))
#     print(f"\nXong: {timeline['n']} khung = {timeline['n'] / a.fps:.1f} giây")
#     print(f"Mở file này (bấm đúp): {out.resolve()}")
#     if a.open:
#         import webbrowser
#         webbrowser.open(out.resolve().as_uri())
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())











#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
npz_to_xbot.py
==============
gloss  --(anhxa.json)-->  tên file .npz  -->  ghép liên tục + làm mượt  -->  1 file HTML: Xbot ký cả câu.

Cần cùng thư mục với file này:  sign_to_avatar.py

CÁCH DÙNG (chọn 1 trong 3):
  1) Sửa khối CẤU HÌNH bên dưới rồi bấm Run (VS Code / PyCharm) hoặc:  python npz_to_xbot.py
  2) Gọi từ code / notebook:
         from npz_to_xbot import build_avatar
         build_avatar(["tuần sau", "học", "không có"])
  3) Dòng lệnh:  python npz_to_xbot.py --words "tuần sau" "học" "không có"
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import sign_to_avatar as S

# =====================================================================
#  CẤU HÌNH - SỬA Ở ĐÂY (không cần gõ gì trong terminal)
# =====================================================================
WORDS = ["tiếp tân", "tỉnh","địa chỉ"]                 # <- chuỗi gloss cần ký

MAPPING_FILE = "anhxa.json"                             # file ánh xạ có cột VIDEO và LABEL
NPZ_DIR = "npz"                                         # thư mục chứa các file .npz
XBOT_FILE = os.path.join("frontend_dis", "models", "BoomBox.glb")
OUT_HTML = os.path.join("output", "sentence.html")      # file kết quả
AUTO_OPEN = True                                        # tạo xong tự mở trong trình duyệt

FPS = 30.0
TRANSITION_SECONDS = 0.25                               # chuyển tiếp giữa 2 từ
HOLD_SECONDS = 0.2                                      # giữ tư thế đầu/cuối
TRIM_REST = True                                        # cắt đoạn tay buông ở đầu/cuối mỗi video
FLIP_Y = False                                          # True nếu dữ liệu .npz có trục y hướng lên
# =====================================================================

_HERE = Path(__file__).resolve().parent


def _find(path):
    """Đường dẫn tương đối: thử theo thư mục đang chạy, rồi theo thư mục của file .py này."""
    p = Path(path)
    if p.exists() or p.is_absolute():
        return p
    q = _HERE / p
    return q if q.exists() else p


# ---------------------------------------------------------------------------
# Cell 1 của bạn (giữ nguyên logic): gloss -> tên file
# ---------------------------------------------------------------------------
def map_words_to_files(input_words, mapping_file, output_ext=None):
    df = pd.read_json(mapping_file)
    mapping_dict = dict(zip(df['LABEL'], df['VIDEO']))
    results = {}
    for word in input_words:
        file_name = mapping_dict.get(word)
        if file_name and output_ext:
            file_name = f"{os.path.splitext(file_name)[0]}{output_ext}"
        results[word] = file_name
    return results


# ---------------------------------------------------------------------------
# Đọc .npz theo định dạng của bạn: pose (F,33,3), lhand (F,21,3), rhand (F,21,3), fps
# ---------------------------------------------------------------------------
def load_npz(path):
    d = np.load(path)
    pose = d["pose"].astype(np.float32)
    lh = d["lhand"].astype(np.float32)
    rh = d["rhand"].astype(np.float32)
    fps = float(d["fps"]) if "fps" in d.files else 30.0
    # khung hình "không phát hiện" có thể được lưu bằng 0 thay vì NaN -> đổi thành NaN
    for arr in (pose, lh, rh):
        arr[(arr == 0).reshape(len(arr), -1).all(axis=1)] = np.nan
    return {"pose": pose, "lhand": lh, "rhand": rh, "fps": fps}


def sanity_check(name, pose):
    """Cảnh báo nếu tọa độ không giống 'world landmarks' của MediaPipe (mét, gốc ở hông, y hướng xuống)."""
    ok = ~np.isnan(pose.reshape(len(pose), -1)).any(axis=1)
    if not ok.any():
        return ["không có khung hình nào có pose"]
    p = pose[ok]
    warn = []
    shoulder = float(np.nanmedian(np.linalg.norm(p[:, 11] - p[:, 12], axis=1)))
    hip_x = float(np.nanmean((p[:, 23, 0] + p[:, 24, 0]) / 2))
    sh_y = float(np.nanmean((p[:, 11, 1] + p[:, 12, 1]) / 2))
    hp_y = float(np.nanmean((p[:, 23, 1] + p[:, 24, 1]) / 2))
    if abs(hip_x) > 0.3:
        warn.append(f"hông lệch x={hip_x:.2f}: có vẻ đây là tọa độ ẢNH (0..1), không phải tọa độ world (mét) -> Xbot sẽ cử động sai")
    if not 0.15 <= shoulder <= 0.7:
        warn.append(f"bề rộng vai = {shoulder:.2f} (world thường ~0.3-0.45 m)")
    if sh_y > hp_y:
        warn.append("vai nằm DƯỚI hông theo trục y: dữ liệu có vẻ y hướng lên. Đặt FLIP_Y = True")
    return warn


# ---------------------------------------------------------------------------
# Hàm chính: gọi trực tiếp từ code
# ---------------------------------------------------------------------------
def build_avatar(words=None, mapping_file=None, npz_dir=None, xbot_file=None, out_html=None,
                 fps=None, transition=None, hold=None, trim=None, flip_y=None, open_browser=None):
    """Trả về đường dẫn file HTML (hoặc None nếu không tạo được). Tham số bỏ trống = lấy từ khối CẤU HÌNH."""
    words = list(WORDS if words is None else words)
    mapping_file = _find(MAPPING_FILE if mapping_file is None else mapping_file)
    npz_dir = _find(NPZ_DIR if npz_dir is None else npz_dir)
    xbot_file = _find(XBOT_FILE if xbot_file is None else xbot_file)
    out_html = OUT_HTML if out_html is None else out_html
    fps = FPS if fps is None else fps
    transition = TRANSITION_SECONDS if transition is None else transition
    hold = HOLD_SECONDS if hold is None else hold
    trim = TRIM_REST if trim is None else trim
    flip_y = FLIP_Y if flip_y is None else flip_y
    open_browser = AUTO_OPEN if open_browser is None else open_browser

    if not words:
        print("Danh sách WORDS đang trống.")
        return None
    if not Path(mapping_file).exists():
        print(f"Không thấy file ánh xạ: {mapping_file}")
        return None

    # ---- gloss -> tên .npz (đúng như cell 1 của bạn) ----
    npz_names = map_words_to_files(words, mapping_file, output_ext=".npz")

    # chỗ không khớp tuyệt đối: thử tra không phân biệt hoa/thường/dấu
    fallback = None
    for word, fname in list(npz_names.items()):
        if fname:
            continue
        if fallback is None:
            fallback = S.GlossIndex(S.load_records(mapping_file))
        found, _ = fallback.resolve_one(word)
        if found:
            npz_names[word] = Path(found[0][1]["video"]).with_suffix(".npz").name
            print(f'  (gần đúng) "{word}" -> {npz_names[word]}')

    print("\nGloss -> file:")
    for w, f in npz_names.items():
        print(f"  {w:<18} -> {f}")

    ns = S.build_parser().parse_args([])      # thông số xử lý mặc định của sign_to_avatar
    ns.no_trim = not trim

    clips = []
    for word, fname in npz_names.items():
        if not fname:
            print(f'  CẢNH BÁO: không có gloss "{word}" trong {mapping_file}')
            continue
        path = Path(npz_dir) / fname
        if not path.exists():
            print(f"  CẢNH BÁO: không thấy file {path}")
            continue
        raw = load_npz(path)
        if flip_y:
            for k in ("pose", "lhand", "rhand"):
                raw[k][..., 1] *= -1
        for msg in sanity_check(fname, raw["pose"]):
            print(f"  CẢNH BÁO [{fname}]: {msg}")
        clip, ok = S.process_clip(raw, fps, ns)
        if clip is None:
            print(f"  CẢNH BÁO: {fname} chỉ có pose ở {ok:.0%} khung hình, bỏ qua")
            continue
        n = len(clip["body"])
        frac = [float((~np.isnan(clip[k].reshape(n, -1)).any(axis=1)).mean()) for k in ("lh", "rh")]
        print(f"  {fname}: {n} khung ({n / fps:.1f}s), có tay trái {frac[0]:.0%} / tay phải {frac[1]:.0%}")
        clip.update({"gloss": word, "video": fname})
        clips.append(clip)

    if not clips:
        print("Không có clip nào dùng được.")
        return None
    if not Path(xbot_file).exists():
        print(f"Không thấy file Xbot: {xbot_file}  (sửa XBOT_FILE ở đầu file)")
        return None

    timeline = S.assemble(clips, fps, transition, hold)
    out = S.write_html(timeline, xbot_file, out_html, "Avatar: " + " | ".join(c["gloss"] for c in clips))
    print(f"\nXong: {timeline['n']} khung = {timeline['n'] / fps:.1f} giây")
    print(f"Mở file này (bấm đúp): {out.resolve()}")
    if open_browser:
        import webbrowser
        webbrowser.open(out.resolve().as_uri())
    return out


# ---------------------------------------------------------------------------
# Dòng lệnh (không bắt buộc): mọi tham số đều tùy chọn, bỏ trống = dùng khối CẤU HÌNH
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Chuỗi gloss -> .npz -> Xbot chuyển động liên tục (HTML).")
    ap.add_argument("--words", nargs="+", help="Bỏ trống = dùng WORDS trong code")
    ap.add_argument("--mapping")
    ap.add_argument("--npz-dir")
    ap.add_argument("--xbot")
    ap.add_argument("--out")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--transition", type=float)
    ap.add_argument("--hold", type=float)
    ap.add_argument("--no-trim", action="store_true", help="Không cắt đoạn tay buông ở đầu/cuối")
    ap.add_argument("--flip-y", action="store_true")
    ap.add_argument("--open", action="store_true", help="Mở file HTML sau khi tạo")
    ap.add_argument("--no-open", action="store_true", help="Không tự mở file HTML")
    a = ap.parse_args(argv)
    open_flag = True if a.open else (False if a.no_open else None)
    out = build_avatar(words=a.words, mapping_file=a.mapping, npz_dir=a.npz_dir, xbot_file=a.xbot,
                       out_html=a.out, fps=a.fps, transition=a.transition, hold=a.hold,
                       trim=False if a.no_trim else None, flip_y=True if a.flip_y else None,
                       open_browser=open_flag)
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())