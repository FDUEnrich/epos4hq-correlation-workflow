import math
import unittest
import numpy as np
from analysis import contributions, reference_percentiles, coverage
from core import decode
from test_core import fixture
from campaign import generator_environment
from pathlib import Path
import collections


class StatisticsTests(unittest.TestCase):
    def test_batch_runtime_does_not_require_login_environment(self):
        env=generator_environment({'source':'/frozen/source','install':'/frozen/install'},Path('/new/work'),{'PATH':'/usr/bin:/bin','seedj':'wrong'})
        self.assertIn('/EPOS4HQ/root/root/lib',env['LD_LIBRARY_PATH'])
        self.assertIn('/HepMC3/install/lib64',env['LD_LIBRARY_PATH'])
        self.assertIn('/fastjet/fastjet-install/lib',env['LD_LIBRARY_PATH'])
        self.assertEqual(env['OPT'],'/new/work/')
        self.assertNotIn('seedj',env)
    def test_normalization_covariance_null_mode(self):
        rng=np.random.RandomState(17);x=np.array([[2.,0.,0.],[0.,1.,0.],[0.,0.,0.],[1.,0.,1.]])
        r=np.array([rng.multinomial(4,np.ones(4)/4).dot(x) for _ in range(1000)])
        ok=r.sum(axis=1)>0;s=r[ok]/r[ok].sum(axis=1)[:,None]
        cov=np.cov(s,rowvar=False)
        self.assertTrue(np.allclose(s.sum(axis=1),1))
        self.assertTrue(np.allclose(cov.sum(axis=0),0,atol=1e-12))
        self.assertLess(cov[0,1],0)
        self.assertTrue(np.allclose(np.cov(np.c_[s,s],rowvar=False)[:3,3:],cov))
    def test_common_cohort_and_signed_bins(self):
        v,c=fixture();p,final=decode(v,1,c,collections.Counter())
        p[0]['final'][0]['phi']=-2.;p[0]['final'][1]['phi']=2.
        e=dict(system='OO',key='test',file_index=0,entry=0,event=1,ep=0.,m=[5,6],pairs=p,final_D0=final)
        names,ei,bi,val,_,_,_=contributions([e])
        i=names.index('wide/inclusive/strict/primary/signed_change')
        self.assertEqual(np.sum(val[(bi//30)==i]),1)
        p[0]['pre']=None
        names,_,_,_,_,_,_=contributions([e])
        self.assertIn('wide/inclusive/strict/primary/final',names)
        self.assertNotIn('wide/inclusive/strict/common3/final',names)
    def test_reference_never_ranks_charm_sample(self):
        c=reference_percentiles([100,0],['same_key','other_key'],[900,100])
        self.assertEqual(c[0],0.)
        self.assertGreaterEqual(c[1],10.)
    def test_source_coverage_without_intermediate(self):
        v,c=fixture();p,final=decode(v,1,c,collections.Counter())
        p[0]['pre']=None
        event=dict(pairs=p,audit={'pre_unknown':2})
        result=coverage([event],[True])
        self.assertEqual(result['by_source']['strict']['wide_primary'],1)
        self.assertEqual(result['by_source']['strict']['wide_missing_pre'],1)
        self.assertEqual(result['event_and_unresolved_counters']['pre_unknown'],2)
        self.assertEqual(coverage([event],[False])['by_source'],{})


if __name__=='__main__':unittest.main()
