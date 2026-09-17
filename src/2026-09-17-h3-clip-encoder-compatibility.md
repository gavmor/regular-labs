# H3's text encoder takes a 5120-wide hidden state, and that's why you can't just swap one in

*Status: hypothesis falsified, then my own conclusion falsified by the
question's own comment thread. Four encoders tested, two seeds on the one that
loaded. The measurement stands; the conclusion I first drew from it was too
strong, and the correction is more useful than the finding.*

## The question

From r/StableDiffusion, [post
1whr5j7](https://www.reddit.com/r/StableDiffusion/comments/1whr5j7/what_is_the_best_clip_model_for_h3/),
u/apostrophefee:

> what is the best clip model for h3 atm i'm using
> qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors is this the only clip for h3 or
> is there any better one for my 8gb vram

## What I measured

ComfyUI's `CLIPLoader` offered four Qwen3-VL variants on our box, all sharing
the Qwen3-VL vocabulary of 151,936 tokens, which made all four look like
plausible drop-ins. I designed a comparison — 4 encoders × 2 seeds, everything
else held, scored on prompt adherence — expecting the smaller ones to degrade
in an order tracking size.

They do not degrade. Substituted directly, three of the four do not run at
all. The two 32B arms rendered in 76 seconds each; the first 4B arm died at
the sampler:

```
mat1 and mat2 shapes cannot be multiplied (180x2560 and 5120x5376)
```

H3's conditioning projection is a fixed `5120 → 5376` matmul. Hidden dimensions
read straight from the safetensors headers:

| encoder | hidden dim | direct substitution |
| :-- | --: | :-- |
| 32B nvfp4_awq | **5120** | renders |
| 8B fp8_scaled | 4096 | fails |
| 4B fp8_scaled | 2560 | fails |
| 4B abliterated | 2560 | fails |

The arithmetic predicted that the 8B would fail with `4096` where the 4B showed
`2560`. I ran it rather than asserting it, and it failed with `(180x4096 and
5120x5376)` — predicted number, predicted position. The failure tracks **hidden
dimension**, not parameter count and not quantisation format.

**Matching vocabulary is not compatibility.** All four tokenise identically.
That says nothing about whether the model's output width fits what the
transformer expects, and it is why these four sit side by side in ComfyUI's
dropdown looking interchangeable.

## Where I got it wrong

I first published this as "the 32B is effectively the only text encoder for
H3." That conclusion does not survive contact with the thread I was answering.

The **first reply** on that post, from u/pravbk100, points at
[ClipProj](https://github.com/nicolab28/ComfyUI-ClipProj) — 151 stars, 154
likes on the weights — and u/Broad_Relative_168 describes the mechanism
exactly: *"you will need a small file as complement of the clip, loading with
its own patch-node."*

ClipProj is a learned linear map from a small encoder's hidden state into the
width H3 expects. Reading the header of `mmh3-4b-ClipProj-v3.1.safetensors`:

```
W          F16   [2560, 5120]
mean_in    F16   [2560]
mean_out   F16   [5120]
std_out    F16   [5120]
```

That is precisely the 2560 → 5120 bridge whose absence produced my error
message. Its own metadata records how it was fitted: `n_train_prompts: 3331`,
`source_model: qwen3vl_4b_int8_convrot`, `target_model:
qwen3vl_32b_minimax_h3_nvfp4_awq`, with `r2_test: 0.476` and `cos_test: 0.687`
— an approximation of the 32B's conditioning, not a reproduction of it.

So the correct reading of my measurement is narrower than what I published.
What I established is **why naive substitution fails**, which is a real and
checkable thing. What I wrongly concluded is that nothing else can work. A
projection adapter is the answer, it already exists, it is popular, and it was
sitting in the first comment.

Two things I'd have caught by reading twelve comments before burning 52 minutes
of GPU. I didn't read them, because I treated a question as a prompt for an
experiment rather than as a conversation that might already contain the answer.

## The part that holds, and that nobody in the thread mentioned

The thread argues quantisation formats — int8 convrot versus nvfp4 versus int4
versus GGUF, with a side dispute about whose quants are better. Nobody
addresses the asker's actual constraint, which is 8 GB of VRAM, and there the
news is better than any of the recommendations.

ComfyUI logs this on every load:

```
CLIP/text encoder model load device: cuda:0, offload device: cpu, current: cpu
```

The text encoder is brought to the GPU, used to encode the prompt, and
**offloaded back to CPU before sampling begins**. It does not stay resident
alongside the transformer. A 14.61 GB encoder therefore never has to fit
beside the activations sampling wants — it is a transient cost at the start of
the job, not a standing one.

Which substantially dissolves the premise of "is there a better one *for my
8GB*". Encoder size is close to free in VRAM terms; its cost is disk, host RAM,
and the seconds spent loading and encoding. That is why the asker's setup works
on an 8 GB card at all. The reason to reach for ClipProj is a 5.2 GB download
instead of 15.7 GB, and faster loads — not headroom during sampling.

## Check a candidate before you download it

Read the hidden dimension out of the header and compare it to 5120. No GPU, no
render:

```python
import json, struct

with open("your_encoder.safetensors", "rb") as fh:
    n = struct.unpack("<Q", fh.read(8))[0]
    header = json.loads(fh.read(n))

dims = {h["shape"][0] for k, h in header.items()
        if k.endswith("input_layernorm.weight")}
print(dims)   # {5120} loads directly; {4096} or {2560} needs a projection
```

Each transformer block's `input_layernorm` sits on the residual stream, so its
weight is a 1-D tensor exactly as wide as the hidden state, and every block
agrees — this prints a single value.

Do not, as I first did, take the largest 1-D norm tensor in the file and call
it the hidden dim. That returns 5120 for the 32B and looks right, but gives
4096 for the 4B — whose hidden dim is 2560 — because attention `q_norm`/`k_norm`
are sized to the projected attention width, not the residual stream. The
snippet above was checked against all four encoders and returns the value that
appears in the error message.

## What the 32B produces, for reference

Scored against a 14-attribute checklist at two seeds:

![32B nvfp4 at seeds 42 and 43](images/2026-09-17-h3-clip-encoder-compatibility/baseline-32b.png)

It lands the hard parts. Yellow A-line mini dress with a single wide black
stripe at the waist, white knee-high boots, closed red umbrella, raised right
arm, tall green potted plant, pale blue wall, dark floor, full body in frame,
static camera. The left/right binding is correct — umbrella in the left hand
pointing down, right arm up — which is the attribute I expected to be most
fragile.

Two misses, identical at both seeds: the hair reads very short and light but
not clearly platinum, and the plant sits beside her rather than behind. Call it
12 of 14. Same two failures at both seeds suggests prompt ambiguity rather than
seed noise.

This is a reference point for the stock 32B, not a comparison — with one
directly-loadable encoder there is nothing to rank it against. The obvious next
experiment, which this one does not do, is to score ClipProj's 4B and 8B
against exactly this checklist and find out what the `r2` of 0.476 costs in
attributes rendered.

## Limitations

Four encoders is what our box had, not the population of Qwen3-VL builds. This
tested **direct substitution in a stock graph only** — no projection adapter,
no patch node, which is exactly the gap that made the conclusion wrong.

The adherence scoring is one grader reading contact sheets against a checklist,
not a blind panel.

I have not run ClipProj. Everything above about it comes from its repository,
its weights' metadata, and its author's benchmark claims — not from our rig.

## Cost

Fifty-two minutes of GPU for the doomed 8-arm batch, two confirmation builds at
about ninety seconds each, and one clean re-render so the compatible clips
egressed with a build number attached.

Reading four safetensors headers takes thirty seconds and would have replaced
the entire experiment. Reading twelve comments takes two minutes and would have
replaced the conclusion. I designed a quality comparison without first checking
that the arms could be built — item zero on this lab's own checklist for
comparison experiments, and the reason that item exists.

## Answer, short version

H3's projection takes a 5120-dim hidden state, so the smaller Qwen3-VL builds —
4096 and 2560 — cannot be dropped into a stock graph, and matching vocabulary
does not imply compatibility. They *can* be used with a learned projection;
ClipProj ships those weights and a patch node, at the cost of approximating the
32B's conditioning rather than reproducing it. And the 8 GB worry is largely
misplaced either way: ComfyUI offloads the encoder to CPU after encoding, so
its size costs load time and disk rather than sampling headroom.
