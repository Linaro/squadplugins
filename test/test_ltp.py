import logging
import unittest
from unittest.mock import Mock
from ltp import LtpLogs

TEST_LOG = """
test_1: some log 1
test_1: some log 2
test_1: some log 3
test_3: some log 1
test_3: some log 2
test_3: some log 3
test[a-1]: some log
"""

logger = logging.getLogger()
logger.setLevel(logging.ERROR)


class LtpLogsPluginTest(unittest.TestCase):
    def setUp(self):
        self.plugin = LtpLogs()

    def test_postprocess_testrun(self):
        test_1 = Mock()
        test_1.id = 1
        test_1.name = 'test_1'
        test_1.log = 'the log 1'
        test_1.save.return_value = None

        test_2 = Mock()
        test_2.id = 2
        test_2.name = 'test_2'
        test_2.log = 'the log 2'
        test_2.save.return_value = None

        test_3 = Mock()
        test_3.id = 3
        test_3.name = 'test_3'
        test_3.log = None
        test_3.save.return_value = None

        testrun = Mock()
        testrun.log_file = TEST_LOG

        testrun.tests = Mock()
        testrun.tests.filter.return_value = [test_1, test_2, test_3]

        self.plugin.postprocess_testrun(testrun)
        testrun.tests.filter.assert_called_with(result=False)

        self.assertEqual("the log 1\ntest_1: some log 1\ntest_1: some log 2\ntest_1: some log 3", test_1.log)
        test_1.save.assert_called_with()

        # Test 2 is not in the logs
        self.assertEqual("the log 2", test_2.log)
        test_2.save.assert_not_called()

        # Test 3 didn't have any logs
        self.assertEqual("test_3: some log 1\ntest_3: some log 2\ntest_3: some log 3", test_3.log)
        test_3.save.assert_called_with()

    def test_tests_with_regex_characters(self):
        test = Mock()
        test.id = 1
        test.name = "test[a-1]"
        test.log = "the log"

        testrun = Mock()
        testrun.log_file = TEST_LOG

        testrun.tests = Mock()
        testrun.tests.filter.return_value = [test]

        self.plugin.postprocess_testrun(testrun)

        self.assertEqual("the log\ntest[a-1]: some log", test.log)

        test.save.assert_called_with()


if __name__ == "__main__":
    unittest.main()
