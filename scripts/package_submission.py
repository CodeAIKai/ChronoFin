"""Export the complete project as an expanded, verified directory."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from verify_clean_checkout import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'ChronoFin-export')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise SystemExit('Output must be outside the source tree')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise SystemExit('Output must be a new or empty directory')
    clean = json.loads((ROOT / 'audit/clean_checkout_verification.json').read_text())
    original = fingerprint(ROOT)
    if not clean['pass'] or clean['source_fingerprint'] != original:
        raise SystemExit('Run verify_clean_checkout.py on the current source first')

    def ignore(path, names):
        relative = Path(path).relative_to(ROOT)
        return [n for n in names if n in {
            '.git', '.venv', '__pycache__', '.pytest_cache', '.env'
        } or n.endswith('.egg-info')
            or (n.startswith('.env.') and n != '.env.example')
            or (relative == Path('data') and n == 'cache')]

    shutil.copytree(ROOT, output, ignore=ignore, dirs_exist_ok=True)
    if fingerprint(output) != original:
        raise RuntimeError('Exported source fingerprint mismatch')
    secret_pattern = re.compile(rb'(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})')
    findings = []
    for p in output.rglob('*'):
        if not p.is_file():
            continue
        if p.name == '.env' or p.suffix in {'.pem', '.key', '.p12', '.pfx', '.pyc'}:
            findings.append(str(p.relative_to(output)))
        elif p.suffix in {'.py', '.md', '.json', '.jsonl', '.csv', '.log', '.txt', '.html', '.toml'} or p.name.startswith('.env'):
            if secret_pattern.search(p.read_bytes()):
                findings.append(str(p.relative_to(output)))
    if findings:
        raise RuntimeError('Private material detected in: ' + ', '.join(findings))
    env = {k: v for k, v in os.environ.items() if k not in {
        'HY3_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN', 'GITHUB_TOKEN', 'PYTHONPATH'
    }}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    run = subprocess.run([sys.executable, 'scripts/verify_artifacts.py'],
                         cwd=output, env=env, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=90)
    if run.returncode:
        raise SystemExit('Exported material failed verification:\n' + run.stdout)
    print(json.dumps({'output': str(output), 'format': 'expanded_directory',
                      'files': sum(p.is_file() for p in output.rglob('*')),
                      'source_fingerprint': original['sha256'],
                      'artifact_integrity_pass': True}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
