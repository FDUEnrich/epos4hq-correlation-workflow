"""Compatibility entry point for the r4 observables; no physics changes."""
import collections
import json
import math
import numpy as np
import uproot
from core import CENTRALITIES, accept, cent_accept, delta, sector, uniform, wrap
from campaign import HERE, frozen, load, now, save, sha
from reuse_cache import source_artifact
from io_utils import read_events
from centrality import calibrate, masks, reference_percentiles
from observables import B, DIRECTIONS, SOURCES, contributions, coverage
from root_output import histogram_output, th1
from bootstrap import joint_bootstrap


def analyze():
    p=frozen();cal=load(HERE/'CENTRALITY.json');assert cal['status']=='PASS' and cal['signature']==p['signature']
    out=HERE/'output';out.mkdir(exist_ok=True);target=out/'InitialCharmCorrelationEvolution.root'
    assert not target.exists(),'never silently overwrite a merged result'
    temp=target.with_name(target.name+'.tmp');source_audit=collections.Counter();all_trace=[];summary={}
    with uproot.recreate(str(temp)) as dest:
        dest['provenance']=json.dumps(dict(signature=p['signature'],stage='ist21 -> unique pre-UrQMD D0 (6/8,ity60) -> final ist0/1 D0',
                                         mass='ROOT e is mass, not energy',source='certified origins1/2/3 separate from companion4',
                                         interpretation='conditional on tagged source subset; not all charm production',bootstrap=1000,
                                         event_mean='per retained tagged event; not an unconditional minimum-bias yield',
                                         centrality=cal,inputs=p['records'],source_reuse=p.get('source_reuse')),sort_keys=True)
        cache=load(HERE/'REUSE_SOURCE_CACHE.json') if p.get('source_reuse') else None
        for system in ('PbPb','OO'):
            events=[];seen=set()
            for job in p['source_jobs']:
                for index in job['indices']:
                    r=p['records'][index]
                    if r['system']!=system:continue
                    path,done=source_artifact(HERE,p,job,index,cache);source_audit.update(done['audit'])
                    for event in read_events(path):
                        assert event['key'] not in seen;seen.add(event['key']);events.append(event)
            assert events
            names,eids,bins,values,responses,memory,trace=contributions(events);n=len(events);size=len(names)*B
            path_index={name:i for i,name in enumerate(names)};keys=[e['key'] for e in events]
            summary[system]=dict(events=n,final_source_pairs=len(trace),source_files=sum(r['system']==system for r in p['records']))
            print('STATISTICS_READY',system,n,len(names),len(values),flush=True)
            for estimator,est_index in [('forward',0),('far_forward',1)]:
                freq=np.asarray(cal['systems'][system]['estimators'][estimator]['frequency'])
                m=np.asarray([e['m'][est_index] for e in events]);c=reference_percentiles(m,keys,freq);cm=masks(c)
                points=np.asarray([np.bincount(bins,weights=values*mask[eids],minlength=size) for mask in cm])
                reps,nreps,bootstrap_groups,draws=joint_bootstrap(
                    eids,bins,values,size,m,keys,freq,system,est_index)
                for ci,(cent,_,_) in enumerate(CENTRALITIES):
                    prefix=system+'/'+estimator+'/'+cent
                    dest[prefix+'/coverage']=json.dumps(coverage(events,cm[ci]),sort_keys=True)
                    for di,name in enumerate(names):
                        raw=points[ci,di*B:(di+1)*B];r=reps[:,ci,di*B:(di+1)*B]
                        if not np.any(raw) and not np.any(r):continue
                        lo,hi=(-math.pi,math.pi) if name.endswith('signed_change') else (0.,math.pi)
                        histogram_output(dest,prefix+'/'+name,raw,r,(int(cm[ci].sum()),nreps[:,ci]),lo,hi)
                    for base,records in responses.items():
                        idx=np.asarray([x[0] for x in records],dtype=int)
                        xx=np.asarray([x[1] for x in records]);yy=np.asarray([x[2] for x in records])
                        raw,_,_=np.histogram2d(xx,yy,bins=30,range=[[0,math.pi],[0,math.pi]],weights=cm[ci][idx])
                        dest[prefix+'/'+base+'/migration/count30']=(raw,np.linspace(0,math.pi,31),np.linspace(0,math.pi,31))
                        rows=np.minimum(9,(xx/math.pi*10).astype(int));cols=np.minimum(9,(yy/math.pi*10).astype(int));flat=rows*10+cols
                        point=np.bincount(flat,weights=cm[ci][idx],minlength=100).reshape(10,10)
                        rowN=point.sum(axis=1);conditional=np.divide(point,rowN[:,None],out=np.full((10,10),np.nan),where=rowN[:,None]>0)
                        rr=np.empty((1000,10,10));mreps=np.empty(1000)
                        cos=np.asarray([x[1] for x in memory[base]])
                        for boot in range(1000):
                            mask=np.ones(len(idx),dtype=bool) if ci==0 else bootstrap_groups[boot,idx]==ci
                            w=draws[boot,idx]*mask
                            a=np.bincount(flat,weights=w,minlength=100).reshape(10,10);nn=a.sum(axis=1)
                            rr[boot]=np.divide(a,nn[:,None],out=np.full((10,10),np.nan),where=nn[:,None]>0)
                            mreps[boot]=np.dot(w,cos)/w.sum() if w.sum()>0 else np.nan
                        dest[prefix+'/'+base+'/migration/conditional10']=(conditional,np.linspace(0,math.pi,11),np.linspace(0,math.pi,11))
                        dest[prefix+'/'+base+'/migration/bootstrap_variance10']=(np.nanvar(rr,axis=0,ddof=1),np.linspace(0,math.pi,11),np.linspace(0,math.pi,11))
                        dest[prefix+'/'+base+'/migration/row_status']=json.dumps(dict(count=rowN.tolist(),recommended_minimum=20,low_statistics=(rowN<20).tolist()))
                        w=cm[ci][idx];mean=float(np.dot(w,cos)/w.sum()) if w.sum() else None
                        dest[prefix+'/'+base+'/memory']=json.dumps(dict(cosine_mean=mean,bootstrap_std=float(np.nanstd(mreps,ddof=1)) if np.isfinite(mreps).sum()>1 else None,
                                                                      valid_replicates=int(np.isfinite(mreps).sum()),definition='cos(wrap((phiD-phiDbar)-(phic-phicbar))); signed legs fixed'))
                    for base in responses:
                        for cohort,stages in [('primary',['initial','final']),('common3',['initial','pre','final'])]:
                            ids=[path_index.get(base+'/'+cohort+'/'+s) for s in stages]
                            if any(i is None for i in ids):continue
                            raw=np.concatenate([points[ci,i*B:(i+1)*B] for i in ids]);rs=[];good=np.ones(1000,dtype=bool)
                            for i in ids:
                                r=reps[:,ci,i*B:(i+1)*B];area=r.sum(axis=1);good&=area>0
                                rs.append(np.divide(r,area[:,None]*(math.pi/B),out=np.full(r.shape,np.nan),where=area[:,None]>0))
                            if good.all():
                                joint=np.concatenate(rs,axis=1);cov=np.cov(joint,rowvar=False,ddof=1);edges=np.arange(len(cov)+1,dtype=float)
                                dest[prefix+'/'+base+'/'+cohort+'/joint_stage_cov']=(cov,edges,edges)
                for row in trace:row['system_code']=0 if system=='PbPb' else 1
                if estimator=='forward':
                    for row in trace:row['centrality_forward']=float(c[row['event_index']])
                    all_trace.extend(trace)
                del reps,draws,bootstrap_groups
        if all_trace:
            schema={k:('bool' if isinstance(v,bool) else 'float64' if isinstance(v,float) else 'int64') for k,v in all_trace[0].items()}
            dest.mktree('source_pairs',schema)
            dest['source_pairs'].extend({k:np.asarray([r[k] for r in all_trace]) for k in schema})
        dest['audit']=json.dumps(dict(source=dict(source_audit),systems=summary),sort_keys=True)
    with uproot.open(str(temp)) as check:
        assert 'source_pairs' in check and check['source_pairs'].num_entries==len(all_trace)
        count=0
        for name,cls in check.classnames(recursive=True).items():
            if cls=='TH1D' and '/unit_area;' in name:
                h=check[name];assert abs(np.sum(h.values()*np.diff(h.axis().edges()))-1)<1e-9;count+=1
        assert count>0
    temp.rename(target)
    save(HERE/'COMPLETE.json',dict(status='COMPUTATIONAL_PASS',signature=p['signature'],root=str(target),sha256=sha(target),utc=now(),systems=summary,
                                  limitations='Certified tagged subset only; sparse bins are not evidence of no effect; MB validation is generator-level, not detector calibration.'))
    print('EVOLUTION_ANALYSIS_PASS',flush=True)

