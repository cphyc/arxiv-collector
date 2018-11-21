#!/usr/bin/env python
from __future__ import print_function

import collections
from functools import partial
import io
import os
import re
import subprocess
import sys
import tarfile


__version__ = '0.1.1'


def consume(iterator):
    collections.deque(iterator, maxlen=0)


def target(fname):
    while os.path.islink(fname):
        fname = os.readlink(fname)
    return fname


strip_comment = partial(re.compile(r'(^|[^\\])%.*').sub, r'\1%')


def collect(out_tar, base_name='main', packages=('biblatex',),
            strip_comments=True):
    # Use latexmk to:
    #  - make sure we have a good main.bbl file
    #  - figure out which files we actually use (to not include unused figures)
    #  - keep track of which files we use from certain packages
    print("Building {}...".format(base_name))

    proc = subprocess.Popen(
        ['latexmk', '-silent', '-pdf', '-deps', base_name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1)

    def next_line():
        return proc.stdout.readline().decode()

    def read_until(check):
        while True:
            line = next_line()
            if line == '':
                raise ValueError("Unexpected EOF")
            elif check(line):
                return
            yield line

    pat = '#===Dependents(, and related info,)? for {}:\n'.format(base_name)
    consume(read_until(re.compile(pat).match))
    assert next_line().strip() == '{}.pdf :\\'.format(base_name)

    pkg_re = re.compile('/' + '|'.join(re.escape(p) for p in packages) + '/')

    end_line = '#===End dependents for {}:\n'.format(base_name)
    for line in read_until(end_line.__eq__):
        dep = line.strip()
        if dep.endswith('\\'):
            dep = dep[:-1]

        if dep.startswith('/'):
            if pkg_re.search(dep):
                out_tar.add(target(dep), arcname=os.path.basename(dep))
        elif dep.endswith('.tex') and strip_comments:
            with io.open(dep) as f, io.BytesIO() as g:
                info = tarfile.TarInfo(name=dep)
                for line in f:
                    g.write(strip_comment(line).encode('utf-8'))
                info.size = g.tell()
                g.seek(0)
                out_tar.addfile(tarinfo=info, fileobj=g)
        elif dep.endswith('.eps'):
            # arxiv doesn't like epstopdf in subdirectories
            base = dep[:-4]
            pdf = base + '-eps-converted-to.pdf'
            assert os.path.exists(pdf)
            out_tar.add(target(pdf), arcname=base + '.pdf')
        elif dep.endswith('-eps-converted-to.pdf'):
            # old versions of latexmk output both the converted and the not
            pass
        elif dep.endswith('.bib'):
            pass
        else:
            out_tar.add(target(dep), arcname=dep)

    consume(iter(proc.stdout.read, b''))
    proc.wait()

    if proc.returncode:
        print("Build failed! Run   latexmk -pdf {}   to see why."
              .format(base_name))
        subprocess.check_call(['latexmk', '-C', base_name])
        sys.exit(proc.returncode)

    out_tar.add('{}.bbl'.format(base_name))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('base_name', nargs='?')
    parser.add_argument('--include-package', '-p',
                        action='append', dest='packages', default=['biblatex'])
    parser.add_argument('--skip-biblatex', action='store_true')
    parser.add_argument('--dest', default='arxiv.tar.gz')
    g = parser.add_mutually_exclusive_group()
    g.add_argument('--strip-comments', action='store_true', default=True,
                   help="Strip comments from all .tex files (by default).")
    g.add_argument('--no-strip-comments', action='store_false',
                   dest='strip_comments')
    parser.add_argument('--version', action='version',
                        version='%(prog)s {}'.format(__version__))
    args = parser.parse_args()

    if not args.base_name:
        from glob import glob
        cands = [c[:-4] for c in glob('*.tex')]
        if len(cands) > 1:
            cands = list(set(cands) & {'main', 'paper'})
        if len(cands) == 1:
            args.base_name = cands[0]
        else:
            parser.error("Can't guess your filename; pass BASE_NAME.")

    if args.base_name.endswith('.tex'):
        args.base_name = args.base_name[:-4]
    if '.' in args.base_name:
        parser.error("BASE_NAME ({!r}) shouldn't contain '.'"
                     .format(args.base_name))
    if '/' in args.base_name:
        parser.error("cd into the directory first")

    if args.skip_biblatex:
        args.packages.remove('biblatex')

    with tarfile.open(args.dest, mode='w:gz') as t:
        collect(t, base_name=args.base_name, packages=args.packages,
                strip_comments=args.strip_comments)
    print("Output in {}".format(args.dest))


if __name__ == '__main__':
    main()