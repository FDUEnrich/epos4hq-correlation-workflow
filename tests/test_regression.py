"""Compare refactored calculations with the downloaded r4 baseline."""
import ast
import collections
import gzip
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import uproot

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'workflow'))
import analysis
import bootstrap
import campaign
import centrality
import core
import observables
from test_core import fixture


def baseline(name):
    spec = importlib.util.spec_from_file_location('reference_'+name, REPO/'reference/r4'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OLD = baseline('analysis')
OLD_CORE = baseline('core')


def events(number=24):
    out = []
    for i in range(number):
        v, cert = fixture(origin=4 if i % 5 == 0 else 1)
        pairs, final = core.decode(v, 1, cert, collections.Counter())
        for j, p in enumerate(final):
            p['phi'] += .02*(i % 5)*(-1 if j else 1)
        if i % 4 == 0:
            pairs[0]['pre'] = None
        if i % 3 == 0:
            final.append(dict(final[0], phi=.4, row=1000))
        out.append(dict(system='OO', key='synthetic/'+str(i), file_index=0,
                        entry=i, event=i+1, ep=0., m=[i % 4, i % 3], b=1.,
                        pairs=pairs, final_D0=final, audit={}))
    return out


def function_ast(path, name):
    node = next(x for x in ast.parse(path.read_text()).body
                if isinstance(x, ast.FunctionDef) and x.name == name)
    return ast.dump(node, include_attributes=False)


class RegressionTests(unittest.TestCase):
    def test_identity_core_is_byte_identical(self):
        self.assertEqual((REPO/'workflow/core.py').read_bytes(),
                         (REPO/'reference/r4/core.py').read_bytes())

    def test_extractor_ast_is_unchanged(self):
        for name in ('output_events', 'physics', 'signature_of'):
            self.assertEqual(function_ast(REPO/'workflow/campaign.py', name),
                             function_ast(REPO/'reference/r4/campaign.py', name))

    def test_observable_and_writer_functions_unchanged(self):
        for filename, names in [('observables.py', ('contributions', 'coverage')),
                                ('root_output.py', ('th1', 'histogram_output')),
                                ('centrality.py', ('reference_percentiles', 'masks', 'calibrate'))]:
            for name in names:
                self.assertEqual(function_ast(REPO/'workflow'/filename, name),
                                 function_ast(REPO/'reference/r4/analysis.py', name))

    def test_percentiles_and_ties(self):
        rng = np.random.RandomState(7)
        values = rng.randint(0, 300, 1000)
        keys = ['event/'+str(i) for i in range(len(values))]
        for freq in (np.array([15000]), rng.multinomial(15000, np.ones(200)/200)):
            np.testing.assert_array_equal(centrality.reference_percentiles(values, keys, freq),
                                          OLD.reference_percentiles(values, keys, freq))

    def compare_contributions(self, data):
        old, new = OLD.contributions(data), observables.contributions(data)
        self.assertEqual(old[0], new[0])
        for a, b in zip(old[1:4], new[1:4]):
            np.testing.assert_array_equal(a, b)
        self.assertEqual(json.dumps(old[4:], sort_keys=True), json.dumps(new[4:], sort_keys=True))

    def test_all_pair_statistics_and_cohorts(self):
        self.compare_contributions(events())

    def test_real_cached_sample_when_supplied(self):
        location = os.environ.get('EPOS_REAL_FIXTURES')
        if not location:
            self.skipTest('Set EPOS_REAL_FIXTURES to the private, untracked sample directory')
        paths = sorted(Path(location).glob('*/*.jsonl.gz'))
        self.assertGreaterEqual(len(paths), 2)
        for path in paths:
            with gzip.open(str(path), 'rt') as f:
                data = [json.loads(line) for line in f]
            self.compare_contributions(data)
            self.assertEqual(OLD.coverage(data, [True]*len(data)),
                             observables.coverage(data, [True]*len(data)))

    def test_single_pass_bootstrap_bitwise_matches_replay(self):
        data = events()
        names, eids, bins, values, _, _, _ = OLD.contributions(data)
        size = len(names)*30
        n = len(data)
        m = np.array([x['m'][0] for x in data])
        keys = [x['key'] for x in data]
        freq = np.array([3000, 4000, 5000, 3000])
        for system, estimator in [('PbPb', 0), ('OO', 1)]:
            rng = np.random.RandomState(15112026+(system=='OO')*97+estimator*13)
            reps = np.zeros((100,4,size));totals=np.zeros((100,4))
            groups=np.zeros((100,n),dtype=np.uint8)
            for boot in range(100):
                draw=rng.multinomial(n,np.ones(n)/n)
                fdraw=rng.multinomial(int(freq.sum()),freq/freq.sum())
                bc=OLD.reference_percentiles(m,keys,fdraw)
                for ci,mask in enumerate(OLD.masks(bc)):
                    if ci:groups[boot,mask]=ci
                    w=draw*mask;totals[boot,ci]=w.sum()
                    reps[boot,ci]=np.bincount(bins,weights=values*w[eids],minlength=size)
            rng=np.random.RandomState(15112026+(system=='OO')*97+estimator*13)
            draws=np.empty((100,n),dtype=np.int32)
            for boot in range(100):
                draws[boot]=rng.multinomial(n,np.ones(n)/n)
                rng.multinomial(int(freq.sum()),freq/freq.sum())
            actual=bootstrap.joint_bootstrap(eids,bins,values,size,m,keys,freq,
                                             system,estimator,replicas=100,progress=False)
            for a,b in zip(actual,(reps,totals,groups,draws)):
                np.testing.assert_array_equal(a,b)

    def test_root_writer_retains_all_bins_errors_and_status(self):
        rng=np.random.RandomState(91)
        cases=[np.arange(30,dtype=float)+1, np.zeros(30), -np.ones(30)]
        with tempfile.TemporaryDirectory() as d:
            paths=[Path(d)/'old.root',Path(d)/'new.root']
            for path,module in zip(paths,(OLD,analysis)):
                with uproot.recreate(str(path)) as dest:
                    rng=np.random.RandomState(91)
                    for i,raw in enumerate(cases):
                        reps=rng.poisson(np.abs(raw),size=(100,30)).astype(float)
                        if i==2:reps*=-1
                        module.histogram_output(dest,'case'+str(i),raw,reps,(24,np.full(100,24)))
            with uproot.open(str(paths[0])) as a,uproot.open(str(paths[1])) as b:
                self.assertEqual(a.classnames(),b.classnames())
                for name,kind in a.classnames().items():
                    if kind.startswith('TH'):
                        np.testing.assert_array_equal(a[name].values(),b[name].values())
                        np.testing.assert_array_equal(a[name].variances(),b[name].variances())
                    elif kind=='TObjString':self.assertEqual(str(a[name]),str(b[name]))


if __name__ == '__main__':
    unittest.main()
