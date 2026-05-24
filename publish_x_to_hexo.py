import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path('/Users/linf/Documents/code/hexo-blog')
VENV_PYTHON = ROOT / 'x2md' / 'bin' / 'python'
X2MD = ROOT / 'x2md.py'
DEPLOY = ROOT / 'deploy.sh'
BLOG_URL = 'https://dimflip.xyz'


def run(cmd):
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    return result


def main():
    parser = argparse.ArgumentParser(description='Convert X post to Hexo markdown and optionally deploy')
    parser.add_argument('--url', required=True, help='X/Twitter status URL')
    parser.add_argument('--category', default='web3', help='Hexo category')
    parser.add_argument('--mode', choices=['draft', 'publish'], default='publish', help='draft=only generate md, publish=generate and deploy')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing markdown')
    parser.add_argument('--skip-if-exists', action='store_true', help='Skip rewrite when markdown already exists')
    parser.add_argument('--authorized-repost', action='store_true', help='Confirm you have permission to save long-form source text')
    parser.add_argument('--clean', action='store_true', help='Run hexo clean before generate (publish mode defaults to clean)')
    args = parser.parse_args()

    python_bin = str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))

    x2md_cmd = [
        python_bin,
        str(X2MD),
        '--url', args.url,
        '--category', args.category,
        '--json',
    ]
    if args.overwrite:
        x2md_cmd.append('--overwrite')
    if args.skip_if_exists:
        x2md_cmd.append('--skip-if-exists')
    if args.authorized_repost:
        x2md_cmd.append('--authorized-repost')

    x2md_res = run(x2md_cmd)
    if x2md_res.returncode != 0:
        print(json.dumps({
            'ok': False,
            'stage': 'x2md',
            'stdout': x2md_res.stdout,
            'stderr': x2md_res.stderr,
        }, ensure_ascii=False))
        sys.exit(1)

    try:
        x2md_json = json.loads(x2md_res.stdout.strip())
    except Exception:
        print(json.dumps({
            'ok': False,
            'stage': 'x2md_parse',
            'stdout': x2md_res.stdout,
            'stderr': x2md_res.stderr,
        }, ensure_ascii=False))
        sys.exit(1)

    result = {
        'ok': True,
        'mode': args.mode,
        'x2md': x2md_json,
        'deploy': {
            'ran': False,
            'ok': None,
            'stdout': None,
            'stderr': None,
        },
        'blog_url': BLOG_URL,
    }

    if args.mode == 'publish':
        deploy_cmd = [str(DEPLOY), '--no-open', '--clean']
        if args.clean and '--clean' not in deploy_cmd:
            deploy_cmd.append('--clean')
        deploy_res = run(deploy_cmd)
        result['deploy'] = {
            'ran': True,
            'ok': deploy_res.returncode == 0,
            'stdout': deploy_res.stdout,
            'stderr': deploy_res.stderr,
        }
        result['ok'] = result['ok'] and deploy_res.returncode == 0
        if deploy_res.returncode != 0:
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(1)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
