import tempfile
import unittest
from pathlib import Path
from campaign import save,sha
from reuse_cache import source_artifact,extractor_text


class ReuseTests(unittest.TestCase):
    def test_read_only_reuse_binds_input_completion_and_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);payload=base/'data.gz';payload.write_bytes(b'fixed test payload')
            done=base/'data.COMPLETE.json';save(done,dict(signature='producer',events=2,sha256=sha(payload),audit={}))
            p=dict(source_reuse={'producer_signature':'producer'},records=[dict(root_sha='input',expected=2)])
            item=dict(path=str(payload),completion=str(done),completion_sha=sha(done),sha256=sha(payload),events=2,input_root_sha='input')
            cache=dict(producer_signature='producer',files={'0':item})
            self.assertEqual(source_artifact(base,p,{},0,cache)[0],payload)
            payload.write_bytes(b'changed')
            self.assertRaises(AssertionError,source_artifact,base,p,{},0,cache)
    def test_producer_function_is_unchanged(self):
        here=Path(__file__).resolve().parent
        prior=here.parent/'initial_source_memory_20261115_r3/campaign.py'
        if prior.exists():self.assertEqual(extractor_text(prior),extractor_text(here/'campaign.py'))


if __name__=='__main__':unittest.main()
