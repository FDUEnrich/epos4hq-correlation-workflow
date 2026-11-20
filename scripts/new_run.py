#!/usr/bin/env python3
"""Create an independent campaign directory. Never change an old campaign."""
import argparse
import os
from pathlib import Path
import shlex
import shutil


def create(destination):
    repo = Path(__file__).resolve().parents[1]
    target = Path(destination).expanduser().resolve()
    if target.exists():
        raise FileExistsError('Choose a new directory; existing runs are immutable: '+str(target))
    target.mkdir(parents=True)
    for source in (repo/'workflow').iterdir():
        if source.is_file() and source.suffix in ('.py', '.sh', '.txt', '.dt'):
            shutil.copy2(str(source), str(target/source.name))
    (target/'launch.sh').chmod(0o755)
    settings={k:v for k,v in os.environ.items() if k in (
        'EPOS_BASE','EPOS_TAGGED_SOURCE','EPOS_OO_PRODUCTION','EPOS_PBPB_PRODUCTION',
        'EPOS_PYTHONHOME','EPOS_VENDOR_SOURCE','EPOS_REUSE_FROM')}
    (target/'site.env').write_text(''.join('export '+k+'='+shlex.quote(v)+'\n'
                                        for k,v in sorted(settings.items())))
    print('Created independent workflow:', target)
    print('No jobs were submitted. Set EPOS_BASE, stage dependencies, prepare and test before submitting.')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    create(parser.parse_args().destination)
