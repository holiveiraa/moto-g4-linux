#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate a GitHub Wiki locally from canonical docs; never uses Git/network."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import quote,urlsplit

PROJECT=Path(__file__).resolve().parents[1]


def export(repository,output,branch='main',project=PROJECT):
    repository=repository.rstrip('/')
    if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('Use the canonical https://github.com/OWNER/REPOSITORY URL.')
    if not branch or any(c in branch for c in '\r\n?#'):
        raise ValueError('Invalid branch')
    project=Path(project).resolve();output=Path(output).resolve()
    if output==project or project.is_relative_to(output):raise ValueError('Use a dedicated output directory.')
    mapping=json.loads((project/'wiki/pages.json').read_text(encoding='utf-8'))
    reverse={(project/source).resolve():page for page,source in mapping.items()}
    raw='https://raw.githubusercontent.com/'+urlsplit(repository).path.strip('/')+'/'+quote(branch,safe='/')
    def convert(source,text):
        def target_url(target,is_image=False):
            if urlsplit(target).scheme or target.startswith('#'):return target
            relative,separator,anchor=target.partition('#')
            resolved=(source.parent/relative).resolve()
            if not resolved.is_relative_to(project):raise ValueError('Link escapes project: '+relative)
            if not resolved.exists():raise ValueError('Missing link: '+relative)
            suffix=('#'+anchor) if separator else ''
            if is_image:
                url=raw+'/'+resolved.relative_to(project).as_posix()
            elif resolved in reverse:
                url=repository+'/wiki/'+quote(reverse[resolved])
            else:
                url=repository+'/blob/'+quote(branch,safe='/')+'/'+resolved.relative_to(project).as_posix()
            return url+suffix
        def link(match):
            prefix,target=match.group(1),match.group(2)
            return prefix+target_url(target,prefix.startswith('!'))+')'
        def html_image(match):
            return match.group(1)+target_url(match.group(2),True)+match.group(3)
        def prose(block):
            block=re.sub(r'(!?\[[^\]]*\]\()([^\s)]+)\)',link,block)
            return re.sub(r'(<img\b[^>]*\bsrc=")([^"]+)(")',html_image,block)
        # Protect shell snippets with parentheses/relative paths from rewriting.
        blocks=re.split(r'(```.*?```)',text,flags=re.S)
        return ''.join(block if block.startswith('```') else prose(block) for block in blocks)
    prepared={}
    for page,relative in mapping.items():
        if not re.fullmatch(r'[A-Za-z0-9-]+',page):raise ValueError('Invalid wiki page name')
        source=(project/relative).resolve()
        if not source.is_relative_to(project):raise ValueError('Source escapes project')
        prepared[page+'.md']=convert(source,source.read_text(encoding='utf-8'))
    for name in ('_Sidebar.md','_Footer.md'):
        prepared[name]=(project/'wiki'/name).read_text(encoding='utf-8').replace('{{REPOSITORY_URL}}',repository)
    output.mkdir(parents=True,exist_ok=True)
    for name,text in prepared.items():(output/name).write_bytes(text.encode('utf-8'))
    return len(prepared)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository-url',required=True)
    parser.add_argument('--output',type=Path,default=PROJECT/'out/wiki')
    parser.add_argument('--branch',default='main')
    args=parser.parse_args()
    print(f'Generated {export(args.repository_url,args.output,args.branch)} wiki files locally in {args.output}. Nothing published.')


if __name__=='__main__':main()
