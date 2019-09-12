from unittest.mock import MagicMock, Mock
from unittest import TestCase
from kernel_issues import KernelIssues

"""
    TEST_LOG contains an entangled example of dmesg messages
    extracted from several kernel logs. To date, it contains:
    - 0 Stack...end trace
    - 1 Oops:
    - 1 [ cut here ]
    - 2 Kernel panic - not syncing
    - 2 Unhandled fault:
    - 3 WARNING: (on their on)
"""
TEST_LOG = open('test/example_dmesg.log', 'r').read()


class KernelIssuesPluginTest(TestCase):
    def setUp(self):
        self.__tests_created__ = []
        suite = Mock(slug='')
        suites = Mock(**{'get_or_create.return_value': (suite, None)})
        project = Mock(suites=suites)
        build = Mock(project=project)

        tests = Mock()
        tests.create = lambda **kwargs: self.__tests_created__.append(kwargs)

        self.testrun = Mock(build=build, tests=tests, log=TEST_LOG)

    def test_postprocess_testrun(self):
        plugin = KernelIssues()
        plugin.postprocess_testrun(self.testrun)

        self.assertEqual(6, len(self.__tests_created__))

        tests = {t['name']: {'result': t['result'], 'log': t['log']} for t in self.__tests_created__}
        self.assertTrue(tests['kernel_trace']['result'])
        self.assertEqual('', tests['kernel_trace']['log'])

        self.assertFalse(tests['kernel_panic']['result'])
        self.assertIn('Kernel panic', tests['kernel_panic']['log'])

        self.assertFalse(tests['kernel_exception']['result'])
        self.assertIn('----[ cut here ]----', tests['kernel_exception']['log'])

        self.assertFalse(tests['kernel_oops']['result'])
        self.assertIn('Oops:', tests['kernel_oops']['log'])

        self.assertFalse(tests['kernel_fault']['result'])
        self.assertIn('Unhandled fault', tests['kernel_fault']['log'])

        self.assertFalse(tests['kernel_warning']['result'])
        self.assertIn('WARNING:', tests['kernel_warning']['log'])
