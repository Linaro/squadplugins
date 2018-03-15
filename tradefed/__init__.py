import logging
import requests
import tarfile
import yaml
import xml.etree.ElementTree as ET
from io import BytesIO
from squad.plugins import Plugin as BasePlugin


logger = logging.getLogger()


class Tradefed(BasePlugin):
    name = "Tradefed"

    def __assign_test_log(self, buf, test_list):
        if buf is None:
            logger.warning("Results file doesn't exist")
            return
        # assume buf is a file-like object
        tradefed_tree = ET.parse(buf)
        for test in test_list:
            # search in etree for relevant test
            logger.debug("processing %s/%s" % (test.suite, test.name))
            test_suite_name_list = str(test.suite).split("/")
            test_suite_name = test_suite_name_list[-1]
            test_suite_abi = None
            if "." in test_suite_name:
                test_suite_abi, test_suite_name = test_suite_name.split(".")
            test_name_list = test.name.rsplit(".")
            test_name = test_name_list[-1]
            logger.debug("searching for %s log" % test_name)
            if test_suite_abi is not None:
                # Module name="VtsKernelLtp" abi="armeabi-v7a"
                suite_node = tradefed_tree.find('.//Module[@name="%s"][@abi="%s"]' % (test_suite_name, test_suite_abi))
            else:
                suite_node = tradefed_tree.find('.//Module[@name="%s"]' % (test_suite_name))
            log_node = suite_node.find('.//Test[@name="%s"]' % test_name)
            if log_node is None:
                test_name = test_name_list[-2] + "." + test_name
                logger.debug("searching for %s log" % test_name)
                log_node = tradefed_tree.find('.//Test[@name="%s"]' % test_name)

            if log_node is not None:
                trace_node = log_node.find('.//StackTrace')
                if trace_node is not None:
                    test.log = trace_node.text
                    test.save()


    def __download_results(self, result_dict):
        if 'metadata' in result_dict:
            if 'reference' in result_dict['metadata']:
                try:
                    logger.debug("Downloading CTS/VTS log from: %s" % result_dict['metadata']['reference'])
                    result_tarball_request = requests.get(result_dict['metadata']['reference'])
                    if result_tarball_request.status_code == 200:
                        result_tarball_request.raw.decode_content = True
                        r = BytesIO(result_tarball_request.content)
                        logger.debug("Retrieved %s bytes" % r.getbuffer().nbytes)
                        t = tarfile.open(fileobj=r, mode='r:xz')
                        for member in t.getmembers():
                            logger.debug("Available member: %s" % member.name)
                            if "test_result.xml" in member.name:
                                buf = t.extractfile(member)
                                logger.debug("buf object is empty: %s" % (buf is None))
                                return buf
                except tarfile.ReadError:
                    return None
                except requests.exceptions.Timeout:
                    return None
        return None

    def __get_from_artifactorial(self, testjob, suite_name):
        logger.debug("Retrieving result summary for job: %s" % testjob.job_id)
        suites = testjob.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml(testjob.job_id)
        y = yaml.load(suites)
        for suite in y:
            if suite_name in suite['name']:
                limit = 500
                offset = 0
                results = testjob.backend.get_implementation().proxy.results.get_testsuite_results_yaml(
                    testjob.job_id,
                    suite['name'],
                    limit,
                    offset)
                yaml_results = yaml.load(results, Loader=yaml.CLoader)
                while True:
                    if len(yaml_results) > 0:
                        for result in yaml_results:
                            if result['name'] == 'test-attachment':
                                return self.__download_results(result)
                        offset = offset + limit
                        logger.debug("requesting results for %s with offset of %s"
                                     % (suite['name'], offset))
                        results = testjob.backend.get_implementation().proxy.results.get_testsuite_results_yaml(
                            testjob.job_id,
                            suite['name'],
                            limit,
                            offset)
                        yaml_results = yaml.load(results, Loader=yaml.CLoader)
                    else:
                        break

    def postprocess_testjob(self, testjob):
        # get related testjob
        logger.info("Starting CTS/VTS plugin for test job: %s" % testjob.pk)
        logging.debug("Processing test job: %s" % testjob.job_id)
        if not testjob.backend.implementation_type == 'lava':
            logger.warning("Test job %s doesn't come from LAVA" % testjob.job_id)
            logger.debug(testjob.backend.implementation_type)
            return # this plugin only applies to LAVA
        # check if testjob is a tradefed job
        if testjob.definition:
            logger.debug("Loading test job definition")
            job_definition = yaml.load(testjob.definition)
            # find all tests
            if 'actions' in job_definition.keys():
                for test_action in [action for action in job_definition['actions'] if'test' in action.keys()]:
                    for test_definition in test_action['test']['definitions']:
                        logger.debug("Processing test %s" % test_definition['name'])
                        if "tradefed.yaml" in test_definition['path']:  # is there any better heuristic?
                            # download and parse results
                            buf = self.__get_from_artifactorial(testjob, test_definition['name'])
                            # only failed tests have logs
                            if testjob.testrun is not None:
                                failed = testjob.testrun.tests.filter(result=False)
                                self.__assign_test_log(buf, failed)
        logger.info("Finishing CTS/VTS plugin for test run: %s" % testjob.pk)


