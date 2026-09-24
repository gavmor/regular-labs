#!/usr/bin/env python3
"""Build the four reference-video fixtures h3-exp-020 needs, on comfyui-local.

h3-exp-020 is a 2x2 over (subject identity) x (reference render engine). The
whole experiment is only as good as its fixtures, so this script produces all
four to the SAME geometry -- 90 frames, 832x480, 24 fps (90 = 17*5+5, inside
the reference window) -- and installs them into comfyui-local's input/ dir,
where the arms' LoadVideo nodes resolve names.

    Arm A  same-subject  / H3   char_ref_90.mp4           already installed
    Arm B  diff-subject  / H3   h3_diff_subject_90.mp4    derived, no GPU
    Arm C  same-subject  / Wan  wan_same_subject_90.mp4   RENDERED here (GPU)
    Arm D  diff-subject  / Wan  vace_guide_90.mp4         derived, no GPU

Three of the four are derivations of artifacts this lab already rendered, which
is the point: re-rendering them would change the fixtures out from under the
exp-012 / exp-014 benchmarks this experiment is supposed to be commensurable
with.

  B comes from H3/exp013/ghost_echo_skeleton -- a native H3 render of a
    character who is NOT the prompt's woman, performing the same briefcase
    action the Wan guide performs. That action match is deliberate: it makes B
    the engine-swapped twin of D rather than a differently-moving clip, so the
    B-vs-D contrast isolates engine and not choreography.
  D comes from the existing vace_guide_294.mp4, the exact Wan2.1 VACE render
    exp-012 used, trimmed to the first 90 frames.

Only C has to be rendered, because no Wan render of the prompt's woman exists.
It uses the same Wan2.1 VACE graph that produced D's source, with D's own
control video, and only the text prompt swapped to exp-014's -- so C differs
from D in subject and nothing else.

Aspect note, stated rather than hidden: B, C and D are 1312x736 (1.783) scaled
to 832x480 (1.733), a ~3% horizontal squash. A is native 832x480 and is NOT
re-derived, because altering it would break comparability with exp-014's
published numbers. The squash is uniform across the three novel fixtures.
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

REF_FRAMES = 90          # 17*5 + 5
REF_W, REF_H = 832, 480
WAN_LENGTH = 93          # 4*23 + 1, the nearest Wan-legal length >= 90

# exp-014's prompt, the one every arm of exp-020 renders. Copied here so the
# Wan same-subject fixture describes the same character the H3 arms ask for;
# build_exp020.py asserts the arms' prompt matches this byte-for-byte.
EXP014_PROMPT = (
    "Live-action, photorealistic cinematic film footage, not animation, not "
    "CGI-stylized. FULL BODY SHOT: the entire figure is visible head to feet "
    "in every single frame, never cropped. Camera at standing eye level, far "
    "back from the subject, locked off and completely static, no camera "
    "movement, no zoom, no pan, no tilt. Wide framing with empty space above "
    "the head and the floor visible across the bottom of the frame. The whole "
    "body stays inside the frame at all times. A young woman with a blonde "
    "bob, wearing a sleeveless late-1960s colour-blocked A-line mini dress in "
    "red, white and blue, and low white heels. Plain concrete floor, neutral "
    "grey wall, soft even lighting. Shot on 35mm film, period-accurate 1968."
)


# --------------------------------------------------------------------------
# comfyui-local HTTP helpers (stdlib only -- house style for task scripts)
# --------------------------------------------------------------------------
def view(base, filename, subfolder, typ, dest):
    q = urllib.parse.urlencode(
        {"filename": filename, "subfolder": subfolder, "type": typ}
    )
    with urllib.request.urlopen(f"{base}/view?{q}", timeout=600) as r, open(
        dest, "wb"
    ) as fh:
        shutil.copyfileobj(r, fh)
    return os.path.getsize(dest)


def upload(base, path, name):
    with open(path, "rb") as fh:
        data = fh.read()
    boundary = "----genops020"
    # `overwrite` is a multipart FORM FIELD, not a header (ComfyUI reads it via
    # post.get("overwrite") in server.py's image_upload). It matters: the
    # fixture name is this experiment's contract with the arms, and without it
    # ComfyUI dedupe-renames a same-named upload to "foo (1).mp4" and leaves
    # the arms silently loading the STALE file still sitting at `name`.
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
        "true\r\n"
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


def queued(base, pid):
    """True if `pid` is still in ComfyUI's running or pending queue."""
    with urllib.request.urlopen(f"{base}/queue", timeout=30) as r:
        q = json.load(r)
    for key in ("queue_running", "queue_pending"):
        for item in q.get(key, []) or []:
            # queue entries are positional arrays; the prompt_id is element 1
            if len(item) > 1 and item[1] == pid:
                return True
    return False


