import unittest
from mb_config import build_mb_options,checked_mb_stdout


class MBTests(unittest.TestCase):
    def test_override_is_inside_hq_scope_only(self):
        original='set nfull 4\nxinput srcext/HQ/hq.i\nset seedj 12\n'
        new=build_mb_options(original,2,930000001,222222222)
        self.assertIn('beginoptns hq\nset iskip 0\nendoptns hq',new)
        self.assertIn('set nfull 2',new)
        self.assertIn('xinput srcext/HQ/hq.i',new)
        self.assertNotIn('set seedj 12\n',new)
        self.assertEqual(new.count('set iskip'),1)
    def test_generic_echo_does_not_prove_runtime(self):
        self.assertRaises(AssertionError,checked_mb_stdout,'set iskip 0\n iskip : 1\nstop program;')
        self.assertRaises(AssertionError,checked_mb_stdout,'set iskip 0\nstop program;')
        self.assertRaises(AssertionError,checked_mb_stdout,' iskip : 0\n iskip : 1\nstop program;')
        self.assertRaises(AssertionError,checked_mb_stdout,' iskip : 0\n No c quarks, event skipped\nstop program;')
        self.assertRaises(AssertionError,checked_mb_stdout,' iskip : 0\n')
        self.assertEqual(checked_mb_stdout(' iskip : 0\nstop program;')['runtime_iskip'],[0])
    def test_template_event_count_ambiguity(self):
        self.assertRaises(AssertionError,build_mb_options,'set nfull 2\nset nfull 4\n',2,1,2)


if __name__=='__main__':unittest.main()
