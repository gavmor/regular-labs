import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
VARIANTS = {
    'original': '/usr/share/ollama/.ollama/models/blobs/sha256-e62d463c135ffe283df8d94b279a96ca145ac128b52ce854478613045bf4de15',
    'qwen38': '/usr/share/ollama/.ollama/models/blobs/sha256-2a5f3565f39cf885103da591182c1266da64745737b42b452fd3e675369f1211',
    'openuncensored': 'OpenUncensored-Inkling-2-Mini-Q4_K_M.gguf',
    'unbound': 'Inkling-2-Mini-Unbound-v2-Q4_K_M.gguf',
    'atomicchat': 'Inkling-2-Mini-Uncensored-AD-Q4_K.gguf',
}
URL = 'http://127.0.0.1:8092'
CTX = 16384
MAX_OUTPUT = 2048
SEED = 42


def make_cases():
    dataset = (ROOT / 'gsm8k-test.jsonl').read_bytes()
    assert hashlib.sha256(dataset).hexdigest() == '3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14'
    rows = [json.loads(line) for line in dataset.splitlines()]
    for index in sorted(random.Random(SEED).sample(range(len(rows)), 8)):
        row = rows[index]
        yield {'id': f'gsm8k-{index}', 'group': 'GSM8K', 'prompt': row['question'] + '\nReturn just the final number, with no units.', 'expected': row['answer'].rsplit('#### ', 1)[1].replace(',', '')}
    for name, snippet, expected in [
        ('python', 'a = [1, 2, 3]\nb = a\na = a[1:]\nb.append(4)\nprint(sum(a) - sum(b))', '-5'),
        ('javascript', 'console.log([...new Set([2, 1, 2, 3, 1])].map((x, i) => x-i).join(","));', '2,0,1'),
        ('sql', 'SQL table t(x) has three rows: 2, NULL, 5. SELECT COUNT(x), SUM(x) FROM t;', '2,7'),
    ]:
        yield {'id': name, 'group': 'Code reading', 'prompt': f'Give the exact output of the following. For a SQL row give comma-separated values with no spaces. Output only the answer.\n\n{snippet}', 'expected': expected}
    yield {'id': 'read-one', 'group': 'Tool use', 'prompt': 'Use the read tool on token.txt. Return only the token, without quoting it.', 'expected': 'orbit-75319-fir', 'files': ['token.txt']}
    yield {'id': 'read-two', 'group': 'Tool use', 'prompt': 'Use the read tool on quantities.txt and adjustment.txt. Subtract the adjustment from the second quantity and return just the resulting number.', 'expected': '638', 'files': ['quantities.txt', 'adjustment.txt']}


def pi_case(case, model, dest, env, fixture):
    args = ['timeout', '--kill-after=3s', '120s', 'pi', '--mode', 'json', '--print', '--offline', '--model', f'inkling-bench/{model}', '--thinking', 'off', '--system-prompt', 'Follow the requested answer format. Use the provided tools when the user requests them.', '--no-extensions', '--no-skills', '--no-prompt-templates', '--no-context-files', '--session-dir', str(dest / 'sessions')]
    args += ['--tools', 'read'] if 'files' in case else ['--no-tools']
    start = time.monotonic()
    started = first_text = end = None
    assistant = []
    reads = set()
    pending_reads = {}
    errors = []
    log_path = dest / (case['id'] + '.jsonl')
    with log_path.open('w') as log, log_path.with_suffix('.stderr').open('w') as err, subprocess.Popen(args + [case['prompt']], cwd=fixture, env=env, text=True, stdout=subprocess.PIPE, stderr=err) as proc:
        for line in proc.stdout:
            log.write(line)
            now = time.monotonic()
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind = event.get('type')
            msg = event.get('message') or {}
            if kind == 'agent_start' and started is None:
                started = now
            elif kind == 'message_update' and first_text is None:
                delta = event.get('assistantMessageEvent') or {}
                if delta.get('type') == 'text_delta' and (delta.get('delta') or '').strip():
                    first_text = now
            elif kind == 'message_end' and msg.get('role') == 'assistant':
                assistant.append(msg)
            elif kind == 'tool_execution_start' and event.get('toolName') == 'read':
                pending_reads[event['toolCallId']] = (event.get('args') or {}).get('path', '')
            elif kind == 'tool_execution_end' and not event.get('isError') and event.get('toolCallId') in pending_reads:
                reads.add(Path(pending_reads.pop(event['toolCallId'])).name)
            elif kind == 'agent_end':
                end = now
        rc = proc.wait()
    final = assistant[-1] if assistant else {}
    answer = ''.join(c.get('text', '') for c in final.get('content', []) if c.get('type') == 'text').strip()
    if case['group'] == 'GSM8K':
        answer = answer.replace(',', '')
    if rc:
        errors.append(f'pi exit {rc}')
    if not end:
        errors.append('missing agent_end')
    if any(m.get('model') != model for m in assistant):
        errors.append('unexpected Pi model')
    stop = final.get('stopReason')
    if stop in ('error', 'aborted'):
        errors.append(final.get('errorMessage') or stop)
    start = started or start
    result = {**case, 'answer': answer, 'stop': stop, 'reads': sorted(reads), 'errors': errors, 'pass': not errors and stop == 'stop' and answer == case['expected'] and set(case.get('files', [])).issubset(reads), 'first_text_s': round(first_text - start, 3) if first_text else None, 'elapsed_s': round((end or time.monotonic()) - start, 3), 'output_tokens': sum(m.get('usage', {}).get('output', 0) for m in assistant)}
    print(f"{model} {case['id']}: {'PASS' if result['pass'] else 'FAIL'} ({result['elapsed_s']:.2f}s, stop={stop})", flush=True)
    return result


