#!/usr/bin/env python3
"""yue-exp-001 metrics: pairwise audio distance between arm renders.

Reads 48kHz mono 16-bit PCM WAVs (one per arm, written by the pipeline's
ffmpeg decode step) and reports, for every arm pair:

  - bit_identical     : byte-for-byte equal sample arrays
  - corr              : Pearson correlation of the overlapping samples
  - log_spec_l1       : mean |log-magnitude-STFT| difference (dB-ish), the
                        actual perceptual-ish quality number
  - rms_db_delta      : loudness difference

The point of the arm set is that these numbers are only interpretable
against a noise floor. Two runs of the SAME model at the SAME seed
(arm0 vs armnull) give the reproducibility floor; the same model at a
DIFFERENT seed (arm0 vs armseedfloor) gives the seed floor. An
int8_convrot-vs-bf16 distance that is not clearly larger than the seed
floor is not evidence of quality loss.

Usage: yue_exp_001_metrics.py <wav-dir> [out.json]
"""
import glob
import itertools
import json
import os
import sys
import wave

import numpy as np


def read_wav(path):
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
        ch = w.getnchannels()
        sr = w.getframerate()
        sw = w.getsampwidth()
    if sw != 2:
        raise ValueError("%s: expected 16-bit PCM, got %d bytes/sample" % (path, sw))
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def stft_logmag(x, n_fft=2048, hop=512):
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    win = np.hanning(n_fft)
    frames = 1 + (len(x) - n_fft) // hop
    out = np.empty((frames, n_fft // 2 + 1))
    for i in range(frames):
        seg = x[i * hop:i * hop + n_fft] * win
        out[i] = np.abs(np.fft.rfft(seg))
    return 20.0 * np.log10(out + 1e-8)


def rms_db(x):
    return float(20.0 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12))


def main():
    wav_dir = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    paths = sorted(glob.glob(os.path.join(wav_dir, "*.wav")))
    arms = {}
    for p in paths:
        name = os.path.splitext(os.path.basename(p))[0]
        x, sr = read_wav(p)
        arms[name] = x
        print("loaded %-34s %8.2f s  rms %7.2f dBFS" % (name, len(x) / sr, rms_db(x)))

    if len(arms) < 2:
        print("\nWARNING: fewer than 2 arms rendered -- no pairwise comparison possible.")
        report = {"arms": {k: {"samples": int(len(v)), "rms_db": rms_db(v)} for k, v in arms.items()},
                  "pairs": [], "note": "insufficient arms for comparison"}
        if out_path:
            with open(out_path, "w") as fh:
                json.dump(report, fh, indent=2)
        return 0

    pairs = []
    print("\n%-30s %-30s %5s %8s %10s %9s" % ("A", "B", "ident", "corr", "logspecL1", "dRMSdB"))
    for a, b in itertools.combinations(sorted(arms), 2):
        xa, xb = arms[a], arms[b]
        n = min(len(xa), len(xb))
        ident = bool(len(xa) == len(xb) and np.array_equal(xa, xb))
        ca, cb = xa[:n], xb[:n]
        if np.std(ca) < 1e-12 or np.std(cb) < 1e-12:
            corr = float("nan")
        else:
            corr = float(np.corrcoef(ca, cb)[0, 1])
        sa, sb = stft_logmag(ca), stft_logmag(cb)
        m = min(len(sa), len(sb))
        l1 = float(np.mean(np.abs(sa[:m] - sb[:m])))
        drms = rms_db(cb) - rms_db(ca)
        pairs.append({"a": a, "b": b, "bit_identical": ident, "corr": corr,
                      "log_spec_l1_db": l1, "rms_db_delta": drms,
                      "overlap_samples": int(n),
                      "len_delta_samples": int(len(xb) - len(xa))})
        print("%-30s %-30s %5s %8.4f %10.3f %9.2f" % (a, b, ident, corr, l1, drms))

    report = {
        "arms": {k: {"samples": int(len(v)), "rms_db": rms_db(v)} for k, v in arms.items()},
        "pairs": pairs,
    }

    def find(sub_a, sub_b):
        for p in pairs:
            names = (p["a"], p["b"])
            if any(sub_a in n for n in names) and any(sub_b in n for n in names):
                return p
        return None

    repro = find("arm0_bf16", "armnull")
    seed = find("arm0_bf16", "armseedfloor")
    claim = find("arm0_bf16", "arm1_int8convrot")
    print("\n--- interpretation ---")
    if repro:
        print("reproducibility floor (same model, same seed): log_spec_l1 = %.3f dB, bit_identical=%s"
              % (repro["log_spec_l1_db"], repro["bit_identical"]))
    if seed:
        print("seed floor (same model, seed 42 vs 43):        log_spec_l1 = %.3f dB"
              % seed["log_spec_l1_db"])
    if claim:
        print("claim under test (bf16 vs int8_convrot):       log_spec_l1 = %.3f dB"
              % claim["log_spec_l1_db"])
    if claim and seed:
        ratio = claim["log_spec_l1_db"] / seed["log_spec_l1_db"] if seed["log_spec_l1_db"] else float("inf")
        report["claim_over_seed_floor_ratio"] = ratio
        print("claim / seed floor ratio:                      %.2fx" % ratio)
        print("(ratio near or below 1.0 means the quantization difference is not")
        print(" distinguishable from ordinary seed-to-seed variation. This is N=1")
        print(" on one prompt: a smoke test, not a quality verdict.)")

    if out_path:
        with open(out_path, "w") as fh:
            json.dump(report, fh, indent=2)
        print("\nwrote %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
