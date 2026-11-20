#!/usr/bin/env python3
"""Fail-closed preflight, bound to the immutable scientific plan."""
import collections
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import numpy as np
import uproot
from campaign import HERE, frozen, now, output_events, save, generator_environment, load, sha
from core import charge_table, decode, certificates
from analysis import th1, reference_percentiles, masks, contributions


def run():
    p=frozen();checks=[]
    smoke=load(HERE/'RUNTIME_SMOKE_PASS.json')
    assert smoke['status']=='PASS' and smoke.get('execution_node') is True,'actual execution-node canary required'
    for name,digest in smoke['tested_code'].items():assert sha(HERE/name)==digest,'changed after execute-node canary'
    for name,digest in load(HERE/'VENDOR_MANIFEST.json').items():assert sha(HERE/'vendor'/name)==digest,'changed vendored package'
    checks.append('actual Condor execution-node runtime canary, frozen shared Python and vendored packages')
    subprocess.run([sys.executable,'-m','unittest','-v','test_core','test_statistics','test_mb_config','test_reuse_cache'],cwd=str(HERE),check=True)
    checks.append('identity, certificates, ordering, unknowns, duplicates, origin split, angles, ties')
    charge=charge_table(HERE/'idt.dt')
    for ident,q in [(12,-1),(-12,1),(120,1),(-120,-1),(130,1),(1120,1),(1220,0),(140,0),(-140,0)]:
        assert abs(charge(ident)-q)<1e-5,(ident,charge(ident))
    checks.append('charge from original generator table, not ID sign')
    for system,t in p['templates'].items():
        env=generator_environment(t,HERE/'preflight',{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
        libraries=subprocess.check_output(['/usr/bin/ldd',str(Path(t['install'])/'bin/Xepos')],env=env,universal_newlines=True)
        assert 'not found' not in libraries,'missing library in minimal batch environment: '+system
    checks.append('both generator binaries resolve libraries in a minimal non-login environment')
    observations={}
    examples=[]
    for system in ('PbPb','OO'):
        r=dict(next(r for r in p['records'] if r['system']==system and r['mode']=='generator_v5'))
        events=list(output_events(r['root'],r,charge));assert len(events)==r['expected']
        pairs=sum(sum(x['final'] is not None for x in e['pairs']) for e in events)
        observations[system]=dict(events=len(events),final_pairs=pairs,audit=r.get('audit',{}))
        examples+=events
    assert sum(v['final_pairs'] for v in observations.values())>0,'preflight files contain no linked final pairs'
    contributions(examples)
    checks.append('complete real ROOT files, both systems, certified initial/final links')
    rng=np.random.RandomState(123);freq=np.bincount(rng.randint(0,100,15000));values=rng.randint(0,100,5000)
    c=reference_percentiles(values,['independent_validation_'+str(i) for i in range(5000)],freq)
    assert abs(masks(c)[1].mean()-.1)<.03
    c2=reference_percentiles([0]*10000,['tie_'+str(i) for i in range(10000)],[15000])
    assert abs(masks(c2)[1].mean()-.1)<.02
    checks.append('independent reference percentiles, fixed-key ties, zero-multiplicity degeneracy')
    t=HERE/'preflight';t.mkdir(exist_ok=True);path=t/'roundtrip.root'
    a=np.arange(30,dtype=float)+1.;variance=a*2
    with uproot.recreate(str(path)) as f:
        f['traditional/h']=th1(a,variance)
        f['traditional/cov']=(np.diag(variance),np.arange(31,dtype=float),np.arange(31,dtype=float))
        f.mktree('identity',{'file_index':'int64','event':'int64','pair':'int64','valid':'bool'})
        f['identity'].extend(dict(file_index=np.array([0,1]),event=np.array([1,1]),pair=np.array([1,1]),valid=np.array([True,True])))
    with uproot.open(str(path)) as f:
        assert f['traditional/h'].classname=='TH1D'
        assert np.array_equal(f['traditional/h'].values(),a)
        assert np.array_equal(f['traditional/h'].variances(),variance)
        assert f['traditional/cov'].classname=='TH2D' and f['identity'].num_entries==2
    checks.append('traditional TH1D/TH2D, bin errors and TTree independent reopen')
    forbidden=r'(?im)^\s*(request_cpus|request_memory|request_disk|requirements|rank|concurrencylimits|machine|should_transfer_files)\s*='
    for path in HERE.glob('*.sub'):
        assert not re.search(forbidden,path.read_text()),'authored constraint '+str(path)
    checks.append('minimal Condor files; no authored resource or node constraints')
    save(HERE/'PREFLIGHT_PASS.json',dict(status='PASS',signature=p['signature'],utc=now(),checks=checks,
                                      real_samples=observations,MB_pilot_must_pass_before_reference=True))
    print('PREFLIGHT_PASS',json.dumps(observations),flush=True)


if __name__=='__main__':run()
