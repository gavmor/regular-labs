# A TTS benchmark harness, four models in, ten to go

Fourth write-up out of the [experiment register](2026-09-02-experiments-sankey.html), and the first one that isn't a pass/fail hypothesis test. `feature/tts-voice-clone-benchmark` is building a [Concourse](https://concourse-ci.org/)-orchestrated harness to compare roughly 14 local zero-shot voice-cloning models on identical inputs. This is a progress snapshot, not a verdict: four models are wired and validated so far, ten are not.

## What it's actually testing

The source is a Reddit thread ("Best AI Voice Cloning in 2026") plus its top comments, cross-checked against what's actually feasible on this rig. Zero-shot cloning only: the source article's per-model rows used 45 minutes of fine-tuning data per voice, which isn't a fair "same inputs" comparison against a harness that hands every model the same short reference clip and walks away. That reference clip is fixed and documented: `reference_24k_mono.wav`, [LibriSpeech](https://www.openslr.org/12/) test-clean speaker 6930, utterance `6930-75918-0003`, 23.3 seconds, with the exact script text held constant across every model too.

<audio src="images/2026-09-06-tts-voice-clone-benchmark-progress/xtts-v2-sample0.wav" controls></audio>
<audio src="images/2026-09-06-tts-voice-clone-benchmark-progress/chatterbox-turbo-sample0.wav" controls></audio>
<audio src="images/2026-09-06-tts-voice-clone-benchmark-progress/omnivoice-sample0.wav" controls></audio>
<audio src="images/2026-09-06-tts-voice-clone-benchmark-progress/dots-tts-sample0.wav" controls></audio>

*Sample 0 from each of the four validated models, in order (XTTS-v2, Chatterbox Turbo, OmniVoice, dots.tts), pulled from the exited `blades68-tts-bench-<model>` Docker containers still on disk (`/tmp/<model>_sample_0.wav`) rather than from git, since generated benchmark audio isn't committed. All four clone the same `reference_24k_mono.wav` speaker reading the same script text. Durations and formats check out against this article's own numbers: XTTS-v2 12.94s/24kHz mono, Chatterbox Turbo 13.88s/24kHz mono, OmniVoice 12.62s/24kHz mono, dots.tts 11.2s/48kHz mono (dots.tts is the only one of the four that renders at 48kHz).*

Every model gets its own directory under `tools/tts-bench/<model>/` with a FastAPI server exposing `/health`, `/load`, `/benchmark`, and `/unload`, running as its own Docker Compose service so it gets real GPU access, the same host-level-passthrough pattern already used for `comfyui-local`. A `tts-benchmark-<model>` Concourse job, mutexed through `gpu-lock`, drives each one. Only one model's service can be up at a time: this rig's single 24GB 3090 and a home partition sitting at 98% full can't hold two models' weights simultaneously.

## What "validated" means here

Validated means each model ran a real `/benchmark` call through Concourse and `gpu-lock`, produced actual generated audio, and returned real measured numbers: load time, per-sample generation time, peak VRAM via the model process's own `torch.cuda` stats, and real-time factor (RTF). It does not mean anyone listened to the output and judged voice-cloning quality; no MOS score or by-ear quality call is recorded for any of the four. This harness measures whether a model runs and how expensive it is, not whether it sounds right yet.

Four models cleared that bar, in this order:

- **[XTTS-v2](https://huggingface.co/coqui/XTTS-v2)** (Coqui): first validated, build #5 after three unrelated bugs (a `transformers` version that dropped a symbol `coqui-tts` still expected, a missing `torchcodec` dependency, and a root-owned cache directory from Docker's bind-mount auto-create). Load 67.7s, generation 3.3-5.3s/sample, peak VRAM ~1.9-2.0GB, RTF 2.4-3.7x.
- **[Chatterbox Turbo](https://huggingface.co/ResembleAI/chatterbox-turbo)** (Resemble AI): second validated, one new bug (a watermarking dependency silently disabled itself because `setuptools>=81` no longer ships `pkg_resources`). Load 7.8s, generation 3.6-12.8s/sample, peak VRAM ~3.3GB, RTF 1.1-3.7x.
- **[OmniVoice](https://github.com/k2-fsa/OmniVoice)** (k2-fsa): third validated, one new container-level bug (Triton needed a full C toolchain for its first JIT compile, which neither prior model had exercised). Load 2.1s, generation 1.9-4.5s/sample, peak VRAM ~3.86GB, RTF up to 6.5x, the fastest of the four.
- **[dots.tts](https://github.com/rednote-hilab/dots.tts)** (rednote-hilab): fourth validated, no new bugs, first attempt clean. Load 24.2s, generation 22.8-39.0s/sample, peak VRAM ~5.6-5.7GB, RTF 0.29-0.44, the only one of the four that runs slower than real time on this box.

## Where the other ten stand

Of the roughly 14 candidates, this is where things actually sit as of this snapshot:

- **Not started, no blockers known:** [Chatterbox](https://huggingface.co/ResembleAI/chatterbox) (base), [CosyVoice 3](https://github.com/FunAudioLLM/CosyVoice), [VibeVoice 1.5B](https://huggingface.co/microsoft/VibeVoice-1.5B), [IndexTTS-2](https://github.com/index-tts/index-tts).
- **Feasibility checked, not scaffolded:** [Audio8-TTS-Preview-0.1b](https://huggingface.co/Audio8/Audio8-TTS-Preview-0.1b) ([Audio8-AI/Audio8_TTS](https://github.com/Audio8-AI/Audio8_TTS) on GitHub; licensing is fine for this use, needs a `git clone` install rather than a plain `pip install`), [MOSS-TTS](https://github.com/OpenMOSS/MOSS-TTS) v1.5 (turns out to need only ~5GB VRAM for the local checkpoint in scope, despite the source article flagging it as memory-hungry, likely conflating it with a larger variant), [Fish S2 Pro](https://huggingface.co/fishaudio/s2-pro) ([Fish-Speech](https://github.com/fishaudio/fish-speech); flagged rather than guessed at: unclear if the open-source repo actually ships the "S2 Pro" checkpoint or only the plain "S2," since "S2 Pro" also exists as a separate paid hosted tier).
- **Partially wired, unvalidated, and explicitly not to be duplicated:** [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS). A separate branch already built a service and a smoke-test job for this one, merged to main, but it OOM'd once against a concurrent render and was never re-validated afterward; nothing is currently running on its port. The benchmark harness's own notes flag that a later candidate ("faster-qwen-tts") should extend that existing work rather than scaffold a fifth Qwen3-TTS install from scratch.
- **Explicitly out of scope:** [ElevenLabs](https://elevenlabs.io/) Professional, a paid cloud API with no local VRAM/GPU-time to capture. Worth a one-line mention in a future final report, not a row in the comparison table.

## Where it actually stands

**Ongoing, four of roughly fourteen wired and validated, ten remaining.** This is not a hypothesis test with a pass/fail outcome: the register correctly tracks it as a non-A/B benchmark build-out. No cross-model comparison or ranking exists yet; what exists is a working harness pattern (proven three times over after the first model's install debugging) and four models' worth of raw performance numbers, with no quality assessment layered on top of any of them. The honest state of this branch today is "harness works, four data points collected," not "here's the best model."
