# H3 Fun ControlNet — pose transfer workflow

Files behind [Pose transfer works: the woman in the dress follows the briefcase
poses](../../2026-09-15-h3-funcontrol-pose-transfer.html).

| file | what it is |
| :-- | :-- |
| `h3-pose-control.api.json` | the pose-conditioned graph (20 nodes) |
| `h3-no-control.api.json` | identical minus the ControlNet — the baseline arm (16 nodes) |
| `make_pose_control.py` | builds a skeleton control video from ordinary footage |

## Read this before you load them

These are **API-format** graphs, not UI workflows. ComfyUI's drag-and-drop
expects the UI format; load these with *Workflow → Open* (which accepts API
JSON) or POST them to `/prompt` directly. They are what our pipeline submits,
so they are exactly what produced the clips in the write-up — but they will not
render as a laid-out node graph.

**They will not run unmodified on your machine.** They name our specific
checkpoints, several of which are quantized builds rather than stock releases:

- `minimax_h3_ref2va_pruned_int8_convrot.safetensors` (UNET)
- `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` (CLIP)
- `minimax_h3_video_vae_fp16` / `minimax_h3_audio_vae_fp32` (VAEs)
- `minimax_h3_turbo_v4_step600_ema.safetensors` (Turbo LoRA)
- `minimax_h3_fun_controlnet_union_pruned_bf16.safetensors` (ControlNet)

Swap those filenames for whatever your install has. The ControlNet is the one
that is **not** interchangeable: the loader takes only Kijai's curve-form
pruned variant. Check the safetensors header — `adaln_proj.linear` of
`[96768, 8]` with `adaln_basis` metadata is the right one; `[96768, 2688]` is
Alibaba's full-width release and gets refused.

Requires [wyzborrero/ComfyUI-H3-FunControl](https://github.com/wyzborrero/ComfyUI-H3-FunControl)
for the `H3FunControlLoader` and `H3FunControlApply` nodes.

## The control video

`H3FunControlApply` takes an IMAGE batch. `LoadVideo` alone returns VIDEO, so
the graph goes `LoadVideo → GetVideoComponents → control_video`.

The control **must match the generation's width, height and frame count
exactly** — the node raises when the control token count diverges from the
video segment, and reports both numbers.

If you already run DWPose or another preprocessor, use it. `make_pose_control.py`
exists because our ComfyUI had no pose preprocessor installed; it draws an
OpenPose-style coloured skeleton with MediaPipe, offline:

```bash
pip install mediapipe opencv-python
curl -sLO https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task
mkdir -p models && mv pose_landmarker_heavy.task models/

python make_pose_control.py source.mp4 pose_control.mp4 \
  --width 1312 --height 736 --frames 294 --thickness 8 --autocrop
```

Then drop `pose_control.mp4` in `ComfyUI/input/`.

`--autocrop` crops the source to the figure before extracting. That matters
more than it sounds: raising resolution alone does **not** raise how much of
the frame the subject occupies, and subject size — not strength — is what
governs how much authority the control has. At 0.4 MP and 0.98 MP our skeleton
occupied the same ~7% of frame and the prompt won outright; cropping took it to
10.6% and the pose took over.

## Settings that produced the published clips

1312×736, 294 frames (12.25 s at 24 fps), 8 steps, `simple` scheduler,
`strength` 0.8, control window `0.0–0.6`. About 18 minutes per clip and 20 GiB
of VRAM on a 3090.

The prompt deliberately describes only *who and where* — it never mentions
kneeling, a briefcase or a tripod. That is the point of the test: any action in
the output has to come from the control. If you write the action into the
prompt as well, you can no longer tell which signal produced it.
