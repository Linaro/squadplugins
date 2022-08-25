import logging
from multiprocessing import Pool
from squad.plugins import Plugin as BasePlugin


logger = logging.getLogger()

log_lines = None
test_names = None

def extract_test_log(test_id):
    test_name = test_names[test_id]
    logger.debug("Assigning LTP logs to %s" % test_name)
    matches = []
    for line in log_lines:
        if not line.startswith(test_name):
            continue

        logger.debug("Found log line for test: %s" % test_name)
        logger.debug(line)
        matches.append(line)

    logs = '\n'.join(matches) if len(matches) else None
    return (test_id, logs)


class LtpLogs(BasePlugin):
    name = "LTP Logs"

    def postprocess_testrun(self, testrun):
        global log_lines
        global test_names

        log_lines = testrun.log_file.split('\n')

        tests = {}
        test_names = {}
        for t in testrun.tests.filter(result=False):
            tests[t.id] = t
            test_names[t.id] = t.name

        results = None
        with Pool() as pool:
            results = pool.map(extract_test_log, test_names.keys())

        for result in results:
            test_id, log = result
            if log is None:
                continue
            logger.debug(f'Saving test {t.id}')
            if tests[test_id].log is None:
                tests[test_id].log = ''
            tests[test_id].log += log
            tests[test_id].save()
