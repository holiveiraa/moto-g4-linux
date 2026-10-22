#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Copy audited public Git candidates into a fresh local tree; never publish."""
import argparse
import importlib.util
from pathlib import Path
import shutil

PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('source_check',Path(__file__).with_name('check-repository.py'))
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=PROJECT/'out/public-source')
    args=parser.parse_args()
    target=args.output.resolve()
    if target.exists():raise SystemExit('Output already exists; choose a new empty destination.')
    if target==PROJECT or PROJECT.is_relative_to(target):raise SystemExit('Use a dedicated export directory.')
    if check.check():raise SystemExit('Repository checks failed; nothing exported.')
    files=check.candidates()
    target.mkdir(parents=True)
    for name in files:
        source=PROJECT/name
        if source.is_symlink():raise SystemExit('Review symlink before export: '+name)
        if source.is_file():
            output=target/name;output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,output)
    print(f'Exported {len(files)} audited files to {target}; no Git history, private state or publishing.')


if __name__=='__main__':main()
