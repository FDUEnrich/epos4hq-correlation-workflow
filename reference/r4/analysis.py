"""Joint event/MB bootstrap and traditional ROOT output. No inverse unfolding."""
import collections
import gzip
import json
import math
from pathlib import Path
import numpy as np
import uproot
from core import CENTRALITIES, accept, cent_accept, delta, sector, uniform, wrap
from campaign import HERE, frozen, load, now, save, sha
from reuse_cache import source_artifact

B = 30
DIRECTIONS = ('inclusive','parallel','perpendicular')
SOURCES = ('strict','origin1','origin2','origin3','companion4')


def read_events(path):
    with gzip.open(str(path),'rt') as f:
        for line in f:yield json.loads(line)


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


def coverage(events, selected):
    """Coverage denominators are tagged initial pairs, not all charm production.

    Unknown-origin failures are kept at event/centrality level and never
    assigned to an invented source category. A missing final D leg need not
    mean missing truth: a charm leg can hadronize to another species.
    """
    counters=collections.Counter();origins={}
    for keep,event in zip(selected,events):
        if not keep:continue
        counters['events']+=1;counters.update(event.get('audit',{}))
        for p in event['pairs']:
            for label in (['strict','origin'+str(p['origin'])] if p['origin']<4 else ['companion4']):
                d=origins.setdefault(label,collections.Counter())
                d['unique_initial_pairs']+=1
                if p['final'] is None:continue
                d['final_D_pairs']+=1
                for selection in ('wide','tight'):
                    if accept(*p['final'],selection=selection):
                        d[selection+'_primary']+=1
                        d[selection+('_common3' if p['pre'] is not None else '_missing_pre')]+=1
    return dict(event_and_unresolved_counters=dict(counters),by_source={k:dict(v) for k,v in origins.items()},
                interpretation='conditional tagged-subset coverage, not physical production fractions; missing D can be other hadron species')


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


def th1(values,variances,low=0.,high=math.pi,title=''):
    from uproot.writing.identify import to_TAxis,to_TH1x
    values=np.asarray(values,dtype=np.float64);var=np.asarray(variances,dtype=np.float64)
    centers=np.linspace(low,high,len(values)+1);centers=(centers[1:]+centers[:-1])/2
    return to_TH1x(fName=None,fTitle=title,data=np.r_[0.,values,0.],fEntries=float(np.abs(values).sum()),
                   fTsumw=float(values.sum()),fTsumw2=float(np.nansum(var)),
                   fTsumwx=float(np.dot(values,centers)),fTsumwx2=float(np.dot(values,centers**2)),
                   fSumw2=np.r_[0.,var,0.],fXaxis=to_TAxis(fName='xaxis',fTitle='',fNbins=len(values),fXmin=low,fXmax=high))


def histogram_output(f,path,raw,rep,nevents=None,lo=0.,hi=math.pi):
    raw=np.asarray(raw);width=(hi-lo)/len(raw)
    rawcov=np.atleast_2d(np.cov(rep,rowvar=False,ddof=1))
    f[path+'/sum']=th1(raw,np.diag(rawcov),lo,hi,'raw pair counts; bootstrap includes events and MB')
    f[path+'/sum_cov']=(rawcov,np.linspace(lo,hi,len(raw)+1),np.linspace(lo,hi,len(raw)+1))
    total=float(raw.sum());areas=rep.sum(axis=1);area_error=float(np.std(areas,ddof=1))
    snr=total/area_error if area_error>0 else None
    warning=total<=0 or not np.all(areas>0) or (snr is not None and snr<5)
    valid=total>0 and not warning
    f[path+'/normalization_status']=json.dumps(dict(area=total,point_valid=total>0,errors_valid=bool(valid),
                                                  bootstrap_valid=int(np.sum(areas>0)),bootstrap_total=len(rep),
                                                  area_error=area_error,signal_to_noise=snr,normalization_warning=bool(warning)))
    if total>0:
        density=raw/total/width
        normrep=rep[areas>0]/areas[areas>0,None]/width
        cov=np.cov(normrep,rowvar=False,ddof=1) if len(normrep)>1 else np.full((len(raw),len(raw)),np.nan)
        var=np.diag(cov) if valid else np.full(len(raw),np.nan)
        f[path+'/unit_area']=th1(density,var,lo,hi,'unit-area shape; inspect normalization_status')
        if valid:f[path+'/unit_area_cov']=(cov,np.linspace(lo,hi,len(raw)+1),np.linspace(lo,hi,len(raw)+1))
        display=raw.reshape(10,-1).sum(axis=1);dr=rep.reshape(len(rep),10,-1).sum(axis=2)
        da=dr.sum(axis=1);ok=da>0
        dc=np.cov(dr[ok]/da[ok,None]/((hi-lo)/10),rowvar=False,ddof=1) if ok.sum()>1 else np.full((10,10),np.nan)
        f[path+'/display10']=th1(display/total/((hi-lo)/10),np.diag(dc) if valid else np.full(10,np.nan),lo,hi)
    if nevents is not None:
        n,nrep=nevents
        if n>0:
            means=np.divide(rep,nrep[:,None]*width,out=np.full(rep.shape,np.nan),where=nrep[:,None]>0)
            good=np.all(np.isfinite(means),axis=1)
            cv=np.cov(means[good],rowvar=False,ddof=1) if good.sum()>1 else np.full((len(raw),len(raw)),np.nan)
            f[path+'/event_mean']=th1(raw/n/width,np.diag(cv),lo,hi)
    return rawcov


