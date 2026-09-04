# The H3-World reproduction that never reached the GPU

Not every item in the experiment register has a branch. This one doesn't, and that's the point of the write-up: the block happened before a single line of workflow JSON got written against `comfyui-local`.

**No media for this one, and that's the correct outcome, not an oversight.** A search across this lab's `blades68-lora` worktrees, git history, and running/exited Docker containers turns up nothing matching "h3-world" or "h3world" anywhere: no checkpoint, no workflow JSON, no render, no screenshot. That's consistent with the write-up below: the license block was hit before any GPU work began.

## What H3-World claims

[H3-World](https://github.com/Danzer1xxxxChan/H3-World) is a third-party project (Tencent, National University of Singapore, Hong Kong Polytechnic University) that adds keyboard-driven control on top of the base [MiniMax H3](https://huggingface.co/MiniMaxAI) video model already in production here. The pitch: feed it one still frame and a scene prompt, then drive character motion with WASD and camera motion with IJKL, and it generates video where the subject walks and the camera moves according to input. Mechanically it's a rank-32 LoRA, 65.6M parameters (0.199% of the 33B H3 backbone), trained on 8,000 gameplay clips from the [`ABot-World-Explorer-500h`](https://github.com/amap-cvlab/ABot-World) dataset, released alongside a paper ([arXiv 2609.01560](https://arxiv.org/abs/2609.01560)) and a patched fork of [DiffSynth-Studio](https://github.com/modelscope/DiffSynth-Studio).

Reproducing it here would have meant: same base model this rig already renders on, a small LoRA download, one attention patch applied to a pinned DiffSynth revision. On paper, a cheap experiment.

## Blocker one: the license, checked twice

MiniMax H3's own weights ship under the [MiniMax H3 Community License Agreement](https://huggingface.co/MiniMaxAI/MiniMax-H3/raw/main/LICENSE). Section V.4 is unambiguous:

> "You may not use, reproduce, modify, distribute, or display the MiniMax H3 Works or any of their Outputs or results outside the Applicable Territory."

"Applicable Territory" is defined as worldwide *excluding* the Excluded Territories, and Section I.5 names those Excluded Territories explicitly: "the European Union, the United Kingdom, the Republic of Korea and the United States of America." This rig is in the United States.

The obvious next question is whether personal, non-commercial use gets a carve-out the way some open-weight licenses distinguish research/personal use from commercial deployment. It doesn't. Section II grants rights "solely within the Applicable Territory" with no exception based on use type, and nothing later in the document reintroduces one. This was checked twice specifically to rule that possibility out, once on a first read and once on a targeted re-read of the full license text looking only for a personal-use clause. There isn't one. The exclusion is territorial and absolute, not use-conditional.

That alone is a clean, hard stop, independent of anything about the H3-World fork itself.

## Blocker two: it isn't what it looks like

Separately from the license, reading H3-World's own repository turns up a second finding worth recording, because it would have mattered even in a jurisdiction where the license allowed a test. The README's actual inference invocation is:

```
python3 code/abot/infer.py \
  --checkpoint checkpoints/H3-World/step-10000.safetensors \
  --first-frame examples/first_frame.png \
  --scene-prompt "A man in a yellow floral shirt stands in a dim, multi-level concrete parking garage." \
  --action-preset forward \
  --seed 2 \
  --steps 50 \
  --num-frames 124 \
  --cfg-scale 1.0 \
  --out outputs/example_forward.mp4
```

`--action-preset` is chosen once, up front, from a fixed list: `still, forward, back, strafe-left, strafe-right, tilt-up, tilt-down, pan-left, pan-right, pan-left-fast, pan-right-fast`. That single choice drives the entire 124-frame, 5.2-second render. There's no live per-frame keystroke stream in the base repository; it's a preset selected before generation starts, the same shape as any other one-shot prompt or parameter choice already used in this lab's production pipeline. The "keyboard-controlled" framing describes the training data and the model's internal mechanism (keyboard states converted to per-latent language instructions via directed attention routing) rather than the actual inference-time interface most people would picture. A genuinely interactive, live-driven version exists only as a separate hosted demo Space built on top of this code, not as something this rig's local pipeline could reproduce by cloning the repo.

## Where it landed

Blocked twice, independently: legally by an unconditional US exclusion in the base model's own license, and separately, on the merits, by the gap between "keyboard-controlled world model" as marketed and "pick one motion preset per render" as actually shipped. No checkpoint was downloaded, no workflow was written, no worktree was created. The register lists this one with no branch because there was nothing left to build once the first check came back negative.
