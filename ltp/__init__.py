import logging
from squad.plugins import Plugin as BasePlugin


logger = logging.getLogger()


class LtpLogs(BasePlugin):
    name = "LTP Logs"

    def postprocess_testrun(self, testrun):
        log_lines = testrun.log_file.split('\n')
        for test in testrun.tests.filter(result=False):
            logger.debug("Assigning LTP logs to %s" % test.name)
            log = [line for line in log_lines if line.startswith(test.name)]

            if len(log) > 0:
                if test.log is not None:
                    log = [test.log] + log
                test.log = '\n'.join(log)
                test.save()
