"""Independent MB calibration; never rank the charm-selected sample."""
import math
import numpy as np
from core import CENTRALITIES, uniform
from campaign import HERE, frozen, load, now, save, sha
from io_utils import read_events


def reference_percentiles(values,keys,counts):
    freq=np.asarray(counts,dtype=float);n=freq.sum()
    assert n>0
    idx=np.asarray(values,dtype=int)
    above=np.cumsum(freq[::-1])[::-1]-freq
    safe=np.minimum(idx,len(freq)-1)
    result=(above[safe]+np.asarray([uniform(k) for k in keys])*freq[safe])/n*100
    result[idx>=len(freq)]=0.
    return result


def masks(c):
    return [np.ones(len(c),dtype=bool), (c>=0)&(c<10), (c>=20)&(c<50), (c>=60)&(c<=100)]


def calibrate():
    p=frozen();systems={}
    for system in ('PbPb','OO'):
        events=[];seen=set()
        for job in p['mb_jobs']:
            if job['system']!=system:continue
            base=HERE/'mb'/job['key'];m=load(base/'COMPLETE.json')
            assert m['signature']==p['signature'] and sha(base/'events.jsonl.gz')==m['events_sha']
            for e in read_events(base/'events.jsonl.gz'):
                assert e['key'] not in seen and e['split']==job['split'];seen.add(e['key']);events.append(e)
        a=[e for e in events if e['split']=='calibration'];v=[e for e in events if e['split']=='validation']
        assert len(a)==15000 and len(v)==5000
        estimators={}
        for ei,name in enumerate(('forward','far_forward')):
            freq=np.bincount([e['m'][ei] for e in a])
            c=reference_percentiles([e['m'][ei] for e in v],[e['key'] for e in v],freq)
            checks=[]
            for (label,lo,hi),mask in zip(CENTRALITIES[1:],masks(c)[1:]):
                expected=(hi-lo)/100;fraction=float(mask.mean())
                tolerance=max(.01,3*math.sqrt(expected*(1-expected)*(1/len(a)+1/len(v))))
                checks.append(dict(group=label,fraction=fraction,expected=expected,tolerance=tolerance,
                                   passed=abs(fraction-expected)<=tolerance))
            above=np.cumsum(freq[::-1])[::-1]-freq;boundaries={}
            for boundary in (10,20,50,60):
                touched=np.where((above/len(a)*100<=boundary)&((above+freq)/len(a)*100>=boundary)&(freq>0))[0]
                boundaries[str(boundary)]=[dict(multiplicity=int(m),events=int(freq[m]),fraction=float(freq[m]/len(a))) for m in touched]
            estimators[name]=dict(frequency=freq.tolist(),validation=checks,zero_fraction=float(freq[0]/freq.sum()),boundary_degeneracy=boundaries,
                                  passed=all(x['passed'] for x in checks),ties='event-key SHA256 randomized percentile')
        systems[system]=dict(calibration_events=len(a),validation_events=len(v),estimators=estimators)
    passed=all(v['passed'] for s in systems.values() for v in s['estimators'].values())
    save(HERE/'CENTRALITY.json',dict(status='PASS' if passed else 'FAIL',signature=p['signature'],utc=now(),systems=systems,
                                  definition='generator final ist0 charged-particle forward multiplicity; not detector V0M'))
    assert passed,'independent MB validation failed; centrality publication is blocked'
    print('CENTRALITY_VALIDATION_PASS',flush=True)

