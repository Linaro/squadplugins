import logging
import unittest
from mock import PropertyMock, Mock
from ltp import LtpLogs


TEST_LOG = """
test_1: some log 1
test_1: some log 2
test_1: some log 3
test_3: some log 1
test_3: some log 2
test_3: some log 3
"""

logger = logging.getLogger()
logger.setLevel(logging.ERROR)


class LtpLogsPluginTest(unittest.TestCase):
    def setUp(self):
        self.plugin = LtpLogs()

    def test_postprocess_testrun(self):
        test_1 = Mock()
        test_1_name = PropertyMock(return_value="test_1")
        type(test_1).name = test_1_name
        test_1_log = PropertyMock()
        type(test_1).log = test_1_log

        test_2 = Mock()
        test_2_name = PropertyMock(return_value="test_2")
        type(test_2).name = test_2_name
        test_2_log = PropertyMock()
        type(test_2).log = test_2_log

        test_3 = Mock()
        test_3_name = PropertyMock(return_value="test_3")
        type(test_3).name = test_3_name
        test_3_log = PropertyMock()
        type(test_3).log = test_3_log

        testrun = Mock()
        testrun_log = PropertyMock(return_value=TEST_LOG)
        type(testrun).log_file = testrun_log

        testrun.tests = Mock()
        testrun.tests.filter.return_value = [test_1, test_2, test_3]

        self.plugin.postprocess_testrun(testrun)
        testrun.tests.filter.assert_called()
        testrun_log.assert_called()

        test_1_name.assert_called()
        test_1_log.assert_called()
        test_1.save.assert_called()

        # test_2 not present in the log
        test_2_name.assert_called()
        test_2_log.assert_not_called()
        test_2.save.assert_not_called()

        test_3_name.assert_called()
        test_3_log.assert_called()
        test_3.save.assert_called()


if __name__ == "__main__":
    unittest.main()