def contributions(events):
    """Sparse event statistics; all stage comparisons reuse the same pair keys."""
    descriptors={};entries=[];response={};memory={};trace=[];audit=collections.Counter()
    def add(name,e,angle,value=1.):
        d=descriptors.setdefault(name,len(descriptors));span=2*math.pi if name.endswith('signed_change') else math.pi
        bi=min(B-1,max(0,int(angle/span*B)))
        entries.append((e,d*B+bi,value))
    def groups(origin):return (['strict','origin'+str(origin)] if origin<4 else ['companion4'])
    for ei,event in enumerate(events):
        system=event['system'];ep=event['ep'];initial={}
        for p in event['pairs']:
            a,b=p['initial'];initial[(p['pair'],1)]=a;initial[(p['pair'],-1)]=b
            for source in groups(p['origin']):add('initial_all/'+source,ei,delta(a,b))
            if p['final'] is None:continue
            da,db=p['final']
            for selection in ('wide','tight'):
                if not accept(da,db,selection):continue
                for direction in DIRECTIONS:
                    if not sector(a,b,ep,direction):continue
                    for source in groups(p['origin']):
                        base=selection+'/'+direction+'/'+source
                        add(base+'/primary/initial',ei,delta(a,b));add(base+'/primary/final',ei,delta(da,db))
                        signed=wrap((da['phi']-db['phi'])-(a['phi']-b['phi']))
                        add(base+'/primary/signed_change',ei,signed+math.pi)
                        memory.setdefault(base,[]).append((ei,math.cos(signed)))
                        response.setdefault(base,[]).append((ei,delta(a,b),delta(da,db)))
                        if p['pre'] is not None:
                            pa,pb=p['pre']
                            for stage,x,y in [('initial',a,b),('pre',pa,pb),('final',da,db)]:
                                add(base+'/common3/'+stage,ei,delta(x,y))
            row=dict(event_index=ei,file_index=event['file_index'],entry=event['entry'],event=event['event'],pair=p['pair'],origin=p['origin'],
                              track_c=a['track'],track_cbar=b['track'],multiplicity_forward=event['m'][0],multiplicity_far=event['m'][1],
                              initial_dphi=delta(a,b),final_dphi=delta(da,db),pre_dphi=delta(*p['pre']) if p['pre'] else np.nan,
                              wide=accept(da,db,'wide'),tight=accept(da,db,'tight'),pre_available=p['pre'] is not None)
            for stage,parts in [('initial',p['initial']),('pre',p['pre']),('final',p['final'])]:
                for leg,index in [('c',0),('cbar',1)]:
                    for variable in ('phi','pt','eta','y','row'):
                        row[stage+'_'+leg+'_'+variable]=parts[index][variable] if parts else (np.nan if variable!='row' else -1)
            trace.append(row)
        candidates=event['final_D0']
        for i,a in enumerate(candidates):
            for b in candidates[i+1:]:
                os_pair=a['id']==-b['id'];sign=1. if os_pair else -1.
                for selection in ('wide','tight'):
                    if not accept(a,b,selection):continue
                    base=selection+'/inclusive/control_all'
                    add(base+'/OSminusSS',ei,delta(a,b),sign)
                    add(base+('/OS' if os_pair else '/SS'),ei,delta(a,b))
                    ia=initial.get((a.get('pair'),a.get('leg')));ib=initial.get((b.get('pair'),b.get('leg')))
                    if ia is None or ib is None or max(ia['origin'],ib['origin'])>3:continue
                    for direction in DIRECTIONS:
                        if sector(ia,ib,ep,direction):add(selection+'/'+direction+'/control_resolved/OSminusSS',ei,delta(a,b),sign)
    if not entries:raise ValueError('no analyzable source or control statistics')
    e=np.asarray([x[0] for x in entries],dtype=np.int64);k=np.asarray([x[1] for x in entries],dtype=np.int64);v=np.asarray([x[2] for x in entries])
    # Collapse repeated pairs in the same event/bin before bootstrap.
    size=len(descriptors)*B;combined=e*size+k;u,inv=np.unique(combined,return_inverse=True)
    values=np.bincount(inv,weights=v);return list(descriptors),u//size,u%size,values,response,memory,trace


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
                reps=np.zeros((1000,4,size));nreps=np.zeros((1000,4));bootstrap_groups=np.zeros((1000,n),dtype=np.uint8)
                rng=np.random.RandomState(15112026+(system=='OO')*97+est_index*13)
                for boot in range(1000):
                    draw=rng.multinomial(n,np.ones(n)/n)
                    fdraw=rng.multinomial(int(freq.sum()),freq/freq.sum())
                    bc=reference_percentiles(m,keys,fdraw)
                    for ci,mask in enumerate(masks(bc)):
                        if ci:bootstrap_groups[boot,mask]=ci
                        w=draw*mask;nreps[boot,ci]=w.sum()
                        reps[boot,ci]=np.bincount(bins,weights=values*w[eids],minlength=size)
                    if boot%100==0:print('BOOTSTRAP',system,estimator,boot,flush=True)
                # Replay the same event draws for response and memory statistics.
                rng=np.random.RandomState(15112026+(system=='OO')*97+est_index*13)
                draws=np.empty((1000,n),dtype=np.int32)
                for boot in range(1000):
                    draws[boot]=rng.multinomial(n,np.ones(n)/n);rng.multinomial(int(freq.sum()),freq/freq.sum())
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
