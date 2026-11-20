import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

from tests.test_regression import REPO, campaign

spec=importlib.util.spec_from_file_location('prepare_simulation',REPO/'scripts/prepare_simulation.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)

FORBIDDEN=r'(?im)^\s*(request_cpus|request_memory|request_disk|requirements|rank|concurrencylimits|machine|should_transfer_files|max_materialize|max_idle)\s*='


class SubmissionTests(unittest.TestCase):
    def test_simulation_changes_only_event_budget_and_seeds(self):
        for system in ('PbPb','OO'):
            text=(REPO/'configs/historical'/(system+'.optns')).read_text()
            transformed=prepare.production_options(text,17)
            self.assertEqual(campaign.physics(text),campaign.physics(transformed))
            self.assertRegex(transformed,r'set nfull 17')
            self.assertNotRegex(transformed,r'(?m)^\s*set seed[ji]')
            self.assertNotIn('set iskip 0',transformed)

    def test_minimal_production_submission(self):
        text=prepare.submit_text(Path('/batch'),Path('/output'),20000,'OO')
        self.assertIsNone(re.search(FORBIDDEN,text))
        self.assertIn('queue 20000',text)
        self.assertIn('notification = Never',text)
        self.assertNotIn('notify_user',text)

    def test_analysis_submit_files_are_minimal(self):
        with tempfile.TemporaryDirectory() as d:
            old=campaign.HERE
            try:
                campaign.HERE=Path(d)
                campaign.write_submit([dict(key='OO_000')],[dict(key='OO_000')])
                files=list(Path(d).glob('*.sub'));self.assertEqual(len(files),7)
                for f in files:self.assertIsNone(re.search(FORBIDDEN,f.read_text()),f.name)
                self.assertIn('PARENT SOURCES CALIBRATION CHILD ANALYSIS',(Path(d)/'analysis.dag').read_text())
            finally:campaign.HERE=old

    def test_render_isolated_batch_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='epos_sim_') as d:
            d=Path(d);source=d/'source';install=d/'install';root=d/'root/bin/root'
            (source/'srcext/HQ').mkdir(parents=True);(source/'srcext/HQ/hq.i').write_text('set iskip 1\n')
            (install/'bin').mkdir(parents=True);(install/'bin/Xepos').write_bytes(b'TEST_ONLY')
            root.parent.mkdir(parents=True);root.write_bytes(b'TEST_ONLY')
            a=argparse.Namespace(system='PbPb',destination=str(d/'new'),source=str(source),install=str(install),root=str(root),
                jobs=10,events=4,seed_base=1001,seed_stride=7919,seedi=222222222,
                pythonhome=str(d/'python'),hepmc_lib=str(d/'hepmc'),fastjet_lib=str(d/'fastjet'))
            batch=prepare.prepare(a)
            self.assertTrue((batch/'FROZEN_SHA256SUMS').is_file())
            self.assertTrue((batch/'ValidateProduction.C').is_file())
            self.assertIsNone(re.search(FORBIDDEN,(batch/'simulation.sub').read_text()))
            self.assertRaises(FileExistsError,prepare.prepare,a)
            a.destination=str(d/'overflow');a.seed_base=999999999
            self.assertRaises(ValueError,prepare.prepare,a)
            self.assertFalse((d/'overflow').exists())

    def test_native_root_validator_changes_labels_only(self):
        old=(REPO/'reference/production/ValidateOO.C').read_text().strip()
        new=(REPO/'simulation/ValidateProduction.C').read_text().strip()
        reconstructed=new.replace('void ValidateProduction(','void ValidateOO(')
        reconstructed=reconstructed.replace('const char* system,int requested','int requested')
        reconstructed=reconstructed.replace('\\"system\\":\\""<<system<<"\\",\\"requested\\":','\\"system\\":\\"OO\\",\\"requested\\":')
        reconstructed=reconstructed.replace('V5_VALIDATION','OO_V5_VALIDATION')
        self.assertEqual(old,reconstructed)

    def test_legacy_and_portable_production_discovery(self):
        with tempfile.TemporaryDirectory(prefix='epos_discovery_') as d:
            base=Path(d);(base/'_batch').mkdir();(base/'done').mkdir()
            work=base/'jobs/cluster_1/job_00000';work.mkdir(parents=True)
            (work/'RESULT_SHA256SUMS').write_text('TEST_ONLY\n')
            m=dict(status='PASS',cluster=1,process=0,root='/test/input.root',seedj=123,seedi=456,
                   retained_events=2,root_sha256='TEST_ONLY',binary_sha256='TEST_ONLY',hq_sha256='TEST_ONLY',
                   result_manifest_sha256=campaign.sha(work/'RESULT_SHA256SUMS'))
            for p in (work/'SHARD_COMPLETE.json',base/'done/job.json'):p.write_text(json.dumps(m))
            (base/'_batch/batch_config.json').write_text('{}')
            records,t=campaign.completed_production(base,'OO')
            self.assertEqual(len(records),1);self.assertEqual(t['source'],str(base/'_batch/runtime/source'))
            config=dict(system='PbPb',source='/explicit/source',install='/explicit/install')
            (base/'_batch/batch_config.json').write_text(json.dumps(config))
            records,t=campaign.completed_production(base,'PbPb')
            self.assertEqual(records[0]['system'],'PbPb');self.assertEqual(t['source'],'/explicit/source')
            self.assertRaises(AssertionError,campaign.completed_production,base,'OO')


if __name__=='__main__':unittest.main()
