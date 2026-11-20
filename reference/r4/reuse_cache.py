"""Read-only, checksum-bound reuse of the completed r3 source extraction."""
import re
from pathlib import Path
from campaign import HERE,BASE,load,save,sha,signature_of,now


def extractor_text(path):
    match=re.search(r'(?ms)^def output_events\(.*?(?=^def )',Path(path).read_text())
    assert match,'source extractor not found'
    return match.group(0).strip()


def prepare_reuse():
    oldbase=BASE/'initial_source_memory_20261115_r3';old=load(oldbase/'PLAN.json')
    p=load(HERE/'PLAN.json')
    assert not (HERE/'REUSE_SOURCE_CACHE.json').exists(),'reuse already frozen'
    assert signature_of(old)==old['signature']
    for name,digest in old['code_sha'].items():assert sha(oldbase/name)==digest,'changed producer code/evidence'
    assert old['records']==p['records'] and old['source_jobs']==p['source_jobs'],'different input set/order'
    assert sha(oldbase/'core.py')==sha(HERE/'core.py'),'changed identity, kinematics or centrality extraction'
    assert sha(oldbase/'idt.dt')==sha(HERE/'idt.dt'),'changed charge table'
    assert extractor_text(oldbase/'campaign.py')==extractor_text(HERE/'campaign.py'),'changed event serialization'
    items={};events=0
    for job in old['source_jobs']:
        for index in job['indices']:
            path=oldbase/'extracted'/job['key']/('%06d.jsonl.gz'%index)
            donepath=path.with_suffix('.COMPLETE.json');done=load(donepath)
            assert done['signature']==old['signature']
            assert done['events']==old['records'][index]['expected']
            assert sha(path)==done['sha256'],'changed/incomplete extraction'
            items[str(index)]=dict(path=str(path),completion=str(donepath),completion_sha=sha(donepath),
                                   sha256=done['sha256'],events=done['events'],input_root_sha=old['records'][index]['root_sha'])
            events+=done['events']
    assert len(items)==len(p['records'])==1937
    manifest=dict(utc=now(),base=str(oldbase),producer_signature=old['signature'],producer_plan_sha=sha(oldbase/'PLAN.json'),
                  core_sha=sha(HERE/'core.py'),files=items,events=events)
    save(HERE/'REUSE_SOURCE_CACHE.json',manifest)
    p['source_reuse']=dict(base=str(oldbase),producer_signature=old['signature'],producer_plan_sha=manifest['producer_plan_sha'],
                           manifest_sha=sha(HERE/'REUSE_SOURCE_CACHE.json'),files=len(items),events=events)
    save(HERE/'PLAN.json',p)
    print('READ_ONLY_SOURCE_REUSE_FROZEN',len(items),events,flush=True)


def source_artifact(base,p,job,index,cache=None):
    if cache is None:
        path=Path(base)/'extracted'/job['key']/('%06d.jsonl.gz'%index)
        done=load(path.with_suffix('.COMPLETE.json'))
        assert done['signature']==p['signature'] and sha(path)==done['sha256']
        return path,done
    assert cache['producer_signature']==p['source_reuse']['producer_signature']
    item=cache['files'][str(index)]
    assert item['input_root_sha']==p['records'][index]['root_sha']
    assert sha(item['completion'])==item['completion_sha'],'changed reuse completion marker'
    done=load(item['completion']);path=Path(item['path'])
    assert done['signature']==cache['producer_signature']
    assert done['events']==item['events']==p['records'][index]['expected']
    assert done['sha256']==item['sha256']==sha(path),'changed reused payload'
    return path,done


def verify_reuse(p):
    cache=load(HERE/'REUSE_SOURCE_CACHE.json')
    assert sha(HERE/'REUSE_SOURCE_CACHE.json')==p['source_reuse']['manifest_sha']
    assert sha(Path(cache['base'])/'PLAN.json')==cache['producer_plan_sha']
    count=0;events=0
    for job in p['source_jobs']:
        for index in job['indices']:
            path,done=source_artifact(HERE,p,job,index,cache);count+=1;events+=done['events']
    save(HERE/'SOURCE_REUSE_PASS.json',dict(status='PASS',signature=p['signature'],files=count,events=events,utc=now(),
                                         producer_signature=cache['producer_signature'],read_only=True))
    print('SOURCE_REUSE_PASS',count,events,flush=True)
