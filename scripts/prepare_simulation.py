#!/usr/bin/env python3
"""Render an isolated PbPb/OO production batch; does NOT submit jobs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil

REPO = Path(__file__).resolve().parents[1]


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def production_options(text, events):
    text,n=re.subn(r'(?m)^\s*set\s+nfull\s+\d+[^\n]*$', 'set nfull '+str(events),text)
    if n!=1:raise ValueError('ambiguous nfull')
    # The worker appends the unique seed pair for each job. No physics edits.
    return re.sub(r'(?m)^\s*set\s+seed[ji]\s+[^\n]*$', '',text)


def submit_text(batch, output, jobs, system):
    return '\n'.join([
        'universe = vanilla', 'notification = Never',
        'executable = '+str(batch/'launch.sh'),
        'arguments = $(ClusterId) $(Process)', 'initialdir = '+str(batch),
        'output = '+str(output/'condor/job_$(ClusterId)_$(Process).out'),
        'error = '+str(output/'condor/job_$(ClusterId)_$(Process).err'),
        'log = '+str(output/'condor/cluster_$(ClusterId).log'),
        '+JobBatchName = "'+system+'_v5_production"',
        'on_exit_hold = (ExitBySignal =?= True) || (ExitCode =!= 0)',
        'queue '+str(jobs), ''])


def prepare(args):
    output=Path(args.destination).expanduser().resolve()
    source=Path(args.source).expanduser().resolve()
    install=Path(args.install).expanduser().resolve()
    root=Path(args.root).expanduser().resolve()
    if args.jobs<=0 or args.events<=0 or args.seed_stride<=0:
        raise ValueError('jobs, events and seed_stride must be positive')
    last=args.seed_base+(args.jobs-1)*args.seed_stride
    if not (0<args.seed_base<=last<1000000000):raise ValueError('seed range outside EPOS contract')
    if not (0<args.seedi<1000000000):raise ValueError('invalid seedi')
    for path in (source/'srcext/HQ/hq.i',install/'bin/Xepos',root):
        if not path.is_file():raise FileNotFoundError(str(path))
    if output.exists():raise FileExistsError('Choose a new batch directory: '+str(output))
    # The original generator macro uses C-string paths; reject ambiguous characters.
    for path in (output,source,install,root):
        if any(c in str(path) for c in ('\n','\r','"','\\',' ')):
            raise ValueError('Use whitespace-free farm paths: '+str(path))
    batch=output/'_batch';batch.mkdir(parents=True)
    for folder in ('condor','done','jobs','check/'+args.system):(output/folder).mkdir(parents=True)
    for filename in ('worker.py','ValidateProduction.C','CompareOriginSubtraction.C','PilotTrees.h','lineage_records.py'):
        shutil.copy2(str(REPO/'simulation'/filename),str(batch/filename))
    template=REPO/'configs/historical'/(args.system+'.optns')
    (batch/'production.optns').write_text(production_options(template.read_text(),args.events))
    config=dict(system=args.system,source=str(source),install=str(install),root=str(root),
                run_id=output.name,jobs=args.jobs,events_per_job=args.events,
                seed_base=args.seed_base,seed_stride=args.seed_stride,seedi=args.seedi,
                binary_sha256=digest(install/'bin/Xepos'),hq_sha256=digest(source/'srcext/HQ/hq.i'),
                original_optns_sha256=digest(template))
    (batch/'batch_config.json').write_text(json.dumps(config,indent=2,sort_keys=True)+'\n')
    pythonhome=Path(args.pythonhome).expanduser().resolve()
    values={'EPOS_PYTHONHOME':str(pythonhome),'EPOS_ROOTSYS':str(root.parent.parent),
            'EPOS_HEPMC_LIB':str(Path(args.hepmc_lib).expanduser().resolve()),
            'EPOS_FASTJET_LIB':str(Path(args.fastjet_lib).expanduser().resolve())}
    (batch/'runtime.env').write_text('\n'.join('export '+k+'='+shlex.quote(v) for k,v in sorted(values.items()))+'\n')
    launch='''#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
source ./runtime.env
export LC_ALL=C LANG=C PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONHOME="$EPOS_PYTHONHOME"
export ROOTSYS="$EPOS_ROOTSYS"
export PATH="$ROOTSYS/bin:$PATH"
export LD_LIBRARY_PATH="$PYTHONHOME/lib64:$ROOTSYS/lib:$EPOS_HEPMC_LIB:$EPOS_FASTJET_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$PYTHONHOME/bin/python3.6" worker.py "$@"
'''
    (batch/'launch.sh').write_text(launch);(batch/'launch.sh').chmod(0o755)
    (batch/'simulation.sub').write_text(submit_text(batch,output,args.jobs,args.system))
    members=sorted(p for p in batch.iterdir() if p.is_file())
    (batch/'FROZEN_SHA256SUMS').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in members))
    print('Prepared only; no jobs submitted:',batch/'simulation.sub')
    return batch


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--system',choices=('PbPb','OO'),required=True)
    for name in ('destination','source','install','root','pythonhome','hepmc-lib','fastjet-lib'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--jobs',type=int,required=True)
    p.add_argument('--events',type=int,required=True)
    p.add_argument('--seed-base',type=int,required=True)
    p.add_argument('--seed-stride',type=int,default=7919)
    p.add_argument('--seedi',type=int,default=222222222)
    prepare(p.parse_args())
