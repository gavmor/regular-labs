#!/usr/bin/env python3
"""Render a pose-skeleton control video from ordinary footage.

The H3 Fun ControlNet takes an IMAGE batch as its control signal -- commonly a
DWPose pass. There is no pose preprocessor installed in comfyui-local (only
`Canny`), so this produces the equivalent offline with MediaPipe's
PoseLandmarker and draws an OpenPose-style skeleton on black.

WHY POSE AND NOT DEPTH: the node's own measurements found depth alone let the
figure drift in distance from camera and grow across the shot, while pose held
its size constant. Pose is the control worth testing first.

Output matches the generation exactly -- same width, height and frame count --
which the node requires (it raises when the control token count diverges from
the video segment, reporting both numbers).

    make_pose_control.py in.mp4 out.mp4 --width 832 --height 480 --frames 124
"""
import argparse
import os
import subprocess
import sys

try:
    import cv2
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
except ImportError as e:
    sys.exit(f"needs opencv-python-headless, numpy, mediapipe: {e}")

MODEL = os.path.expanduser("~/code/beauty-morph/models/pose_landmarker_heavy.task")

# MediaPipe Pose landmark indices -> OpenPose-ish limb chains, with the BGR
# colours OpenPose conventionally uses. Colour matters: the ControlNet was
# trained on coloured skeletons, not white-on-black lines.
LIMBS = [
    ((11, 13), (255, 0, 0)), ((13, 15), (255, 85, 0)),      # left arm
    ((12, 14), (0, 0, 255)), ((14, 16), (0, 85, 255)),      # right arm
    ((11, 12), (0, 255, 255)),                              # shoulders
    ((23, 24), (0, 255, 0)),                                # hips
    ((11, 23), (0, 255, 85)), ((12, 24), (0, 170, 255)),    # torso sides
    ((23, 25), (0, 255, 170)), ((25, 27), (0, 255, 255)),   # left leg
    ((24, 26), (85, 0, 255)), ((26, 28), (170, 0, 255)),    # right leg
    ((27, 31), (0, 200, 200)), ((28, 32), (200, 0, 200)),   # feet
    ((0, 11), (255, 0, 170)), ((0, 12), (255, 0, 85)),      # neck
]
JOINTS = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 31, 32]


def read_frames(path, n, w, h, crop=None):
    cap = cv2.VideoCapture(path)
    buf = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if crop:
            fh, fw = f.shape[:2]
            x0, y0, x1, y1 = crop
            f = f[int(y0 * fh):int(y1 * fh), int(x0 * fw):int(x1 * fw)]
        buf.append(f)
    cap.release()
    if not buf:
        raise SystemExit(f"no frames in {path}")
    # resample to exactly n frames -- the node demands an exact match
    idx = np.linspace(0, len(buf) - 1, n).round().astype(int)
    out = []
    for i in idx:
        f = buf[i]
        if crop:
            # Letterbox, never stretch. A tall crop squeezed into a 16:9 canvas
            # distorts limb proportions enough that PoseLandmarker loses the
            # figure -- measured 52% detection when stretching vs 100% when
            # fitting. Aspect fidelity matters more than filling the frame.
            fh, fw = f.shape[:2]
            sc = min(w / fw, h / fh)
            nw, nh = int(fw * sc), int(fh * sc)
            r = cv2.resize(f, (nw, nh))
            pad = np.zeros((h, w, 3), f.dtype)
            y0, x0 = (h - nh) // 2, (w - nw) // 2
            pad[y0:y0 + nh, x0:x0 + nw] = r
            f = pad
        else:
            f = cv2.resize(f, (w, h))
        out.append(f)
    return out, len(buf)


def figure_box(path, det, pad=0.06):
    """Normalised bbox of the figure across the whole clip, padded."""
    cap = cv2.VideoCapture(path)
    xs, ys = [], []
    i = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % 4 == 0:
            img = mp.Image(image_format=mp.ImageFormat.SRGB,
                           data=cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
            r = det.detect(img)
            if r.pose_landmarks:
                xs += [l.x for l in r.pose_landmarks[0]]
                ys += [l.y for l in r.pose_landmarks[0]]
        i += 1
    cap.release()
    if not xs:
        return None
    return (max(0.0, min(xs) - pad), max(0.0, min(ys) - pad),
            min(1.0, max(xs) + pad), min(1.0, max(ys) + pad))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--frames", type=int, default=124)
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--thickness", type=int, default=4)
    ap.add_argument("--autocrop", action="store_true",
                    help="crop the source to the figure before extracting, so "
                         "the skeleton fills the frame. The node's README names "
                         "subject size in frame -- not strength -- as the "
                         "binding constraint on control authority; raising "
                         "resolution alone does NOT change it (measured: "
                         "0.40MP and 0.98MP both gave a 7.1%% bbox).")
    args = ap.parse_args()

    if not os.path.isfile(MODEL):
        sys.exit(f"pose model missing: {MODEL}")

    det = vision.PoseLandmarker.create_from_options(
        vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL),
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.3,
            min_pose_presence_confidence=0.3))

    if args.autocrop:
        box = figure_box(args.src, det)
        if box:
            print(f"autocrop to x {box[0]:.3f}-{box[2]:.3f} y {box[1]:.3f}-{box[3]:.3f}")
        frames, src_n = read_frames(args.src, args.frames, args.width,
                                    args.height, crop=box)
    else:
        frames, src_n = read_frames(args.src, args.frames, args.width,
                                    args.height)
    print(f"source {src_n} frames -> {len(frames)} at {args.width}x{args.height}")

    tmp = args.dst + ".frames"
    os.makedirs(tmp, exist_ok=True)
    hits = 0
    for i, f in enumerate(frames):
        canvas = np.zeros((args.height, args.width, 3), np.uint8)
        img = mp.Image(image_format=mp.ImageFormat.SRGB,
                       data=cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        res = det.detect(img)
        if res.pose_landmarks:
            hits += 1
            lm = res.pose_landmarks[0]
            pt = {j: (int(lm[j].x * args.width), int(lm[j].y * args.height))
                  for j in JOINTS if j < len(lm)}
            for (a, b), colour in LIMBS:
                if a in pt and b in pt:
                    cv2.line(canvas, pt[a], pt[b], colour, args.thickness,
                             cv2.LINE_AA)
            for j, p in pt.items():
                cv2.circle(canvas, p, args.thickness, (255, 255, 255), -1,
                           cv2.LINE_AA)
        cv2.imwrite(os.path.join(tmp, f"{i:05d}.png"), canvas)

    print(f"pose detected in {hits}/{len(frames)} frames "
          f"({hits * 100 // max(len(frames), 1)}%)")
    if hits == 0:
        sys.exit("FAILED: no pose detected in any frame -- the control video "
                 "would be pure black and the ControlNet would steer nothing.")
    if hits < len(frames) * 0.5:
        print("WARNING: pose found in under half the frames; the control "
              "signal will drop out and the figure will drift where it does.")

    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(args.fps),
                    "-i", os.path.join(tmp, "%05d.png"),
                    "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                    args.dst], check=True)
    for f in os.listdir(tmp):
        os.unlink(os.path.join(tmp, f))
    os.rmdir(tmp)
    print(f"wrote {args.dst}")


if __name__ == "__main__":
    main()
