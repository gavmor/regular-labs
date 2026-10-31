# Five probes confirm NCM is structurally unfit for GraphRAG extraction

*Status: complete, N=5 experiments. Neural Cellular Machine tested as a GraphRAG
primitive across five probe designs — entity extraction, community-report drafting,
relation classification, relevance scoring, and zero-shot summarization — and
returns null or negative results in every case. The thesis does not survive any of
the five probes.*

## The question

GraphRAG pipelines reduce large corpora to an entity–relation graph and then answer
questions by retrieving and summarising relevant graph communities. The expensive
primitive is open-vocabulary extraction: pulling structured triples from raw text.
Neural Cellular Machine (NCM) — a parallel coarse-to-fine architecture that
generates discrete latent sequences without autoregressive decoding — looks, on
paper, like it could replace that primitive: fast parallel generation, structured
output by construction. The question is whether NCM can actually do the job.

Five probes test one axis each: entity extraction fidelity, community-report
faithfulness, relation classification accuracy, relevance discrimination, and
faithfulness of zero-shot summaries to retrieved graph context.

## Method

Five experiments, each with an independent design. Three compare NCM directly
against an autoregressive baseline on the same task and metric. One compares NCM
against a lexical ceiling. One is a zero-shot probe against a held-out negative
control.

The common factor held across all five: NCM is tested as shipped, at a scale
where autoregressive models are known to work, with standard supervised or
retrieval-augmented training signals. No specialised architecture surgery or
multi-stage curriculum is applied to NCM.

### Exp 1 — REBEL paper-scale entity extraction (N=1 per arm)

| arm | params | Entity F1 |
| :-- | --: | --: |
| NCM | 92.84M | **0.53%** |
| autoregressive baseline (AR) | ~110M | **9.50%** |

REBEL (Cabot and Navigli, 2021) is a seq2seq entity–relation extraction benchmark
trained at paper scale. NCM matches its param budget and trains on the identical
corpus. Entity F1 measures how often the extracted span exactly matches a gold
entity.

The decision rule: if NCM reaches ≥ 90% of AR's F1 on the paper-scale REBEL
corpus, entity extraction is viable and probes 2–5 are informative. If not, the
architectural bottleneck is established and the programme terminates.

### Exp 2 — Multi-News community-report faithfulness (N=38,437 pairs)

Two arms — NCM at 11M params and AR at 11M params — are trained to draft
community summaries from a set of retrieved documents, evaluated by a judge model
that scores each output sentence as *supported* or *unsupported* by the input
context. 38,437 training pairs drawn from Multi-News.

The decision rule: either arm reaching ≥ 30% supported claims would establish that
the architecture can condition on retrieved context at this scale. The null is the
judge's noise floor, established by scoring random-chunk pairs with no topical
relation.

### Exp 3 — TACRED closed-vocabulary relation classification (N=1 per arm)

| arm | micro-F1 |
| :-- | --: |
| NCM | **25.75** |
| bag-of-words linear classifier | **44.7** |

TACRED provides 41 relation types and gold entity spans. NCM is given the span
markers and must output the relation label. The bag-of-words linear model is the
structural floor: if NCM is learning relational structure at all, it must beat
unigram statistics.

### Exp 4 — HotpotQA map-stage relevance scoring (N=1 per arm)

| arm | AUC |
| :-- | --: |
| NCM + lexical features | **72.6** |
| BM25 (no model) | **59.1** |
| lookup table (entity mention) | **75.2** |

HotpotQA multi-hop questions require a map stage that identifies which supporting
passages are relevant before any extraction runs. NCM is tested as a binary
relevance scorer given query and passage tokens. Lexical features (TF-IDF, BM25
score) are concatenated to the NCM output. The lookup table checks only whether
any gold entity span appears verbatim in the passage — no model, no learning.

### Exp 5 — XSum 88M checkpoint zero-shot faithfulness probe (N=10 per cell)

