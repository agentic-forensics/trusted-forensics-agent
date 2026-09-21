#!/usr/bin/env python3
"""Four-step offline presentation, with a tampered copy (companion D.4)."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tfa.bundle import create_bundle
from tfa.report import analyse
from tfa.scenarios import build_cross_provider_episode
from tfa.synth import build_episode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pause', action='store_true', help='wait for Enter before each stage')
    parser.add_argument('--output', type=Path, help='new output directory (must not exist)')
    args = parser.parse_args()
    if args.output:
        folder = args.output.resolve()
        folder.mkdir(parents=True, exist_ok=False)
    else:
        base = ROOT / 'results'
        base.mkdir(exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='demo-', dir=str(base)))
    path = folder / 'captured.bundle.json'
    path.write_text(json.dumps(create_bundle(analyse(build_episode())), indent=2, sort_keys=True) + '\n', encoding='utf-8')

    def run(*options, expected=0):
        command = [sys.executable, '-B', '-m', 'tfa', *map(str, options)]
        print('$ ' + shlex.join(['python', '-m', 'tfa', *map(str, options)]), flush=True)
        result = subprocess.run(command, cwd=str(ROOT), check=False)
        if result.returncode != expected:
            raise SystemExit(f'Unexpected exit {result.returncode}; expected {expected}')

    print('Synthetic case. Development witness with a public demo key.\n', flush=True)
    for step in range(1, 5):
        if args.pause:
            input(f'Press Enter for step {step}...')
        if step == 4:
            final = folder / 'mailbox.bundle.json'
            run('--from-bundle', path, '--bundle', final, '--demo-step', step)
            path = final
        else:
            run('--from-bundle', path, '--demo-step', step)
        if step == 3:
            print('\nCROSS-PROVIDER CONTRAST - illustrative records, not the Mexico case evidence', flush=True)
            cross = analyse(build_cross_provider_episode())
            for answer in cross.answers:
                if answer.qid in ('Q2', 'Q6'):
                    print(f'{answer.qid}: {answer.classification.value}', flush=True)
                    print(f'  GAP: {answer.gap.party} | {answer.gap.data_class}', flush=True)
        if step == 4:
            run('--verify-bundle', path)
            run('--reproduce', path)
            changed = json.loads(path.read_text(encoding='utf-8'))
            changed['payload']['report'] += '\nAltered conclusion for the tamper demonstration.\n'
            tampered = folder / 'tampered-report.bundle.json'
            tampered.write_text(json.dumps(changed, indent=2) + '\n', encoding='utf-8')
            print('\nChange a COPY of the report; retain the original seal:', flush=True)
            run('--verify-bundle', tampered, expected=1)
            print('Expected failure detected. Original bundle retained at ' + str(path), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
