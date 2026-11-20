"""An actual Condor-node canary, BEFORE permitting the production DAG."""
import os
import socket
import sys
import subprocess
from pathlib import Path
import numpy
import uproot
import awkward
from campaign import HERE, load, save, sha, now, output_events, generator_environment
from core import charge_table


def main():
    p=load(HERE/'PLAN.json');charge=charge_table(HERE/'idt.dt');observations={}
    for system,t in p['templates'].items():
        env=generator_environment(t,HERE/'preflight',{'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C'})
        out=subprocess.check_output(['/usr/bin/ldd',str(Path(t['install'])/'bin/Xepos')],env=env,universal_newlines=True)
        assert 'not found' not in out,system+': '+out
        r=dict(next(r for r in p['records'] if r['system']==system and r['mode']=='generator_v5'))
        events=list(output_events(r['root'],r,charge))
        observations[system]=dict(events=len(events),final_pairs=sum(x['final'] is not None for e in events for x in e['pairs']))
    tested={f.name:sha(f) for f in HERE.glob('*.py')};tested['launch.sh']=sha(HERE/'launch.sh')
    save(HERE/'RUNTIME_SMOKE_PASS.json',dict(status='PASS',utc=now(),host=socket.gethostname(),python=sys.executable,
                                          execution_node=bool(os.environ.get('_CONDOR_JOB_AD')),
                                          versions=dict(numpy=numpy.__version__,uproot=uproot.__version__,awkward=awkward.__version__),
                                          real_samples=observations,tested_code=tested))
    print('RUNTIME_PROBE_PASS',socket.gethostname(),sys.executable,observations,flush=True)


if __name__=='__main__':main()