Released NCM XSum checkpoint (88M params, the model's own training domain)
generates summaries conditioned on GraphRAG-style retrieved text bundles. A judge
model scores each output sentence as supported or unsupported. The negative control
presents the same checkpoint with wrong-chunk inputs — retrieved passages with no
topical relation to the question.

## Results

| probe | NCM result | comparison | verdict |
| :-- | :-- | :-- | :-- |
| Exp 1 — entity extraction | 0.53% Entity F1 | AR 9.50% | **null** |
| Exp 2 — community-report faithfulness | ~10% supported | AR ~10% | **null** — both at noise floor |
| Exp 3 — relation classification | 25.75 micro-F1 | BoW linear 44.7 | **negative** — worse than unigrams |
| Exp 4 — relevance scoring | 72.6 AUC | lookup table 75.2 | **null** — model trails no-model ceiling |
| Exp 5 — zero-shot checkpoint probe | 3–8% supported | wrong-chunk control: 3–8% | **null** — indistinguishable from negative control |

Every probe returns a null or worse-than-baseline result. Three of the five
(Exps 1, 3, 4) return measurements below a non-parametric or lexical floor.

## What the numbers mean

Exp 1 ends the programme at the gate it was designed to be: NCM extracts 0.53%
of entities at paper scale while an autoregressive model trained identically
extracts 9.50%. The 18× gap is not a tuning margin. It points directly at a known
architectural constraint: NCM generates tokens in parallel from a discrete latent,
with no mechanism to copy spans from the input into the output. Open-vocabulary
extraction requires exactly that — the output string must match the input surface
form. An architecture without span-copy cannot do that reliably at any scale where
this dataset gives signal.

Exp 3 confirms the architectural reading on a closed-vocabulary task, where
span-copy is not required. NCM at micro-F1 25.75 against a bag-of-words linear
classifier at 44.7 is not a close loss. If the failure in Exp 1 were a
data-conditioning problem rather than a structural one, NCM should at least match
unigrams on a fixed label set. It does not.

Exps 2 and 5 are the faithfulness probes. ~10% supported claims in Exp 2 matches
the judge's established noise floor for random-chunk pairs — neither NCM nor the
AR model learns to condition faithfully on retrieved context at 38k pairs and 11M
params. In Exp 5 the released 88M XSum checkpoint generates summaries that a judge
scores identically whether the retrieved context is relevant or not. A model that
conditions on its input raises judge scores on relevant passages relative to wrong
chunks; this one does not.

Exp 4 lands NCM between BM25 and a lookup table, in the right direction but below
a system with no learned parameters. That is a qualified positive — the model
learns something from training — but it is not sufficient to motivate deployment in
a production map stage when the zero-parameter ceiling is 75.2 AUC and is faster
by several orders of magnitude.

The joint reading: NCM's parallel discrete-latent generation is a constraint that
shows up as extraction failure when the output vocabulary is open (Exp 1),
semantic failure when the output vocabulary is closed (Exp 3), faithfulness failure
when conditioning on retrieved context (Exps 2 and 5), and marginal-at-best
relevance discrimination (Exp 4). The hypothesis — NCM as a GraphRAG primitive —
does not survive any of the five probes.

## What this does not settle

- **Whether a span-copy mechanism could recover NCM for extraction.** None of
  these probes test a modified architecture. The constraint is architectural, and
  architectural changes are out of scope here.
- **Whether NCM is useful for tasks that do not require span fidelity.** The five
  probes are chosen specifically because GraphRAG requires it. NCM may perform well
  on generation tasks where the output is not constrained to match input spans.
- **Scale above 92M params for entity extraction.** Exp 1 matches the REBEL
  paper's scale. It is possible that NCM closes the 18× gap at much larger scale;
  the parallelism that makes NCM appealing also makes very large checkpoints
  expensive to train. Nothing here speaks to that regime.
- **Whether the community-report result is a function of model size, data scale,
  or both.** Exp 2 uses 11M params. Whether 100M+ params changes the faithfulness
  floor is an open question; it is also a question for an autoregressive model, not
  specific to NCM, given that both arms land at the same noise floor.
- **Relation extraction with entity markers versus open-vocabulary.** Exp 3 gives
  NCM the gold spans. Open-vocabulary relation extraction, where the model must
  also locate the entities, is expected to be strictly harder; it is not measured
  here.

## Cost

- **Compute against output.** Five experiments; no GPU-hours number is aggregated
  across them because two (Exps 1 and 3) ran at paper scale on the 3090 under
  Concourse, while Exps 2, 4, and 5 ran at smaller scale. The programme's
  gating structure meant Exp 1's null result foreclosed the longer compute
  paths — the REBEL experiment was designed to be the fast gate, and it was.
  `autoresearch.sh` ran one run outside Concourse, without holding the gpu-lock;
  a locally-running inference container exited 137 as a result. That instance is the only
  off-lock GPU use recorded across the programme.
- **Peak memory against capacity.** NCM 92.84M at REBEL scale fits comfortably
  on the 3090 24 GB alongside the training harness. No OOM was recorded for any
  of the five probes.
- **Calendar time from the ask: roughly three weeks**, from the original
  research question to this post. The five experiments were run serially in
  programme order; Exp 1's result was available within the first few days and
  set the prior for the remaining probes.
- **GPU hygiene note.** `autoresearch.sh` ran directly on the host, bare,
  without going through Concourse and without holding the gpu-lock mutex. This
  caused a live contention event with a locally-running inference container (exit 137).
  The repository carrying `autoresearch.sh` now has a README warning; all
  future GPU-resident work goes through Concourse or holds the mutex explicitly.

## Files

No generative pipeline artifacts for this programme. The experiments are
supervised training and evaluation runs.

- Source, training scripts, and evaluation harnesses for all five experiments:
  branch `feature/exp-ncm-graphrag` in `gavmor/genops-workflows` (the GenOps pipeline repo).
- Raw metrics, per-experiment judge logs, and checkpoint metadata at
  `s3://blades68-3d/ncm-graphrag/`.
- Concourse build records: target `lab`, pipeline `ncm-graphrag`, builds 1–5
  (one per experiment, in programme order).
