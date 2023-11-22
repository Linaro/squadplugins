import logging
from squad.plugins import Plugin as BasePlugin
from urllib.parse import urlparse, urljoin


logger = logging.getLogger()


class Mmtests(BasePlugin):
    name = "Mmtests"

    def postprocess_testjob(self, testjob):
        if testjob.backend.implementation_type != "tuxsuite":
            logger.debug("Mmtests runs only on Tuxsuite backends for now")
            return

        testrun = testjob.testrun
        if testrun is None:
            logger.error(f"Failed to run Mmtests plugin: no testrun for job {testjob.id}")
            return

        tuxsuite = testjob.backend.get_implementation()
        job_url = tuxsuite.job_url(testjob) + "/"

        job_url_path = urlparse(job_url).path.replace("/v1/", "/public/").replace("/groups/", "/").replace("/projects/", "/")
        attachments_url = urljoin("https://storage.tuxsuite.com", job_url_path)
        attachments_url = urljoin(attachments_url, "attachments") + "/"

        response = tuxsuite.fetch_url(attachments_url)
        if response.status_code != 200:
            logger.debug(f"Failed to run Mmtests plugin: bad http response {response.status_code} when fetching {attachments_url}")
            return

        try:
            file_urls = [f['Url'] for f in response.json()['files']]
        except KeyError:
            logger.debug("Failed to run Mmtests plugin: the returned json does not have 'files' or 'Url' keys")
            return

        for url in file_urls:
            response = tuxsuite.fetch_url(url)
            if response.status_code != 200:
                logger.error(f"Failed to run Mmtests plugin: bad http response {response.status_code} when fetching file at {url}")
                continue

            data = response.content
            filename = url.replace(attachments_url, "")
            if 0 in [len(filename), len(data)]:
                logger.error(f"Failed to run Mmtests plugin: file name or content is empty: filename '{filename}', content '{data}'")
                continue

            attachment = testrun.attachments.create(filename=filename, length=len(data))
            attachment.save_file(filename, data)
