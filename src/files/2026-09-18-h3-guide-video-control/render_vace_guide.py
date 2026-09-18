#!/usr/bin/env python3
"""Render the VACE guide video and install it for the H3 arms.

Stdlib only, no third-party deps -- house style for Concourse task scripts.
The model stack lives in comfyui-local; this is a thin HTTP client, so GPU work
happens over there while the caller holds gpu-lock.

Three things happen here, and the middle one is the reason this is a script
rather than a couple of shell lines:

  1. POST the guide graph, wait for it, pull the resulting mp4
  2. TRIM to exactly --target-frames. Wan VACE needs 4n+1, H3 needs 17n+5, and
     294 satisfies only the second. H3FunControlApply hard-fails on a frame
     count mismatch rather than padding, so an untrimmed guide fails the arms
     AFTER they have loaded and taken the lock.
  3. Install into comfyui-local's input/ dir, because LoadVideo resolves names
     against that directory and the H3 arms name the guide statically.

Timing is read from ComfyUI's own execution timestamps, not wall clock, so the
reported cost excludes queueing and HTTP overhead. That number is the one the
experiment's secondary claim is scored against.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def post_prompt(base, graph):
    body = json.dumps({"prompt": graph}).encode()
    req = urllib.request.Request(
        f"{base}/prompt", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def get_json(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def wait_for(base, pid, poll=5, limit=7200):
    """Block until prompt `pid` leaves the queue, then return its history."""
    start = time.time()
    while time.time() - start < limit:
        try:
            hist = get_json(f"{base}/history/{pid}")
        except urllib.error.URLError as exc:
            print(f"  (history fetch failed, retrying: {exc})")
            time.sleep(poll)
            continue

        if pid in hist:
            entry = hist[pid]
            status = (entry.get("status") or {}).get("status_str")
            if status == "error":
                msgs = []
                for kind, payload in (entry.get("status") or {}).get("messages", []):
                    if kind == "execution_error":
                        msgs.append(
                            f"{payload.get('node_type')}: {payload.get('exception_message')}"
                        )
                raise SystemExit("FAILED: guide render errored -- " + "; ".join(msgs))
            return entry
        time.sleep(poll)
    raise SystemExit(f"FAILED: guide render did not finish within {limit}s")


def exec_seconds(entry):
    """Render time from ComfyUI's own timestamps, in seconds."""
    msgs = (entry.get("status") or {}).get("messages", [])
    start = end = None
    for kind, payload in msgs:
        if kind == "execution_start":
            start = payload.get("timestamp")
        if kind in ("execution_success", "execution_error"):
            end = payload.get("timestamp")
    if start and end:
        return (end - start) / 1000.0
    return None


def find_output(entry):
    for node_out in (entry.get("outputs") or {}).values():
        for key in ("videos", "gifs", "images"):
            for item in node_out.get(key, []) or []:
                if str(item.get("filename", "")).endswith(".mp4"):
                    return item
    return None


def frame_count(path):
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-count_frames", "-show_entries", "stream=nb_read_frames",
            "-of", "default=nw=1:nk=1", path,
        ],
        capture_output=True, text=True, check=True,
    )
    return int(out.stdout.strip())


