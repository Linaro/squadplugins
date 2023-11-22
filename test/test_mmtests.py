import logging
import unittest
from unittest.mock import MagicMock

from mmtests import Mmtests


logger = logging.getLogger()
logger.setLevel(logging.ERROR)


class MmtestsPluginTest(unittest.TestCase):
    def setUp(self):

        attachment = MagicMock()
        attachment.save_file = MagicMock()

        attachments = MagicMock()
        attachments.create = MagicMock(return_value=attachment)
        testrun = MagicMock()
        testrun.attachments = attachments

        testjob = MagicMock()
        testjob.testrun = testrun
        testjob.job_id = "TEST:mygroup@myproject#123"

        tuxsuite = MagicMock()
        tuxsuite.job_url = MagicMock(
            return_value="https://tuxapi.tuxsuite.com/v1/groups/mygroup/projects/myproject/tests/123/"
        )

        filename = "file.txt"
        content = b"some content"
        attachments_url = "https://storage.tuxsuite.com/public/mygroup/myproject/tests/123/attachments/"
        attachment_file_url = f"{attachments_url}{filename}"

        def request_mock(url):
            response = MagicMock()
            response.status_code = 200

            if url == self.attachments_url:
                files_json = {
                    'files': [{
                        'Url': attachment_file_url,
                    }]
                }
                response.json = MagicMock(return_value=files_json)

            elif url == attachment_file_url:
                response.content = content

            return response

        tuxsuite.fetch_url = request_mock

        backend = MagicMock()
        backend.implementation_type = "tuxsuite"
        backend.get_implementation = MagicMock(return_value=tuxsuite)

        testjob.backend = backend

        self.plugin = Mmtests()
        self.attachments_url = attachments_url
        self.attachment_file_url = attachment_file_url
        self.attachments_mock = attachments
        self.attachment_mock = attachment
        self.filename_mock = filename
        self.content_mock = content
        self.testrun_mock = testrun
        self.backend_mock = backend
        self.tuxsuite_mock = tuxsuite
        self.testjob_mock = testjob

    def test_tuxsuite_only(self):
        self.testjob_mock.backend.implementation_type = "lava"
        self.plugin.postprocess_testjob(self.testjob_mock)
        self.testjob_mock.testrun.assert_not_called()

    def test_testrun_must_exist(self):
        self.testjob_mock.testrun = None
        self.plugin.postprocess_testjob(self.testjob_mock)
        self.backend_mock.get_implementation.assert_not_called()

    def test_bad_storage_request(self):
        bad_request = MagicMock()
        bad_request.status_code = 400
        self.tuxsuite_mock.fetch_url = MagicMock(return_value=bad_request)

        self.plugin.postprocess_testjob(self.testjob_mock)
        self.tuxsuite_mock.fetch_url.assert_called_with(self.attachments_url)
        self.attachments_mock.create.assert_not_called()

    def test_missing_json_keys(self):
        bad_request = MagicMock()
        bad_request.status_code = 200
        bad_request.json = MagicMock(return_value={})
        self.tuxsuite_mock.fetch_url = MagicMock(return_value=bad_request)

        self.plugin.postprocess_testjob(self.testjob_mock)
        self.tuxsuite_mock.fetch_url.assert_called_with(self.attachments_url)
        self.attachments_mock.create.assert_not_called()

    def test_attachments_created(self):
        self.plugin.postprocess_testjob(self.testjob_mock)
        self.attachments_mock.create.assert_called_with(filename=self.filename_mock, length=len(self.content_mock))
        self.attachment_mock.save_file.assert_called_with(self.filename_mock, self.content_mock)
