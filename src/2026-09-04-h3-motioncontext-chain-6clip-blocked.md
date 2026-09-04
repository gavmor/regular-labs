# Blocked before the six-clip chain could even run

Not every branch on this register gets to test its own hypothesis. This one (`feature/h3-motioncontext-chain-6clip`) didn't, and the reason why turned out to matter more than the question it was asking.

**No render output for this experiment is retrievable.** The workflow's only `SaveVideo` node writes to the final stitched-chain output (`h3_chain/final/H3_motioncontext_chain_6clip`), which was never reached since the chain failed on the second clip; the per-clip preview nodes that would have saved the one clip that did render (`VHS_VideoCombine`) had already been pruned out of the graph for the reason described below, before this build ever ran. A search of both the branch's worktree and `comfyui-local`'s shared output directory (container path `/opt/ComfyUI/output`) for any file matching this branch, this workflow's prefix, or the reference images it uses (`graves_face_ref.png`/`graves_body_ref.png`) turned up nothing. The opening clip's numbers below (duration, VRAM, RAM) come from Concourse build telemetry, not from a file anyone can watch.

## The hypothesis

An earlier pipeline had already proven a 3-clip chain: a static reference-image opening clip, then two more clips carrying raw latent and frame context forward via a motion-context node, no decode/re-encode round trip in between. That result (13.7 seconds combined, one consistent character across a 3-beat scene) is already written up separately. Separately, three attempts at a single-shot monolithic 30-second render had all failed, two to a host-RAM OOM during decode, one to an unrelated monkeypatch collision. Gavin's direction: chase 30 seconds by extending the already-proven chain to 6 clips instead, specifically because it doesn't touch that OOM failure mode at all.

The hypothesis had two parts: that the safe VRAM/host-RAM envelope which held for 3 clips would still hold for 6, since each clip is still a discrete, independent submission rather than added concurrent pressure; and that character and scene consistency might degrade over more cuts, since each handoff conditions only on a fixed-length tail of the previous clip, not full history.

## What happened

Getting the workflow to even submit took two fixes, both for environment drift since the original chain was built, not anything about this branch's own design. First submission failed prompt validation on a missing node (`VHS_VideoCombine`, used only for optional per-clip previews, part of [ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite)); the custom-node package providing it isn't installed on this instance anymore, so the generated graph was pruned down to just the ancestors of the final save node instead of installing something new to chase a preview. Second submission failed on `Invalid image file` for the reference images; the files on disk had different names than the base workflow expected, another instance of drift, fixed by correcting the two load-image nodes.

With both fixed, the workflow validated and began executing for real. The opening clip, a plain reference-to-video segment with no motion-context handoff, rendered successfully: about 5.2 seconds, peak VRAM around 22.4GB, peak host RAM around 46.5GB, both in line with the documented safe envelope. The second clip, the first one requiring the motion-context node to carry latent and frame context forward, failed immediately with:

```
h3_motion_context: another pack has already patched H3's layout
(PackedLayout.__init__ now comes from
'/opt/ComfyUI/custom_nodes/ComfyUI-SolAttn_triton._morton_h3'). Several
ComfyUI packs lift the same first/last keyframe restriction independently
and they cannot both own it, so this one is refusing rather than wrapping a
wrapper and producing joins neither pack intended. Disable one of them and
restart.
RuntimeError: h3_motion_context: the layout patch could not be applied, so
interior anchors would be rejected by ComfyUI.
```

Confirmed via install timestamps: the motion-context node package this whole chain depends on ([ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)) was installed weeks earlier; a separate attention-stack package ([ComfyUI-SolAttn_triton](https://github.com/kijai/ComfyUI-SolAttn_triton)), installed later for the unrelated monolithic 30-second attempts, patches the exact same interior layout restriction. Whichever package loads second refuses to double-patch rather than silently produce joins neither one intended, and the motion-context package is the one refusing here.

This is not a 3-clip-versus-6-clip finding. The failure happens at the very first continuation clip, structurally identical regardless of whether the target is 3 clips or 6, meaning the previously-proven 3-clip pipeline would fail identically if resubmitted against this instance's current custom-node set today. It also converges with a concurrent investigation on a different branch chasing a monkeypatch collision for the monolithic-render approach, circumstantial evidence both are looking at the same root cause from two different workflows.

Uninstalling the conflicting package would have fixed this branch's symptom, but at the time of the run at least four other branches had active or queued GPU jobs on the same shared instance, and the concurrent investigation elsewhere hadn't resolved whether it needed that same package. Removing a shared dependency unilaterally, mid-investigation, wasn't attempted; this was reported as a blocked result instead.

## Where it landed

Blocked, not refuted. The hypothesis was never actually tested, because the chain mechanism itself is currently broken on this box for a reason that has nothing to do with clip count: two custom-node packages fighting over the same patch target. The one clip that did render came in exactly where prior single-clip figures put it, so the model, LoRA, and sampler stack are still fine. This is a genuine candidate for re-running, unchanged, once the node-package conflict is resolved by Gavin's call, and it would be the fastest path to actually testing the 3-versus-6-clip question this branch exists to answer.
