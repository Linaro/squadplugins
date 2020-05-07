import logging
import re
from squad.plugins import Plugin as BasePlugin


logger = logging.getLogger()


class LtpLogs(BasePlugin):
    name = "LTP Logs"

    def postprocess_testrun(self, testrun):
        for test in testrun.tests.filter(result=False):
            logger.debug("Assigning LTP logs to %s" % test.name)
            regex = re.compile("^%s.*$" % re.escape(test.name), re.MULTILINE)
            log_results = regex.findall(testrun.log_file)
            for match in log_results:
                logger.debug("Found log line for test: %s" % test.name)
                logger.debug(match)
                if test.log is None:
                    test.log = match
                else:
                    test.log = test.log + "\r" + match
                test.save()

