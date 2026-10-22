#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Inspect Git's candidate file set without staging or publishing anything."""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote,urlsplit
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN={'.private','.local-tools','out','build','sources','.venv','__pycache__'}
BAD_SUFFIX={'.img','.apk','.msi','.key','.pem','.state','.wav','.xwd','.dtb','.dtbo','.bin','.zip','.tgz'}
PATTERNS={
 'private key':re.compile(r'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED|) ?PRIVATE KEY-----'),
 'live-looking Groq token':re.compile(r'gsk_[A-Za-z0-9]{24,}'),
 'public maintenance key':re.compile(r'ssh-ed25519\s+[A-Za-z0-9+/=]{40,}'),
 'personal Windows path':re.compile(r'(?:C:[\\/]|/mnt/c/)[Uu]sers[\\/]'),
 'real tailnet hostname':re.compile(r'\btail[a-f0-9]{6}\.ts\.net\b',re.I),
}


def candidates():
    result=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard','-z'],
                          cwd=ROOT,capture_output=True,check=True)
    return sorted(set(value.decode('utf-8') for value in result.stdout.split(b'\0') if value))


def check():
    errors=[];files=candidates()
    try:
        wiki_pages=json.loads((ROOT/'wiki/pages.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):
        wiki_pages={}
        errors.append('Cannot validate Wiki navigation: page map missing or invalid')
    wiki_templates={'{{REPOSITORY_URL}}','{{REPOSITORY_URL}}/wiki'}
    wiki_templates.update('{{REPOSITORY_URL}}/wiki/'+page for page in wiki_pages)
    for name in files:
        path=ROOT/name
        if not path.is_file():continue
        if set(Path(name).parts)&FORBIDDEN or path.suffix.lower() in BAD_SUFFIX:
            errors.append(name+': private/generated file selected for publication');continue
        if path.stat().st_size>2*1024*1024:errors.append(name+': unexpectedly large source asset')
        if path.suffix.lower()=='.png':continue
        try:text=path.read_text(encoding='utf-8')
        except UnicodeError:errors.append(name+': unexpected binary/non-UTF8 file');continue
        for label,pattern in PATTERNS.items():
            if name==Path(__file__).relative_to(ROOT).as_posix():continue
            for match in pattern.finditer(text):
                errors.append(f'{name}:{text.count(chr(10),0,match.start())+1}: {label}; value not printed')
        if path.suffix=='.py':
            try:ast.parse(text,filename=name)
            except SyntaxError as exc:errors.append(f'{name}:{exc.lineno}: Python syntax error')
        if path.suffix=='.json':
            try:json.loads(text)
            except ValueError:errors.append(name+': invalid JSON')
        if path.suffix=='.svg':
            try:ET.fromstring(text)
            except ET.ParseError:errors.append(name+': invalid SVG')
        if path.suffix=='.sh' or name.startswith(('initramfs/','native/')) and text.startswith('#!'):
            if b'\r' in path.read_bytes():errors.append(name+': executable must use LF')
        if path.suffix=='.md':
            # Ignore fenced examples; check real relative docs/assets links.
            prose=re.sub(r'```.*?```','',text,flags=re.S)
            links=re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)',prose)
            links+=re.findall(r'<img[^>]+src="([^"]+)"',prose)
            for link in links:
                link=link.strip('<>')
                if name in ('wiki/_Sidebar.md','wiki/_Footer.md') and link in wiki_templates:continue
                if urlsplit(link).scheme or link.startswith('#'):continue
                target=(path.parent/unquote(link.split('#')[0])).resolve()
                if not target.is_relative_to(ROOT) or not target.exists():
                    errors.append(name+': broken/outside local link '+link)
    required=('README.md','README.pt-BR.md','AGENTS.md','LICENSE','CREDITS.md','NOTICE.md',
              'SECURITY.md','CONTRIBUTING.md','sources.lock.json','wiki/pages.json')
    for name in required:
        if name not in files:errors.append('Missing public candidate: '+name)
    for probe in ('.private/probe','.local-tools/probe','out/probe.img','sources/probe','build/probe'):
        if subprocess.run(['git','check-ignore','-q',probe],cwd=ROOT).returncode:
            errors.append('Ignore rule missing: '+probe)
    if errors:
        print('\n'.join(errors),file=sys.stderr);return 1
    print(f'PASS: {len(files)} public candidates; docs links, syntax, source format and targeted privacy checks.')
    print('No files staged, committed or published. Review remains necessary before release.')
    return 0


if __name__=='__main__':raise SystemExit(check())
