# Pose landmarks and face detection cannot classify charref view angles from stylized renders

*Status: falsified. Two families of computer-vision signals — MediaPipe pose geometry and face-area detection — are tested against 62 charref render clips (248 frames) to classify four shot types (front, rear, side, close-up). Neither reaches a useful accuracy floor, and the signals that discriminate one class damage another.*

## The question

The charref pipeline generates four shots per character: front, rear, side, and close-up. The filenames carry the character identity but not the view label. Downstream sorting and audit tools need the view label without human review of each clip.

The question is whether cheap, GPU-free geometry signals can infer the view label post-hoc from the renders themselves.

## Method

62 clips at 480×864×107 frames from `/tmp/charref_audit/`. Four frames are sampled per clip at positions 13, 40, 67, and 94, giving 248 frames total — one per shot. Ground-truth labels come from the generation order embedded in the clip sequence (clips 0, 16, 32, 48 are always shot 1 / front, and so on).

**Signal family 1: MediaPipe pose landmarks (PoseLandmarker 1.0.1 Tasks API)**

Three derived features:
- `sho_sign` — signed shoulder width (right shoulder x minus left shoulder x, in normalised frame coordinates). Positive when the right shoulder appears to the left — the convention for a character facing toward camera.
- `nose_ear_z` — nose depth minus mean ear depth. Negative indicates the nose is in front of the ears, consistent with a face-toward-camera orientation.
- `sho_torso` — shoulder width divided by torso height. Smaller values indicate a tight crop or compressed perspective.

Classification rule:
- `nose_ear_z > 0.10` **or** `sho_sign < -0.05` → rear
- `sho_torso < 0.60` → close-up
- `abs(sho_sign) < 0.15` → side
- else → front

**Signal family 2: MediaPipe face detection (BlazeFace short-range)**

Face bounding box area as a fraction of frame area, and face aspect ratio (width/height).

Classification rule:
- no face detected → rear
- `area > 0.12` → close-up
- `aspect < 0.85` → side
- else → front

**Pass criterion (pre-registered):** ≥90% agreement with ground truth on all four classes.

## Results

**Pose landmarks:**

| View | Correct | Total | Accuracy |
|---|---|---|---|
| front | 55 | 55 | 100% |
| rear | 32 | 62 | 52% |
| side | 53 | 62 | 85% |
| close-up | 0 | 69 | 0% |
| **overall** | **140** | **248** | **56%** |

**Face detection:**

| View | Correct | Total | Accuracy |
|---|---|---|---|
| front | 9 | 55 | 16% |
| rear | 31 | 62 | 50% |
| side | 0 | 62 | 0% |
| close-up | 60 | 69 | 87% |
| **overall** | **100** | **248** | **40%** |

Neither classifier reaches 90% on any class except the ones the other fails. No combination fixes both.

## What the numbers show

**Rear at 52%:** The 30 unclassified rear frames have `sho_sign ≈ -0.31` and `nose_ear_z ≈ -0.29` — the same range as confirmed front frames. MediaPipe places visible-shoulder silhouettes and depth estimates in rear-view stylized renders identically to front-facing ones. This is a model-training-data mismatch: the pose estimator was trained on photographs, not halftone/litho stylization. No threshold on the available signals separates these 30 clips from front without poisoning front accuracy.

**Close-up at 0% (pose) / 87% (face):** Close-up is a crop, not a viewing angle. Pose geometry cannot distinguish a tight-cropped front from a full-body front — the landmark ratios are identical. Face area correctly identifies tight crops most of the time, but the area distributions for front and close-up fully overlap (both range 0.08–0.43 in this corpus), so the 0.12 threshold fails for clips where the front shot frames the character at medium distance.

**Side at 85% (pose) / 0% (face):** Shoulder asymmetry works for profiles. Face aspect ratio does not — stylized profiles do not narrow the face bounding box reliably enough to exceed the threshold.

**Front at 100% (pose) / 16% (face):** Pose geometry correctly identifies full-face-forward frames. The face detector misclassifies most as close-up because the characters are rendered at medium shot, not long shot, giving face areas above 0.12.

## What this does not settle

The 30 ambiguous rear frames may be recoverable by checking whether eye and mouth landmarks are placed on the front of the head or extrapolated behind it — a signal available from the full landmark set but not tested here. A facing-direction model trained on stylized renders would likely close the gap, but that is a supervised learning problem, not a geometry problem.

The close-up/front confusion is a composition question. The two shot types in this corpus are not separated by face size — they are separated by how much body the director chose to include. That requires either a body-segment detector or, more reliably, a label baked into the filename at render time.

## Cost

- **Compute:** MediaPipe runs CPU-only. 248 frames classify in under 3 minutes on a consumer CPU. No GPU time consumed.
- **Calendar time from the original ask:** 2 days (ask: 2026-09-18, result: 2026-09-20).
- **Active build span:** approximately 4 hours across two sessions.

## Files

- Classification scripts: experiment branch `exp-018` of `gavmor/comfyui-workflows`, directory `gen_charref/`.
- Corpus: `/tmp/charref_audit/` (62 clips, not committed — regenerate from the charref pipeline).
- KANBAN entry: `exp-018` closed in `Done`, `KANBAN.md` on `main`.
