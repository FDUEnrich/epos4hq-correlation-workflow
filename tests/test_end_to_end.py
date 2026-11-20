"""Full synthetic old/new ROOT comparison, including all 1000 bootstrap draws."""
import contextlib
import copy
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
import warnings

import numpy as np
import uproot
from tests.test_regression import OLD, analysis, campaign, events


def run(module, root):
    plan=dict(signature='TEST_ONLY', records=[], source_jobs=[],
              source_reuse={'producer_signature':'TEST_ONLY_PRODUCER'})
    cache=dict(producer_signature='TEST_ONLY_PRODUCER', files={})
    for si, system in enumerate(('PbPb','OO')):
        key=system+'_test';data=events()
        for e in data:
            e.update(system=system, key=system+'/'+e['key'], file_index=si)
        record=dict(system=system,root_sha='TEST_ONLY_'+system,expected=len(data))
        plan['records'].append(record);plan['source_jobs'].append(dict(key=key,indices=[si]))
        path=root/'extracted'/key/('%06d.jsonl.gz'%si);path.parent.mkdir(parents=True)
        with gzip.open(str(path),'wt') as f:
            for e in data:f.write(json.dumps(e)+'\n')
        done=path.with_suffix('.COMPLETE.json')
        campaign.save(done,dict(signature='TEST_ONLY_PRODUCER',sha256=campaign.sha(path),audit={},events=len(data)))
        cache['files'][str(si)]=dict(path=str(path),completion=str(done),completion_sha=campaign.sha(done),
                                   sha256=campaign.sha(path),events=len(data),input_root_sha=record['root_sha'])
    campaign.save(root/'REUSE_SOURCE_CACHE.json',cache)
    cal=dict(status='PASS',signature='TEST_ONLY',systems={})
    for system in ('PbPb','OO'):
        cal['systems'][system]=dict(estimators={x:dict(frequency=[3000,4000,5000,3000])
                                               for x in ('forward','far_forward')})
    campaign.save(root/'CENTRALITY.json',cal)
    old_here,old_frozen=module.HERE,module.frozen
    try:
        module.HERE=root;module.frozen=lambda:plan
        with contextlib.redirect_stdout(io.StringIO()),warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning);module.analyze()
    finally:
        module.HERE, module.frozen=old_here,old_frozen
    return root/'output/InitialCharmCorrelationEvolution.root'


class PipelineTests(unittest.TestCase):
    def test_entire_root_payload_matches(self):
        with tempfile.TemporaryDirectory() as d:
            a=run(OLD,Path(d)/'old');b=run(analysis,Path(d)/'new')
            with uproot.open(str(a)) as old,uproot.open(str(b)) as new:
                self.assertEqual(old.classnames(),new.classnames())
                histograms=0
                for key,kind in old.classnames().items():
                    if kind.startswith('TH'):
                        histograms+=1
                        np.testing.assert_array_equal(old[key].values(),new[key].values(),err_msg=key)
                        np.testing.assert_array_equal(old[key].variances(),new[key].variances(),err_msg=key)
                    elif kind=='TObjString':self.assertEqual(str(old[key]),str(new[key]),key)
                    elif kind=='TTree':
                        x=old[key].arrays(library='np');y=new[key].arrays(library='np')
                        self.assertEqual(set(x),set(y))
                        for branch in x:np.testing.assert_array_equal(x[branch],y[branch],err_msg=key+'/'+branch)
                self.assertGreater(histograms,100)


if __name__=='__main__':unittest.main()
