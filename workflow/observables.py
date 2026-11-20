"""Unchanged r4 pair definitions and fixed cross-stage cohorts."""
import collections
import math
import numpy as np
from core import accept, delta, sector, wrap

B = 30
DIRECTIONS = ("inclusive", "parallel", "perpendicular")
SOURCES = ("strict", "origin1", "origin2", "origin3", "companion4")


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