def wait_for(base, pid, poll=5, limit=7200):
    start = time.time()
    # ComfyUI's queue is IN-MEMORY: a container restart silently forgets every
    # submitted prompt. Build #18 lost its fixture render that way and would
    # have polled a nonexistent prompt for the full 2h limit. Once the server
    # is reachable again, a pid that is in neither history nor the queue is
    # gone for good, so fail in seconds instead of burning the GPU lock.
    vanished = 0
    while time.time() - start < limit:
        try:
            with urllib.request.urlopen(f"{base}/history/{pid}", timeout=60) as r:
                hist = json.load(r)
        except urllib.error.URLError as exc:
            print(f"  (history fetch failed, retrying: {exc})")
            time.sleep(poll)
            continue
        entry = hist.get(pid)
        if entry:
            status = (entry.get("status") or {}).get("status_str")
            if status == "error":
                msgs = []
                for kind, payload in (entry.get("status") or {}).get("messages", []):
                    if kind == "execution_error":
                        msgs.append(
                            f"{payload.get('node_type')}: "
                            f"{payload.get('exception_message')}"
                        )
                raise SystemExit("FAILED: Wan fixture render errored -- " + "; ".join(msgs))
            if (entry.get("status") or {}).get("completed"):
                return entry
        else:
            try:
                still_queued = queued(base, pid)
            except Exception:                                   # noqa: BLE001
                still_queued = True     # can't tell -> keep waiting
            vanished = 0 if still_queued else vanished + 1
            # Three consecutive misses, to ride out the brief window between
            # leaving the queue and landing in history.
            if vanished >= 3:
                raise SystemExit(
                    f"FAILED: prompt {pid} is in neither the queue nor history. "
                    "comfyui-local almost certainly restarted and dropped it "
                    "(its queue is in-memory). Re-run the job."
                )
        time.sleep(poll)
    raise SystemExit(f"FAILED: Wan fixture render did not finish within {limit}s")


def find_mp4(entry):
    for node_out in (entry.get("outputs") or {}).values():
        for key in ("videos", "gifs", "images"):
            for item in node_out.get(key, []) or []:
                if str(item.get("filename", "")).endswith(".mp4"):
                    return item
    return None


# --------------------------------------------------------------------------
# ffmpeg helpers
# --------------------------------------------------------------------------
def frames(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    )
    return int(out.stdout.strip())


def dims(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True, check=True,
    )
    w, h = out.stdout.strip().split("x")
    return int(w), int(h)


