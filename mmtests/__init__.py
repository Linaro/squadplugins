from squad.plugins import Plugin as BasePlugin


class Mmtests(BasePlugin):
    name = "Mmtests"

    def postprocess_testjob(self, testjob):
        if testjob.backend.implementation_type == 'tuxsuite':
            testrun = testjob.testrun
            tuxsuite = testjob.backend.get_implementation()
            job_url = tuxsuite.job_url(testjob)
            # Retrieve TuxSuite attachments
            attachment_json = tuxsuite.fetch_url(job_url + '/attachments/').json()
            for file_url in [f['Url'] for f in attachment_json['files'] if f['Url']]:
                response = tuxsuite.fetch_url(file_url)
                if response.status_code != 200:
                    # TOOD: Check return code from tuxsuite
                    continue
                data = response.content
                filename = file_url.split("/attachments/", 2)[1]
                if not filename:
                    continue
                attachment = testrun.attachments.create(filename=filename, length=len(data))
                attachment.save_file(filename, data)