def run_model(model, out, env, fixture, cases):
    dest = out / model
    dest.mkdir()
    bindir = ROOT.parents[1] / 'llama.cpp' if model == 'original' else ROOT.parent / 'b12633' / 'llama-b12633'
    flags = ['-m', str(ROOT.parent / VARIANTS[model]), '--alias', model, '-ngl', 'all', '--fit', 'off', '-ot', '.*=CUDA0', '-fa', 'on', '-ctk', 'q8_0', '-ctv', 'q8_0', '-b', '512', '-ub', '256', '-c', str(CTX), '-np', '1', '--temp', '0', '--seed', str(SEED), '--chat-template-kwargs', '{"reasoning_effort":0}', '--cache-ram', '0', '--host', '127.0.0.1', '--port', '8092', '--cors-origins', 'localhost', '-lv', '4']
    if model == 'original':
        flags += ['--lazy-mode', 'off']
    if model == 'qwen38':
        flags[flags.index('--chat-template-kwargs') + 1] = '{"reasoning_effort":"low","enable_thinking":false}'
    log_path = dest / 'server.log'
    libraries = str(bindir)
    if model == 'original':
        libraries += ':/usr/local/lib/ollama/cuda_v13'
    with log_path.open('w') as log, subprocess.Popen([str(bindir / 'llama-server'), *flags], env={**env, 'LD_LIBRARY_PATH': libraries}, stdout=log, stderr=subprocess.STDOUT) as server:
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError(f'server exited {server.returncode}; see {log_path}')
                try:
                    with urllib.request.urlopen(URL + '/v1/models', timeout=1) as response:
                        row, = json.load(response)['data']
                    if row['id'] == model and row['meta']['n_ctx'] == CTX:
                        break
                except (OSError, urllib.error.HTTPError):
                    pass
                time.sleep(1)
            else:
                raise RuntimeError(f'server not ready; see {log_path}')
            text = log_path.read_text()
            layers = re.search(r'offloaded (\d+)/(\d+) layers to GPU', text)
            if not layers or layers[1] != layers[2] or 'CUDA0 model buffer size' not in text:
                raise RuntimeError(f'full CUDA offload not confirmed; see {log_path}')
            with (dest / 'results.jsonl').open('w') as results:
                for case in cases:
                    results.write(json.dumps(pi_case(case, model, dest, env, fixture)) + '\n')
                    results.flush()
        finally:
            if server.poll() is None:
                server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
    decode = [(float(ms), int(tokens)) for ms, tokens in re.findall(r'\|\s+eval time =\s*([\d.]+) ms /\s*(\d+) tokens', log_path.read_text())]
    result_rows = [json.loads(line) for line in (dest / 'results.jsonl').read_text().splitlines()]
    groups = {group: [sum(r['pass'] for r in result_rows if r['group'] == group), sum(r['group'] == group for r in result_rows)] for group in dict.fromkeys(r['group'] for r in result_rows)}
    valid = [r for r in result_rows if not r['errors']]
    visible = [r['first_text_s'] for r in valid if r['first_text_s'] is not None]
    return {'scores': groups, 'median_first_text_s': statistics.median(visible) if visible else None, 'median_elapsed_s': statistics.median(r['elapsed_s'] for r in valid) if valid else None, 'decode_tokens_per_s': round(1000 * sum(n for _, n in decode) / sum(ms for ms, _ in decode), 2) if decode else None, 'errors': sum(bool(r['errors']) for r in result_rows), 'gpu_layers': int(layers[1])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=VARIANTS, action='append')
    parser.add_argument('--smoke', action='store_true')
    opt = parser.parse_args()
    models = opt.model or list(VARIANTS)
    out = ROOT / datetime.now(timezone.utc).strftime('run-%Y%m%d-%H%M%S-%f')
    out.mkdir()
    print(f'Artifacts: {out}', flush=True)
    config = out / 'pi-agent'
    config.mkdir()
    fixture = out / 'fixture'
    fixture.mkdir()
    (fixture / 'token.txt').write_text('orbit-75319-fir\n')
    (fixture / 'quantities.txt').write_text('324\n917\n552\n')
    (fixture / 'adjustment.txt').write_text('279\n')
    entries = [{'id': model, 'contextWindow': CTX, 'maxTokens': MAX_OUTPUT, 'input': ['text']} for model in models]
    provider = {'baseUrl': URL + '/v1', 'apiKey': 'local', 'api': 'openai-completions', 'compat': {'supportsDeveloperRole': False, 'supportsStore': False, 'maxTokensField': 'max_tokens'}, 'models': entries}
    (config / 'models.json').write_text(json.dumps({'providers': {'inkling-bench': provider}}, indent=2) + '\n')
    env = {**os.environ, 'PI_CODING_AGENT_DIR': str(config), 'PI_TELEMETRY': '0'}
    cases = list(make_cases())
    if opt.smoke:
        cases = [cases[0], cases[-2]]
    summaries = {}
    for model in models:
        try:
            summaries[model] = run_model(model, out, env, fixture, cases)
        except RuntimeError as error:
            summaries[model] = {'error': str(error)}
        print(f'{model}: {json.dumps(summaries[model])}', flush=True)
        (out / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
    if any('error' in s or s['errors'] for s in summaries.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
