#!/usr/bin/env python3
"""Build every video fixture h3-exp-023 needs, then install them in comfyui-local.

Stdlib + ffmpeg only -- house style for Concourse task scripts. GPU work happens
inside comfyui-local over HTTP, so the caller still holds gpu-lock.

WHAT THIS PRODUCES

Six clips, all 832x480 @ 24fps, two lengths each (124 = 17*7+5 for a shot-length
control video, 90 = 17*5+5 for a ref_videos entry inside its 2-15s window):

    exp023_guide_same_124.mp4   exp023_guide_same_90.mp4    <- rendered here
    exp023_guide_diff_124.mp4   exp023_guide_diff_90.mp4    <- from vace_guide_294.mp4
    exp023_pose_124.mp4    exp023_pose_90.mp4     <- from pose_briefcase_hq.mp4

THE RESAMPLE IS THE LOAD-BEARING DECISION

Every source clip is 294 frames of ONE continuous action: walk in, kneel, set
the case down, open it, extract a tripod. Head-trimming 294 -> 124 would keep
only the walk-in, and "the guide's choreography did not transfer" would then be
trivially true because the guide never showed the kneel in the first place. So
each fixture is a UNIFORM temporal resample -- frame i of the output is frame
round(i * (src-1) / (dst-1)) of the input -- which keeps the whole action and
merely plays it faster. The same resample is applied identically to all three
sources, so the Subject-Alignment x Injection-Pathway comparison stays matched;
pace is a constant, not a factor.

Frame selection happens in Python over extracted PNGs rather than through an
ffmpeg `fps=` filter, because `fps=` gives an approximate count and both H3
consumers hard-fail on an exact frame-count mismatch rather than padding.
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

SRC_FRAMES_EXPECTED = 294
TARGET_W, TARGET_H = 832, 480

# Stable name for the freshly rendered, UNTRIMMED same-subject guide. It is
# installed under this name so a retry can reuse the ~44 minutes of GPU time
# it cost instead of rendering an identical clip again. exp023_-prefixed for
# the same reason every other fixture here is: comfyui-local's input/ dir is
# shared with concurrently running experiment pipelines.
REUSE_PROBE_NAME = "exp023_guide_same_raw_294.mp4"


# --------------------------------------------------------------------------
# ComfyUI HTTP
# --------------------------------------------------------------------------
def post_prompt(base, graph):
    body = json.dumps({"prompt": graph}).encode()
    req = urllib.request.Request(
        f"{base}/prompt", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"FAILED /prompt {exc.code}: {exc.read().decode(errors='replace')[:2000]}"
        )


def wait_for(base, pid, poll=5, limit=7200):
    start = time.time()
    while time.time() - start < limit:
        try:
            with urllib.request.urlopen(f"{base}/history/{pid}", timeout=60) as r:
                hist = json.load(r)
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
    msgs = (entry.get("status") or {}).get("messages", [])
    start = end = None
    for kind, payload in msgs:
        if kind == "execution_start":
            start = payload.get("timestamp")
        if kind in ("execution_success", "execution_error"):
            end = payload.get("timestamp")
    return (end - start) / 1000.0 if (start and end) else None


def find_output(entry):
    for node_out in (entry.get("outputs") or {}).values():
        for key in ("videos", "gifs", "images"):
            for item in node_out.get(key, []) or []:
                if str(item.get("filename", "")).endswith(".mp4"):
                    return item
    return None


def fetch_view(base, filename, dest, subfolder="", kind="input", timeout=600):
    q = urllib.parse.urlencode(
        {"filename": filename, "subfolder": subfolder, "type": kind}
    )
    with urllib.request.urlopen(f"{base}/view?{q}", timeout=timeout) as r, open(
        dest, "wb"
    ) as fh:
        shutil.copyfileobj(r, fh)
    return dest


def upload_input(base, path, name):
    with open(path, "rb") as fh:
        data = fh.read()
    boundary = "----genops023"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{base}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


# --------------------------------------------------------------------------
# ffmpeg
# --------------------------------------------------------------------------
def frame_count(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    )
    return int(out.stdout.strip())


def dimensions(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True, check=True,
    )
    w, h = out.stdout.strip().split("x")
    return int(w), int(h)


def resample(src, dst, n_out, workdir):
    """Uniform temporal resample + scale to TARGET_WxTARGET_H, exactly n_out frames."""
    n_in = frame_count(src)
    if n_in < n_out:
        raise SystemExit(
            f"FAILED: {src} has {n_in} frames, fewer than the {n_out} requested; "
            "resampling cannot invent frames."
        )
    stage = os.path.join(workdir, "frames_" + os.path.basename(dst).replace(".", "_"))
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)

    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src,
         "-vf", f"scale={TARGET_W}:{TARGET_H}:flags=lanczos",
         "-vsync", "0", "-an", os.path.join(stage, "f_%05d.png")],
        check=True,
    )
    have = sorted(os.listdir(stage))
    if len(have) != n_in:
        raise SystemExit(
            f"FAILED: extracted {len(have)} PNGs from {src} but ffprobe counted {n_in}"
        )

    picked = os.path.join(stage, "picked")
    os.makedirs(picked)
    for i in range(n_out):
        j = round(i * (n_in - 1) / (n_out - 1)) if n_out > 1 else 0
        os.link(os.path.join(stage, have[j]), os.path.join(picked, f"p_%05d.png" % i))

    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-framerate", "24",
         "-i", os.path.join(picked, "p_%05d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12", "-r", "24", dst],
        check=True,
    )
    got = frame_count(dst)
    gw, gh = dimensions(dst)
    if got != n_out:
        raise SystemExit(f"FAILED: {dst} has {got} frames, expected exactly {n_out}")
    if (gw, gh) != (TARGET_W, TARGET_H):
        raise SystemExit(
            f"FAILED: {dst} is {gw}x{gh}, expected {TARGET_W}x{TARGET_H}. "
            "H3FunControlApply compares packed token counts, so the spatial "
            "dimensions must match the shot exactly."
        )
    shutil.rmtree(stage, ignore_errors=True)
    print(f"  {os.path.basename(dst)}: {n_in} -> {got} frames at {gw}x{gh}, "
          f"{os.path.getsize(dst)} bytes")
    return dst


def video_md5(path):
    """Hash the DECODED video stream, so container metadata cannot mask sameness."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-an", "-f", "md5", "-"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfyui-url", required=True)
    ap.add_argument("--guide-graph", required=True,
                    help="the SAME-SUBJECT Wan VACE guide graph to render")
    ap.add_argument("--diff-guide-input", default="vace_guide_294.mp4",
                    help="existing different-subject guide, already in comfyui input/")
    ap.add_argument("--pose-input", default="pose_briefcase_hq.mp4",
                    help="existing OpenPose skeleton track, already in comfyui input/")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--reuse-guide", action="store_true",
                    help="reuse a previously installed same-subject guide of "
                         "the right length instead of re-rendering it")
    args = ap.parse_args()

    base = args.comfyui_url.rstrip("/")
    os.makedirs(args.out_dir, exist_ok=True)
    report = {"rendered_same_subject_guide": None, "fixtures": {}, "decoded_md5": {}}

    # ---- 1. the novel fixture: same-subject guide, rendered on the GPU -----
    #
    # The guide graph reads a SHARED source clip out of comfyui-local's input/
    # dir. That directory is not this pipeline's private property: other
    # experiment pipelines write to it, and comfyui-local gets recreated from
    # time to time, which empties it. A 42-minute guide render that dies at
    # minute 40 because someone else's build removed the source is a wasted
    # GPU-lock hold, so the source is pinned FIRST: fetch it, re-upload it
    # under an exp023-private name, and point the graph at that copy. The
    # window in which a foreign change can break this run shrinks from the
    # length of the render to the length of one HTTP round trip.
    graph = json.load(open(args.guide_graph))
    loaders = [n for n in graph.values() if n.get("class_type") == "LoadVideo"]
    if len(loaders) != 1:
        raise SystemExit(
            f"FAILED: guide graph has {len(loaders)} LoadVideo nodes, expected 1"
        )
    shared_src = loaders[0]["inputs"]["file"]
    private_src = "exp023_src_props.mp4"
    src_local = fetch_view(base, shared_src,
                           os.path.join(args.out_dir, "exp023_src_props.mp4"))
    n_src = frame_count(src_local)
    print(f"pinned guide source {shared_src}: {n_src} frames at "
          f"{dimensions(src_local)} -> re-uploading as {private_src}")
    if n_src != SRC_FRAMES_EXPECTED:
        raise SystemExit(
            f"FAILED: guide source has {n_src} frames, expected "
            f"{SRC_FRAMES_EXPECTED}."
        )
    upload_input(base, src_local, private_src)
    loaders[0]["inputs"]["file"] = private_src
    report["guide_source"] = {"shared": shared_src, "pinned_as": private_src,
                              "frames": n_src}

    same_raw = os.path.join(args.out_dir, "vace_guide_same_raw.mp4")

    # The guide is an INSTRUMENT, not a result, and it costs ~44 minutes of
    # gpu-lock. A retry caused by something downstream -- a flaky poller, a
    # failed arm -- must not pay for it twice. If a previously installed
    # same-subject guide of the right length is still in comfyui-local's
    # input/ dir, reuse it; the derived fixtures below are rebuilt from it
    # either way, so reuse changes nothing about what the arms consume.
    reused = False
    if args.reuse_guide:
        try:
            fetch_view(base, REUSE_PROBE_NAME, same_raw)
            n_have = frame_count(same_raw)
            if n_have == SRC_FRAMES_EXPECTED:
                print(f"reusing installed same-subject guide {REUSE_PROBE_NAME}: "
                      f"{n_have} frames -- skipping the render")
                reused = True
            else:
                print(f"installed guide is {n_have}f, need {SRC_FRAMES_EXPECTED}f; "
                      "re-rendering")
        except Exception as exc:
            print(f"no reusable same-subject guide ({exc}); rendering one")

    if not reused:
        print(f"submitting same-subject guide graph to {base}")
        t0 = time.time()
        resp = post_prompt(base, graph)
        pid = resp.get("prompt_id")
        if not pid:
            raise SystemExit(f"FAILED: no prompt_id in response: {resp}")
        print(f"  prompt_id {pid}")
        entry = wait_for(base, pid)
        secs = exec_seconds(entry)
        print(f"  done: {secs}s by ComfyUI's clock, {time.time() - t0:.1f}s wall")
        item = find_output(entry)
        if not item:
            raise SystemExit("FAILED: no .mp4 in the same-subject guide's outputs")
        fetch_view(base, item["filename"], same_raw,
                   subfolder=item.get("subfolder", ""),
                   kind=item.get("type", "output"))
        print(f"  fetched {same_raw} ({os.path.getsize(same_raw)} bytes, "
              f"{frame_count(same_raw)} frames)")
        # Install the RAW guide under a stable name so a later retry can reuse
        # it. This is the probe --reuse-guide looks for.
        upload_input(base, same_raw, REUSE_PROBE_NAME)
    else:
        pid, secs = None, None

    n_same = frame_count(same_raw)
    if n_same != SRC_FRAMES_EXPECTED:
        raise SystemExit(
            f"FAILED: same-subject guide has {n_same} frames, expected "
            f"{SRC_FRAMES_EXPECTED}."
        )
    report["rendered_same_subject_guide"] = {
        "prompt_id": pid,
        "reused": reused,
        "seconds_comfyui_clock": secs,
        "frames": n_same,
        "bytes": os.path.getsize(same_raw),
    }

    # ---- 2. the two pre-existing sources -----------------------------------
    diff_raw = fetch_view(base, args.diff_guide_input,
                          os.path.join(args.out_dir, "vace_guide_diff_raw.mp4"))
    pose_raw = fetch_view(base, args.pose_input,
                          os.path.join(args.out_dir, "pose_briefcase_raw.mp4"))
    for label, p in (("diff-guide", diff_raw), ("pose", pose_raw)):
        n = frame_count(p)
        print(f"  {label}: {n} frames at {dimensions(p)}")
        if n != SRC_FRAMES_EXPECTED:
            raise SystemExit(
                f"FAILED: {label} source has {n} frames, expected "
                f"{SRC_FRAMES_EXPECTED}. All three sources must carry the SAME "
                "choreography over the same span or the arms are not matched."
            )

    # ---- 3. derive every fixture, identically ------------------------------
    print("\nderiving fixtures (uniform temporal resample + scale):")
    sources = {"same": same_raw, "diff": diff_raw, "pose": pose_raw}
    names = {
        ("same", 124): "exp023_guide_same_124.mp4",
        ("same", 90): "exp023_guide_same_90.mp4",
        ("diff", 124): "exp023_guide_diff_124.mp4",
        ("diff", 90): "exp023_guide_diff_90.mp4",
        ("pose", 124): "exp023_pose_124.mp4",
        ("pose", 90): "exp023_pose_90.mp4",
    }
    for (kind, n), name in sorted(names.items()):
        dst = os.path.join(args.out_dir, name)
        resample(sources[kind], dst, n, args.out_dir)
        report["fixtures"][name] = {
            "frames": frame_count(dst),
            "width": TARGET_W,
            "height": TARGET_H,
            "bytes": os.path.getsize(dst),
            "source": os.path.basename(sources[kind]),
        }

    # ---- 4. the guard that decides whether the experiment means anything ---
    # If the same-subject and different-subject guides decode identically, then
    # Factor 1 does not vary and every comparison below it is void. Check the
    # DECODED stream, not the file bytes: two different encodes of the same
    # pixels would pass a file hash.
    print("\ndecoded-stream hashes:")
    for name in sorted(names.values()):
        h = video_md5(os.path.join(args.out_dir, name))
        report["decoded_md5"][name] = h
        print(f"  {name:28} {h}")
    for n in (124, 90):
        a = report["decoded_md5"][names[("same", n)]]
        b = report["decoded_md5"][names[("diff", n)]]
        if a == b:
            raise SystemExit(
                f"FAILED: the same-subject and different-subject {n}-frame guides "
                "decode identically. Factor 1 (Subject Alignment) does not vary, "
                "so the experiment cannot answer its question."
            )
    print("  OK: same-subject and different-subject guides are distinct at both lengths")

    # ---- 5. install where LoadVideo resolves names ------------------------
    print("\ninstalling into comfyui-local input/:")
    for name in sorted(names.values()):
        up = upload_input(base, os.path.join(args.out_dir, name), name)
        print(f"  {name} -> {up}")

    # Read each one back and re-verify: an upload that silently landed under a
    # different name would fail the ARMS task after it has taken the lock.
    print("\nverifying installed fixtures by reading them back:")
    for name in sorted(names.values()):
        probe = os.path.join(args.out_dir, "verify_" + name)
        fetch_view(base, name, probe)
        n_back, dims_back = frame_count(probe), dimensions(probe)
        expect = report["fixtures"][name]["frames"]
        if n_back != expect or dims_back != (TARGET_W, TARGET_H):
            raise SystemExit(
                f"FAILED: installed {name} reads back as {n_back}f {dims_back}, "
                f"expected {expect}f ({TARGET_W}, {TARGET_H})"
            )
        os.remove(probe)
        print(f"  {name:28} {n_back}f {dims_back[0]}x{dims_back[1]} OK")

    json.dump(report, open(args.report, "w"), indent=2)
    print(f"\nOK: 6 fixtures built, distinct, and installed. Report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
