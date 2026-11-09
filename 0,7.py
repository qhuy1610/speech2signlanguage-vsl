import cv2
import json
import mediapipe as mp
import numpy as np
from pathlib import Path
from tqdm import tqdm

# =====================================================================
# CẤU HÌNH ĐƯỜNG DẪN & THAM SỐ
# =====================================================================
# Thư mục gốc chứa các thư mục con (mỗi thư mục con là 1 từ vựng)
INPUT_DIR = Path(r"C:\Users\ADMIN\qh\processed\processed\frame_splited\test")

# Thư mục chứa các file .npz đầu ra
OUTPUT_NPZ_DIR = Path(r"C:\Users\ADMIN\qh\processed\processed\npz_output")

# Đường dẫn file JSON đầu ra sẽ được tạo
OUTPUT_JSON_PATH = Path(r"C:\Users\ADMIN\qh\processed\processed\output_mapping.json")

TARGET_FPS = 30.0
SMOOTH_BODY = 1.5
SMOOTH_HANDS = 1.0
HAND_GAP = 6
REST_THRESHOLD = 0.10

# =====================================================================
# CÁC HÀM XỬ LÝ DỮ LIỆU & CHUẨN HÓA (GIỮ NGUYÊN)
# =====================================================================
def assign_hands(hands, left_wrist, right_wrist):
    res = {"L": None, "R": None}
    if not hands: return res
    def d(a, b): return float(np.hypot(a[0] - b[0], a[1] - b[1]))
    if left_wrist is not None and right_wrist is not None:
        if len(hands) == 1:
            h = hands[0]
            res["L" if d(h[0], left_wrist) <= d(h[0], right_wrist) else "R"] = h[1]
        else:
            h0, h1 = hands[0], hands[1]
            if d(h0[0], left_wrist) + d(h1[0], right_wrist) <= d(h0[0], right_wrist) + d(h1[0], left_wrist):
                res["L"], res["R"] = h0[1], h1[1]
            else:
                res["L"], res["R"] = h1[1], h0[1]
    else:
        for h in hands:
            res["R" if h[2] == "Left" else "L"] = h[1]
    return res

def resample(arr, src_fps, dst_fps):
    T = len(arr)
    if T < 2 or abs(src_fps - dst_fps) < 1e-3: return arr
    new_T = max(2, int(round((T - 1) * dst_fps / src_fps)) + 1)
    t = np.linspace(0, T - 1, new_T)
    i0 = np.floor(t).astype(int)
    i1 = np.minimum(i0 + 1, T - 1)
    a = (t - i0).reshape((-1,) + (1,) * (arr.ndim - 1))
    return arr[i0] * (1 - a) + arr[i1] * a

def fill_gaps(arr, max_gap, hold_edges):
    T = len(arr)
    flat = arr.reshape(T, -1).astype(np.float64)
    valid = ~np.isnan(flat).any(axis=1)
    idx = np.where(valid)[0]
    if len(idx) == 0: return arr
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
    T = len(arr)
    flat = arr.reshape(T, -1).copy()
    valid = ~np.isnan(flat).any(axis=1)
    if not valid.any(): return arr
    last = None
    for i in range(T):
        if valid[i]: last = flat[i].copy()
        elif last is not None: flat[i] = last
    first = np.where(valid)[0][0]
    flat[:first] = flat[first]
    return flat.reshape(arr.shape)

def smooth_nan(arr, sigma):
    T = len(arr)
    if sigma <= 0 or T < 2: return arr
    flat = arr.reshape(T, -1).astype(np.float64)
    valid = ~np.isnan(flat).any(axis=1)
    if not valid.any(): return arr
    i = np.arange(T)
    W = np.exp(-0.5 * ((i[:, None] - i[None, :]) / sigma) ** 2) * valid[None, :]
    num = W @ np.where(valid[:, None], flat, 0.0)
    den = np.maximum(W.sum(axis=1, keepdims=True), 1e-9)
    out = num / den
    out[~valid] = np.nan
    return out.reshape(arr.shape).astype(np.float32)

def active_range(pose, threshold, pad):
    T = len(pose)
    hips_y = (pose[:, 23, 1] + pose[:, 24, 1]) / 2
    wrist_y = np.minimum(pose[:, 15, 1], pose[:, 16, 1])
    idx = np.where(wrist_y < hips_y - threshold)[0]
    if len(idx) == 0: return 0, T
    return max(0, int(idx[0]) - pad), min(T, int(idx[-1]) + pad + 1)

