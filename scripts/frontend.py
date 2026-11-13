"""Run approved frontend tools using the project-local Node/npm, without PATH edits."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT/'data/local/toolchains/node-v26.13.1-win-x64/node.exe'
NPM = NODE.parent/'node_modules/npm/bin/npm-cli.js'
LOCAL = ROOT/'data/local/frontend-stage1-20261112'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('dev','build','test','preview','dependencies'))
    command = parser.parse_args().command
    if not NODE.is_file() or not NPM.is_file():
        parser.error('The approved project-local Node.js 26.13.1 toolchain is missing; no global fallback is used.')
    LOCAL.mkdir(parents=True,exist_ok=True)
    for name in ('npm-user.conf','npm-global.conf'):
        path = LOCAL/name
        if not path.exists():
            with path.open('x',encoding='utf-8') as stream:stream.write('')
    args = [str(NODE),str(NPM),'--prefix',str(ROOT/'frontend'),
            '--cache='+str(LOCAL/'npm-cache'),'--userconfig='+str(LOCAL/'npm-user.conf'),
            '--globalconfig='+str(LOCAL/'npm-global.conf'),'--update-notifier=false']
    args.extend(['ls','--all','--offline'] if command=='dependencies' else ['run',command])
    try:
        return subprocess.call(args,cwd=ROOT)
    except KeyboardInterrupt:
        return 130


if __name__=='__main__':
    raise SystemExit(main())