def dimensions(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True, check=True,
    )
    w, h = out.stdout.strip().split("x")
    return int(w), int(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfyui-url", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--target-frames", type=int, required=True)
    ap.add_argument(
        "--target-width",
        type=int,
        required=True,
        help="H3's render width; the guide is upscaled to match",
    )
    ap.add_argument(
        "--target-height",
        type=int,
        required=True,
        help="H3's render height; the guide is upscaled to match",
    )
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument(
        "--install-name",
        default="vace_guide_294.mp4",
        help="filename the H3 arms' LoadVideo node expects",
    )
    ap.add_argument(
        "--reuse-if-present",
        action="store_true",
        help=(
            "skip the render if comfyui-local already has a guide of the right "
            "frame count installed under --install-name"
        ),
    )
    args = ap.parse_args()

    base = args.comfyui_url.rstrip("/")
    os.makedirs(args.out_dir, exist_ok=True)

    # The guide is an instrument, not a result: if a valid one is already
    # installed, re-rendering it burns GPU to produce the same file. This
    # matters because the guide costs ~42 minutes on this box, and a downstream
    # failure (a missing module in the ARMS task, say) should not force it to
    # be paid twice.
    if args.reuse_if_present:
        q = urllib.parse.urlencode(
            {"filename": args.install_name, "subfolder": "", "type": "input"}
        )
        probe = os.path.join(args.out_dir, "existing_guide.mp4")
        try:
            with urllib.request.urlopen(f"{base}/view?{q}", timeout=300) as r, open(
                probe, "wb"
            ) as fh:
                shutil.copyfileobj(r, fh)
            have = frame_count(probe)
            have_w, have_h = dimensions(probe)
            if (have, have_w, have_h) == (
                args.target_frames,
                args.target_width,
                args.target_height,
            ):
                print(
                    f"reusing installed guide {args.install_name}: "
                    f"{have} frames at {have_w}x{have_h}, "
                    f"{os.path.getsize(probe)} bytes -- skipping render"
                )
                json.dump(
                    {
                        "reused": True,
                        "installed_as": args.install_name,
                        "frames_after_trim": have,
                        "bytes": os.path.getsize(probe),
                        "guide_seconds_comfyui_clock": None,
                    },
                    open(args.report, "w"),
                    indent=2,
                )
                return 0
            print(
                f"installed guide is {have}f {have_w}x{have_h}, need "
                f"{args.target_frames}f {args.target_width}x{args.target_height}; "
                "re-rendering"
            )
        except Exception as exc:
            print(f"no reusable guide ({exc}); rendering one")

    graph = json.load(open(args.graph))

    print(f"submitting guide graph ({len(graph)} nodes) to {base}")
    t0 = time.time()
    resp = post_prompt(base, graph)
    pid = resp.get("prompt_id")
    if not pid:
        raise SystemExit(f"FAILED: no prompt_id in response: {resp}")
    print(f"  prompt_id {pid}")

    entry = wait_for(base, pid)
    wall = time.time() - t0
    secs = exec_seconds(entry)
    print(f"  done: {secs:.1f}s by ComfyUI's clock, {wall:.1f}s wall")

    item = find_output(entry)
    if not item:
        raise SystemExit("FAILED: no .mp4 in the guide's outputs")

    q = urllib.parse.urlencode(
        {
            "filename": item["filename"],
            "subfolder": item.get("subfolder", ""),
            "type": item.get("type", "output"),
        }
    )
    raw = os.path.join(args.out_dir, "vace_guide_raw.mp4")
    with urllib.request.urlopen(f"{base}/view?{q}", timeout=600) as r, open(raw, "wb") as fh:
        shutil.copyfileobj(r, fh)
    print(f"  fetched {raw} ({os.path.getsize(raw)} bytes)")

    got = frame_count(raw)
    print(f"  guide has {got} frames, target {args.target_frames}")
    if got < args.target_frames:
        raise SystemExit(
            f"FAILED: guide is SHORTER than the target ({got} < {args.target_frames}). "
            "Raise the graph's length; trimming cannot invent frames."
        )

    trimmed = os.path.join(args.out_dir, args.install_name)
    # Trim AND scale in one pass. The scale is not cosmetic: H3FunControlApply
    # packs the control video to tokens and compares against the shot's own
    # token count, so a guide at the wrong resolution fails with
    #   "it packs to 33930 tokens but the video segment of the stream is 82041"
    # Those divide to the same 87 temporal positions at 390 and 943 tokens per
    # frame -- i.e. the frame counts already matched and ONLY the spatial
    # dimensions were wrong. Generating the guide at the source clip's 832x480
    # and handing it to a 1312x736 shot is exactly that failure.
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", raw,
            "-vf",
            (
                f"select='lt(n,{args.target_frames})',"
                f"scale={args.target_width}:{args.target_height}:flags=lanczos"
            ),
            "-vsync", "0", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "12", trimmed,
        ],
        check=True,
    )
    final = frame_count(trimmed)
    final_w, final_h = dimensions(trimmed)
    if final != args.target_frames:
        raise SystemExit(
            f"FAILED: trimmed guide has {final} frames, expected {args.target_frames}. "
            "H3FunControlApply requires an exact match."
        )
    if (final_w, final_h) != (args.target_width, args.target_height):
        raise SystemExit(
            f"FAILED: guide is {final_w}x{final_h}, expected "
            f"{args.target_width}x{args.target_height}. H3FunControlApply compares "
            "packed token counts, so width and height must match the shot exactly."
        )
    print(f"  trimmed to {final} frames at {final_w}x{final_h} -> {trimmed}")

    # Install where LoadVideo resolves names. The task container cannot write
    # into comfyui-local's filesystem directly, so this goes through the
    # documented upload endpoint.
    with open(trimmed, "rb") as fh:
        data = fh.read()
    boundary = "----genops010"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{args.install_name}"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{base}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        up = json.load(r)
    print(f"  installed into comfyui input/: {up}")

    report = {
        "prompt_id": pid,
        "guide_seconds_comfyui_clock": secs,
        "guide_seconds_wall": round(wall, 1),
        "frames_generated": got,
        "frames_after_trim": final,
        "installed_as": up.get("name", args.install_name),
        "bytes": os.path.getsize(trimmed),
    }
    json.dump(report, open(args.report, "w"), indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    sys.exit(main())