# =====================================================================
# HÀM XỬ LÝ MỘT VIDEO
# =====================================================================
def process_single_video(video_path, output_npz_path, label, pose_det, hands_det):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return False

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not src_fps or src_fps != src_fps or src_fps <= 1:
        src_fps = 30.0

    pose_l, lh_l, rh_l = [], [], []
    nan_pose = np.full((33, 3), np.nan, np.float32)
    nan_hand = np.full((21, 3), np.nan, np.float32)

    while True:
        ok, frame = cap.read()
        if not ok: break
        h, w = frame.shape[:2]
        if w != 640 and w > 0:
            frame = cv2.resize(frame, (640, int(h * 640 / w)))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        pr = pose_det.process(rgb)
        p_world = nan_pose.copy()
        left_w = right_w = None
        if pr.pose_world_landmarks:
            p_world = np.array([[l.x, l.y, l.z] for l in pr.pose_world_landmarks.landmark], dtype=np.float32)
        if pr.pose_landmarks:
            lm = pr.pose_landmarks.landmark
            left_w, right_w = (lm[15].x, lm[15].y), (lm[16].x, lm[16].y)

        hr = hands_det.process(rgb)
        hands = []
        if hr.multi_hand_world_landmarks and hr.multi_hand_landmarks:
            for wl, il, hd in zip(hr.multi_hand_world_landmarks, hr.multi_hand_landmarks, hr.multi_handedness):
                world = np.array([[l.x, l.y, l.z] for l in wl.landmark], dtype=np.float32)
                hands.append(((il.landmark[0].x, il.landmark[0].y), world, hd.classification[0].label))

        a = assign_hands(hands, left_w, right_w)
        pose_l.append(p_world)
        lh_l.append(a["L"] if a["L"] is not None else nan_hand)
        rh_l.append(a["R"] if a["R"] is not None else nan_hand)

    cap.release()
    if not pose_l:
        return False

    raw_pose = np.stack(pose_l).astype(np.float32)
    raw_lh = np.stack(lh_l).astype(np.float32)
    raw_rh = np.stack(rh_l).astype(np.float32)

    pose = resample(raw_pose, src_fps, TARGET_FPS)
    lh = resample(raw_lh, src_fps, TARGET_FPS)
    rh = resample(raw_rh, src_fps, TARGET_FPS)

    pose = fill_gaps(pose, max_gap=int(TARGET_FPS * 0.6), hold_edges=True)
    pose = hold_last_valid(pose)
    pose = smooth_nan(pose, SMOOTH_BODY)
    
    lh = smooth_nan(fill_gaps(lh, max_gap=HAND_GAP, hold_edges=False), SMOOTH_HANDS)
    rh = smooth_nan(fill_gaps(rh, max_gap=HAND_GAP, hold_edges=False), SMOOTH_HANDS)

    a_idx, b_idx = active_range(pose, REST_THRESHOLD, int(round(TARGET_FPS * 0.12)))
    pose, lh, rh = pose[a_idx:b_idx], lh[a_idx:b_idx], rh[a_idx:b_idx]

    Path(output_npz_path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_npz_path,
        pose=pose,
        lhand=lh,
        rhand=rh,
        fps=TARGET_FPS,
        label=label,
        version=1
    )
    return True

# =====================================================================
# HÀM CHÍNH XỬ LÝ THEO CẤU TRÚC MỚI
# =====================================================================
def main():
    if not INPUT_DIR.exists():
        print(f"[LỖI] Không tìm thấy thư mục đầu vào: {INPUT_DIR}")
        return

    OUTPUT_NPZ_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    mp_pose = mp.solutions.pose
    mp_hands = mp.solutions.hands

    success_count = 0
    fail_count = 0
    
    # Danh sách để xuất ra file JSON
    json_output_data = []

    print(f"Bắt đầu quét thư mục: {INPUT_DIR}")
    
    with mp_pose.Pose(static_image_mode=False, model_complexity=1, smooth_landmarks=True) as pose_det, \
         mp_hands.Hands(static_image_mode=False, max_num_hands=2, model_complexity=1) as hands_det:
        
        # Duyệt qua các thư mục con trong thư mục 'test'
        for label_dir in INPUT_DIR.iterdir():
            if not label_dir.is_dir():
                continue
                
            label = label_dir.name # Tên thư mục con chính là nhãn (VD: "ăn")
            
            # Quét tất cả các file mp4 trong thư mục từ vựng này
            video_paths = list(label_dir.glob("*.mp4"))
            if not video_paths:
                continue
                
            processed_videos_for_label = []
            
            # Xử lý từng video trong thư mục từ vựng
            for video_path in tqdm(video_paths, desc=f"Đang xử lý [{label}]"):
                video_name = video_path.name
                
                # Tạo tên file npz (thêm tên nhãn ở đầu để tránh trùng lặp nếu 2 thư mục đều có file "a.mp4")
                output_npz_name = f"{label}_{video_path.stem}.npz"
                output_npz_path = OUTPUT_NPZ_DIR / output_npz_name

                success = process_single_video(video_path, output_npz_path, label, pose_det, hands_det)
                
                if success:
                    success_count += 1
                    # Ghi nhận lại video này đã thành công cho label hiện tại
                    processed_videos_for_label.append(video_name)
                else:
                    fail_count += 1
                    print(f"\n[LỖI] Xử lý thất bại video: {video_path}")
            
            # Nếu có video xử lý thành công, thêm vào kết quả JSON
            if processed_videos_for_label:
                json_output_data.append({
                    "VIDEO": ", ".join(processed_videos_for_label),
                    "LABEL": label
                })

    # Lưu kết quả mapping ra file JSON
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(json_output_data, f, ensure_ascii=False, indent=4)

    print(f"\n[HOÀN TẤT] Thành công: {success_count} | Thất bại: {fail_count}")
    print(f"Các file NPZ được lưu tại: {OUTPUT_NPZ_DIR}")
    print(f"File JSON danh sách được lưu tại: {OUTPUT_JSON_PATH}")

if __name__ == "__main__":
    main()