def trim_scale(src, dst, n_frames, w, h):
    """Cut to the first n_frames and scale to w x h, dropping audio.

    -an is not cosmetic: trimming video while leaving the original audio
    stream in place yields a container that outruns its video, so the clip
    freezes on its last frame during playback. The reference node reads decoded
    frames and never consults container duration, so this would not reach the
    render -- it would just make every fixture unreviewable by a human.
    """
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src,
         "-vf", f"select='lt(n,{n_frames})',scale={w}:{h}:flags=lanczos",
         "-vsync", "0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "12", dst],
        check=True,
    )
    got = frames(dst)
    gw, gh = dims(dst)
    if (got, gw, gh) != (n_frames, w, h):
        raise SystemExit(
            f"FAILED: {dst} is {got}f {gw}x{gh}, expected {n_frames}f {w}x{h}"
        )
    vdur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=duration", "-of", "default=nw=1:nk=1", dst],
        capture_output=True, text=True, check=True).stdout.strip())
    cdur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", dst],
        capture_output=True, text=True, check=True).stdout.strip())
    if abs(vdur - cdur) > 0.05:
        raise SystemExit(
            f"FAILED: {dst} container runs {cdur:.2f}s against {vdur:.2f}s of "
            "video -- playback would freeze on the last frame"
        )
    return got, gw, gh, os.path.getsize(dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfyui-url", required=True)
    ap.add_argument("--wan-graph", required=True,
                    help="Wan2.1 VACE graph used as the template for fixture C")
    ap.add_argument("--work-dir", default="fixtures-out")
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    base = args.comfyui_url.rstrip("/")
    wd = args.work_dir
    os.makedirs(wd, exist_ok=True)
    report = {"fixtures": {}}

    # ---- Arm A: rebuilt from the DURABLE exp-010 render --------------------
    # Originally this reused the installed input/char_ref_90.mp4 as-is. That
    # was wrong on this deployment: comfyui-local's input/ is SHARED MUTABLE
    # STATE across every experiment on the box, and build #17 died here with a
    # 404 because a sibling pipeline emptied input/ mid-queue while this job
    # waited ~19 minutes on gpu-lock. Renders under output/ are durable and
    # never swept, so every fixture is now derived from an output/ render.
    #
    # This is the same clip exp-014 used (exp-010 seed-43, second render),
    # trimmed and scaled identically -- so Arm A remains exp-014's fixture by
    # construction rather than by trusting a file to still be sitting there.
    a_src = os.path.join(wd, "exp010_s43_src.mp4")
    view(base, "skeleton_s43_00002_.mp4", "H3/exp010", "output", a_src)
    a_path = os.path.join(wd, "char_ref_90.mp4")
    an, aw, ah, size = trim_scale(a_src, a_path, REF_FRAMES, REF_W, REF_H)
    print(f"A char_ref_90.mp4          derived:      {an}f {aw}x{ah} {size}B")
    report["fixtures"]["char_ref_90.mp4"] = {
        "arm": "A", "subject": "same", "engine": "MiniMax-H3",
        "source": "output/H3/exp010/skeleton_s43_00002_.mp4, first 90f "
                  "(the clip exp-014 used as char_ref_90.mp4)",
        "frames": an, "width": aw, "height": ah, "bytes": size, "rendered": False,
    }

    # ---- Arm D: trim the exp-010 Wan VACE guide ---------------------------
    # Also from output/, for the same reason. This is the guide render itself,
    # i.e. the Wan-rendered DIFFERENT subject (the briefcase/tripod actor).
    d_src = os.path.join(wd, "vace_guide_src.mp4")
    view(base, "vace_guide_00002_.mp4", "H3/exp010", "output", d_src)
    d_path = os.path.join(wd, "vace_guide_90.mp4")
    dn, dw, dh, db = trim_scale(d_src, d_path, REF_FRAMES, REF_W, REF_H)
    print(f"D vace_guide_90.mp4        derived:      {dn}f {dw}x{dh} {db}B")
    report["fixtures"]["vace_guide_90.mp4"] = {
        "arm": "D", "subject": "different", "engine": "Wan2.1-VACE",
        "source": "output/H3/exp010/vace_guide_00002_.mp4, first 90f",
        "frames": dn, "width": dw, "height": dh, "bytes": db, "rendered": False,
    }

    # ---- Arm B: trim a native H3 render of a different character ----------
    b_src = os.path.join(wd, "ghost_echo_src.mp4")
    view(base, "ghost_echo_skeleton_00001_.mp4", "H3/exp013", "output", b_src)
    b_path = os.path.join(wd, "h3_diff_subject_90.mp4")
    bn, bw, bh, bb = trim_scale(b_src, b_path, REF_FRAMES, REF_W, REF_H)
    print(f"B h3_diff_subject_90.mp4   derived:      {bn}f {bw}x{bh} {bb}B")
    report["fixtures"]["h3_diff_subject_90.mp4"] = {
        "arm": "B", "subject": "different", "engine": "MiniMax-H3",
        "source": "output/H3/exp013/ghost_echo_skeleton_00001_.mp4, first 90f",
        "frames": bn, "width": bw, "height": bh, "bytes": bb, "rendered": False,
    }

    # ---- Arm C: the one fixture that must be rendered ---------------------
    # Control video trimmed to Wan's 4n+1 length first. Feeding the untrimmed
    # source to a length-93 WanVaceToVideo is a token-count mismatch at the
    # sampler, i.e. a failure AFTER the GPU lock is held.
    #
    # Source is output/, not input/vace_src_props.mp4, for the shared-mutable-
    # state reason above. The exp-010 guide render carries the same
    # briefcase/tripod action and is durable.
    #
    # Reuse: this render costs ~15 minutes of the GPU lock and is an
    # INSTRUMENT, not a result. Its output lands in output/H3/exp020/, which
    # survives container recreates, so a retry after a downstream failure
    # (build #19 died in preflight with all four fixtures already built) must
    # not pay for it twice.
    c_path = os.path.join(wd, "wan_same_subject_90.mp4")
    c_raw = os.path.join(wd, "wan_same_subject_raw.mp4")
    pid = None
    cn = cw = ch = cb = 0
    try:
        view(base, "wan_same_subject_00001_.mp4", "H3/exp020", "output", c_raw)
        cn, cw, ch, cb = trim_scale(c_raw, c_path, REF_FRAMES, REF_W, REF_H)
        print(f"C wan_same_subject_90.mp4  reused:       {cn}f {cw}x{ch} {cb}B")
        rendered = False
    except Exception as exc:                                    # noqa: BLE001
        print(f"no reusable Wan fixture ({exc}); rendering one")
        rendered = True

    if rendered:
        ctl_src = os.path.join(wd, "wan_control_src.mp4")
        view(base, "vace_guide_00002_.mp4", "H3/exp010", "output", ctl_src)
        ctl = os.path.join(wd, "exp020_wan_control_93.mp4")
        trim_scale(ctl_src, ctl, WAN_LENGTH, REF_W, REF_H)
        up = upload(base, ctl, "exp020_wan_control_93.mp4")
        print(f"  control for C installed: {up}")

        graph = json.load(open(args.wan_graph))
        positive = [k for k, v in graph.items()
                    if v.get("class_type") == "CLIPTextEncode"
                    and "blurry" not in v["inputs"]["text"]]
        if len(positive) != 1:
            raise SystemExit(
                f"FAILED: expected exactly one positive CLIPTextEncode in "
                f"{args.wan_graph}, found {positive}"
            )
        vace = [k for k, v in graph.items() if v.get("class_type") == "WanVaceToVideo"]
        loadv = [k for k, v in graph.items() if v.get("class_type") == "LoadVideo"]
        scale = [k for k, v in graph.items() if v.get("class_type") == "ImageScale"]
        save = [k for k, v in graph.items() if v.get("class_type") == "SaveVideo"]
        for label, got in (("WanVaceToVideo", vace), ("LoadVideo", loadv),
                           ("ImageScale", scale), ("SaveVideo", save)):
            if len(got) != 1:
                raise SystemExit(f"FAILED: expected one {label} node, found {got}")

        # The ONLY differences from the graph that produced D's source: the
        # prompt (different subject -> same subject), geometry, output name.
        graph[positive[0]]["inputs"]["text"] = EXP014_PROMPT
        graph[loadv[0]]["inputs"]["file"] = "exp020_wan_control_93.mp4"
        graph[scale[0]]["inputs"]["width"] = REF_W
        graph[scale[0]]["inputs"]["height"] = REF_H
        graph[vace[0]]["inputs"]["width"] = REF_W
        graph[vace[0]]["inputs"]["height"] = REF_H
        graph[vace[0]]["inputs"]["length"] = WAN_LENGTH
        graph[save[0]]["inputs"]["filename_prefix"] = "H3/exp020/wan_same_subject"

        print(f"submitting Wan same-subject fixture ({len(graph)} nodes) to {base}")
        t0 = time.time()
        pid = post_prompt(base, graph).get("prompt_id")
        if not pid:
            raise SystemExit("FAILED: no prompt_id for the Wan fixture render")
        print(f"  prompt_id {pid}")
        entry = wait_for(base, pid)
        print(f"  done in {time.time() - t0:.1f}s wall")

        item = find_mp4(entry)
        if not item:
            raise SystemExit("FAILED: no .mp4 among the Wan fixture's outputs")
        view(base, item["filename"], item.get("subfolder", ""),
             item.get("type", "output"), c_raw)
        cn, cw, ch, cb = trim_scale(c_raw, c_path, REF_FRAMES, REF_W, REF_H)
        print(f"C wan_same_subject_90.mp4  rendered:     {cn}f {cw}x{ch} {cb}B")
    report["fixtures"]["wan_same_subject_90.mp4"] = {
        "arm": "C", "subject": "same", "engine": "Wan2.1-VACE",
        "source": (f"rendered here, prompt_id {pid}, control "
                   "exp020_wan_control_93.mp4") if rendered else
                  "reused output/H3/exp020/wan_same_subject_00001_.mp4",
        "frames": cn, "width": cw, "height": ch, "bytes": cb,
        "rendered": rendered,
        "prompt_id": pid,
    }

    # ---- install all four fixtures ---------------------------------------
    # char_ref_90.mp4 is in this list because comfyui-local's input/ lives in
    # the container's WRITABLE LAYER, not a volume -- a recreate wipes it. An
    # earlier version omitted A here, assuming it was already installed;
    # build #19 then rendered all four fixtures and still failed preflight
    # with "char_ref_90.mp4 is not an allowed value". Nothing is assumed
    # resident: every fixture this experiment names is uploaded here.
    for name in ("char_ref_90.mp4", "h3_diff_subject_90.mp4", "vace_guide_90.mp4",
                 "wan_same_subject_90.mp4"):
        up = upload(base, os.path.join(wd, name), name)
        installed = up.get("name")
        if installed != name:
            raise SystemExit(
                f"FAILED: comfyui installed the fixture as {installed!r}, not "
                f"{name!r}. The arms load fixtures BY NAME, so a renamed "
                "upload means they would read a stale file."
            )
        report["fixtures"][name]["installed_as"] = installed
        print(f"  installed {installed}")

    # ---- the fixtures must be genuinely different from one another --------
    import hashlib
    seen = {}
    for name in ("char_ref_90.mp4", "h3_diff_subject_90.mp4",
                 "vace_guide_90.mp4", "wan_same_subject_90.mp4"):
        h = hashlib.sha256(open(os.path.join(wd, name), "rb").read()).hexdigest()
        if h[:16] in seen:
            raise SystemExit(
                f"FAILED: {name} is byte-identical to {seen[h[:16]]}. Two cells "
                "of the 2x2 would carry the same reference and the factorial "
                "would be void."
            )
        seen[h[:16]] = name
        report["fixtures"][name]["sha256"] = h
        print(f"  {name:26} sha256 {h[:16]}")

    json.dump(report, open(args.report, "w"), indent=2)
    print("\nOK: four distinct fixtures at "
          f"{REF_FRAMES}f {REF_W}x{REF_H}, all installed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
