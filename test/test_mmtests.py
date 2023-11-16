import logging
import unittest
import requests_mock
from unittest.mock import Mock
from mmtests import Mmtests
from unittest.mock import PropertyMock, MagicMock, Mock, patch

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


class MmtestsPluginTest(unittest.TestCase):
    def setUp(self):
        self.plugin = Mmtests()
        self.testjob_mock = MagicMock()
        self.testjob_mock.backend = MagicMock()
        self.testjob_mock.testrun = MagicMock()
        implementation_type_mock = PropertyMock(return_value="tuxsuite")
        self.testjob_mock.backend.implementation_type = implementation_type_mock

    def test_tuxsuite_only(self):

        self.testjob_mock.backend.implementation_type = PropertyMock(return_value="lava")
        self.plugin.postprocess_testjob(self.testjob_mock)
        self.testjob_mock.testrun.assert_not_called()


    def test_no_attachments(self):
        pass

    def test_content_not_available(self):
        pass

    def test_filename_not_abailable(self):
        pass

    def test_attachments_created(self):
        pass


if __name__ == "__main__":
    unittest.main()
