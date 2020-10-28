import logging
import os
import requests
import tarfile
import xmlrpc
import yaml
import xml.etree.ElementTree as ET
#from celery import chord as celery_chord
from io import BytesIO
from django.conf import settings
from django.db import transaction
from squad.plugins import Plugin as BasePlugin
from urllib.parse import urljoin
#from squad.celery import app as celery
from squad.core.utils import join_name
from squad.core.models import Suite, SuiteMetadata, Test, KnownIssue, Status, TestRun, ProjectStatus
from squad.core.tasks import get_suite


logger = logging.getLogger()


#@celery.task
def update_build_status(results_list, testrun_id):
    testrun = TestRun.objects.get(pk=testrun_id)
    ProjectStatus.create_or_update(testrun.build)


#@celery.task
def create_testcase_tests(test_case_string, atomic_test_suite_name, testrun_id, suite_id):
    test_case = ET.fromstring(test_case_string)
    testrun = TestRun.objects.get(pk=testrun_id)
    suite = Suite.objects.get(pk=suite_id)
    local_status = {
        'tests_pass': 0,
        'tests_xfail': 0,
        'tests_fail': 0,
        'tests_skip': 0
    }
    issues = {}
    for issue in KnownIssue.active_by_environment(testrun.environment):
        issues.setdefault(issue.test_name, [])
        issues[issue.test_name].append(issue)

    test_case_name = test_case.get("name")
    tests = test_case.findall('.//Test')
    logger.debug("Extracting TestCase: {test_case_name}".format(test_case_name=test_case_name))
    logger.debug("Adding {} testcases".format(len(tests)))
    test_list = []
    for atomic_test in tests:
        atomic_test_result = atomic_test.get("result")
        decoded_test_result = atomic_test_result == 'pass'
        if atomic_test_result == 'skip' or atomic_test.get("skipped") == "true":
            decoded_test_result = None
        atomic_test_name = "{test_case_name}.{test_name}".format(test_case_name=test_case_name, test_name=atomic_test.get("name"))
        atomic_test_log = ""
        trace_node = atomic_test.find('.//StackTrace')
        if trace_node is not None:
            atomic_test_log = trace_node.text

        metadata, _ = SuiteMetadata.objects.get_or_create(suite=atomic_test_suite_name, name=atomic_test_name, kind='test')
        full_name = join_name(suite.slug, atomic_test_name)
        test_issues = issues.get(full_name, [])
        test_list.append(Test(
            test_run=testrun,
            suite=suite,
            metadata=metadata,
            result=decoded_test_result,
            log=atomic_test_log,
            has_known_issues=bool(test_issues),
        ))
        if decoded_test_result is True:
            local_status['tests_pass'] += 1
        elif decoded_test_result is False:
            if test_issues:
                local_status['tests_xfail'] += 1
            else:
                local_status['tests_fail'] += 1
        else:
            local_status['tests_skip'] += 1
    created_tests = Test.objects.bulk_create(test_list)
    for test in created_tests:
        if test.name in issues.keys():
            test.known_issues.add(issues[test.name])

    with transaction.atomic():
        tr_status = testrun.status.select_for_update().get(suite=None)
        tr_status.tests_pass += local_status['tests_pass']
        tr_status.tests_xfail += local_status['tests_xfail']
        tr_status.tests_fail += local_status['tests_fail']
        tr_status.tests_skip += local_status['tests_skip']
        tr_status.save()
    suite_status, _ = Status.objects.get_or_create(test_run=testrun, suite=suite)
    with transaction.atomic():
        suite_status_for_update = Status.objects.select_for_update().get(pk=suite_status.pk)
        suite_status_for_update.tests_pass += local_status['tests_pass']
        suite_status_for_update.tests_xfail += local_status['tests_xfail']
        suite_status_for_update.tests_fail += local_status['tests_fail']
        suite_status_for_update.tests_skip += local_status['tests_skip']
        suite_status_for_update.save()


class PaginatedObjectException(Exception):
    pass


class ExtractedResult(object):
    contents = None
    length = None
    name = None
    mimetype = None


class ResultFiles(object):
    test_results = None
    test_result_xslt = None
    test_result_css = None
    test_result_image = None
    tradefed_logcat = None
    tradefed_stdout = None
    tradefed_zipfile = None


class Tradefed(BasePlugin):
    name = "Tradefed"
    tradefed_results_url = None

    def __iterate_test_names(self, tradefed_tree, test_suite_name_list, test_name_list, join_char):
        prefix_string = "/".join(test_suite_name_list[2:])
        prefixes = prefix_string.split(".")
        for index in range(0, len(prefixes)):
            test_name = ".".join(prefixes[index:]) + join_char + ".".join(test_name_list)
            logger.debug("searching for test: %s" % test_name)
            log_node = tradefed_tree.find('.//Test[@name="%s"]' % test_name)
            if log_node is not None:
                return log_node

    def _convert_paths(self, testrun, results):
        base_url = settings.BASE_URL
        results_stringio = BytesIO()
        for line in results.test_results.contents:
            line_to_write = line.decode().replace(
                "compatibility_result.xsl",
                "{base_url}/{group_slug}/{project_slug}/build/{build_version}/attachments/testrun/{testrun_id}/compatibility_result.xsl".format(
                    base_url=base_url,
                    group_slug=testrun.build.project.group.slug,
                    project_slug=testrun.build.project.slug,
                    build_version=testrun.build.version,
                    testrun_id=testrun.id)
            )
            results_stringio.write(line_to_write.encode('utf-8'))
        results_stringio.seek(0, os.SEEK_END)
        results.test_results.length = results_stringio.tell()
        results_stringio.seek(0)
        results.test_results.contents = results_stringio
        if results.test_result_xslt is not None:
            result_xslt_stringio = BytesIO()
            for line in results.test_result_xslt.contents:
                result_xslt_stringio.write(
                    line.decode().replace(
                        "compatibility_result.css",
                        "{base_url}/{group_slug}/{project_slug}/build/{build_version}/attachments/testrun/{testrun_id}/compatibility_result.css".format(
                            base_url=base_url,
                            group_slug=testrun.build.project.group.slug,
                            project_slug=testrun.build.project.slug,
                            build_version=testrun.build.version,
                            testrun_id=testrun.id)
                        ).replace("logo.png", "{base_url}/{group_slug}/{project_slug}/build/{build_version}/attachments/testrun/{testrun_id}/logo.png".format(
                            base_url=base_url,
                            group_slug=testrun.build.project.group.slug,
                            project_slug=testrun.build.project.slug,
                            build_version=testrun.build.version,
                            testrun_id=testrun.id)
                        ).encode('utf-8')
                    )
            result_xslt_stringio.seek(0, os.SEEK_END)
            results.test_result_xslt.length = result_xslt_stringio.tell()
            result_xslt_stringio.seek(0)
            results.test_result_xslt.contents = result_xslt_stringio


    def __parse_xml_results(self, buf):
        if buf is None:
            logger.warning("Results file doesn't exist")
            return None
        # assume buf is a file-like object
        tradefed_tree = None
        try:
            tradefed_tree = ET.parse(buf)
        except ET.ParseError as e:
            logger.warning(e)
            return None
        buf.seek(0)
        return tradefed_tree

    def _extract_cts_results(self, buf, testrun, suite_prefix):
        tradefed_tree = self.__parse_xml_results(buf)
        if tradefed_tree is None:
            return

        issues = {}
        for issue in KnownIssue.active_by_environment(testrun.environment):
            issues.setdefault(issue.test_name, [])
            issues[issue.test_name].append(issue)

        test_elems = tradefed_tree.findall(".//Test")
        logger.debug("Tests: {}".format(len(test_elems)))
        elems = tradefed_tree.findall('Module')
        logger.debug("Modules: {}".format(len(elems)))
        #task_list = []
        for elem in elems:
            # Naming: Module Name + Test Case Name + Test Name
            if 'abi' in elem.attrib.keys():
                module_name = '.'.join([elem.attrib['abi'], elem.attrib['name']])
            else:
                module_name = elem.attrib['name']
            logger.debug("Extracting tests for module: {}".format(module_name))
            test_cases = elem.findall('.//TestCase')
            suite_metadata_list = []
            suite_list = []
            logger.debug("Extracting suite names")
            atomic_test_suite_name = "{suite_prefix}/{module_name}".format(suite_prefix=suite_prefix, module_name=module_name)
            logger.debug("creating suite metadata: {}".format(atomic_test_suite_name))
            suite_metadata, _ = SuiteMetadata.objects.get_or_create(suite=atomic_test_suite_name, kind='suite')
            suite, _ = Suite.objects.get_or_create(slug=atomic_test_suite_name, project=testrun.build.project, defaults={"metadata": suite_metadata})
            #logger.debug("Adding status with suite: {suite_prefix}/{module_name}".format(suite_prefix=suite_prefix, module_name=module_name))
            #logger.debug("Creating subtasks for extracting results")
            #task_list = task_list + [create_testcase_tests.s(ET.tostring(test_case, encoding="utf-8"), module_name, testrun.pk, suite.pk) for test_case in test_cases]
            for test_case in test_cases:
                create_testcase_tests(ET.tostring(test_case, encoding="utf-8"), atomic_test_suite_name, testrun.pk, suite.pk)

        #celery_chord(task_list)(update_build_status.s(testrun.pk))

    def _assign_test_log(self, buf, test_list):
        # assume buf is a file-like object
        logger.debug("About to parse XML from buffer")
        tradefed_tree = self.__parse_xml_results(buf)
        if tradefed_tree is None:
            return
        for test in test_list:
            # search in etree for relevant test
            logger.debug("processing %s/%s" % (test.suite, test.name))
            test_suite_name_list = str(test.suite).split("/")
            if len(test_suite_name_list) <= 1:
                # assume that test results produced by LAVA
                # and test-definitions always contain at least one "/"
                continue
            test_suite_name = test_suite_name_list[1]
            test_suite_abi = None
            if "." in test_suite_name:
                test_suite_abi, test_suite_name = test_suite_name.split(".")
            test_name_list = test.name.rsplit(".")
            test_name = test_name_list[-1]
            logger.debug("searching for %s log" % test_name)
            suite_node = None
            if test_suite_abi is not None:
                # Module name="VtsKernelLtp" abi="armeabi-v7a"
                suite_node = tradefed_tree.find('.//Module[@name="%s"][@abi="%s"]' % (test_suite_name, test_suite_abi))
            else:
                suite_node = tradefed_tree.find('.//Module[@name="%s"]' % (test_suite_name))
            if not suite_node:
                logger.debug("Module %s is not present in the log" % test_suite_name)
                continue
            log_node = suite_node.find('.//Test[@name="%s"]' % test_name)
            if log_node is None:
                test_name = ".".join(test_name_list[1:])
                logger.debug("searching for test: %s" % test_name)
                log_node = tradefed_tree.find('.//Test[@name="%s"]' % test_name)
            if log_node is None:
                log_node = self.__iterate_test_names(tradefed_tree, test_suite_name_list, test_name_list, ".")
            if log_node is None:
                log_node = self.__iterate_test_names(tradefed_tree, test_suite_name_list, test_name_list, "/")

            if log_node is not None:
                trace_node = log_node.find('.//StackTrace')
                if trace_node is not None:
                    test.log = trace_node.text
                    test.save()

    def _extract_member(self, tar_file, tar_member):
        extracted_container = ExtractedResult()
        extracted_container.contents = tar_file.extractfile(tar_member)
        extracted_container.length = tar_member.size
        return extracted_container

    def _download_results(self, result_dict):
        results = ResultFiles()
        if 'metadata' in result_dict:
            if 'reference' in result_dict['metadata']:
                try:
                    logger.debug("Downloading CTS/VTS log from: %s" % result_dict['metadata']['reference'])
                    self.tradefed_results_url = result_dict['metadata']['reference']
                    result_tarball_request = requests.get(self.tradefed_results_url)
                    if result_tarball_request.status_code == 200:
                        result_tarball_request.raw.decode_content = True
                        r = BytesIO(result_tarball_request.content)
                        results.tradefed_zipfile = ExtractedResult()
                        results.tradefed_zipfile.contents = r
                        results.tradefed_zipfile.length = len(result_tarball_request.content)
                        results.tradefed_zipfile.name = result_tarball_request.url.rsplit("/", 1)[1]
                        results.tradefed_zipfile.mimetype = result_tarball_request.headers.get("Content-Type")
                        logger.debug("Retrieved %s bytes" % r.getbuffer().nbytes)
                        t = tarfile.open(fileobj=r, mode='r:xz')
                        for member in t.getmembers():
                            logger.debug("Available member: %s" % member.name)
                            if "test_result.xml" in member.name:
                                results.test_results = self._extract_member(t, member)
                                logger.debug("test_results object is empty: %s" % (results.test_results is None))
                            if "compatibility_result.xsl" in member.name:
                                results.test_result_xslt = self._extract_member(t, member)
                                logger.debug("test_result_xslt object is empty: %s" % (results.test_result_xslt is None))
                            if "compatibility_result.css" in member.name:
                                results.test_result_css = self._extract_member(t, member)
                                logger.debug("test_result_css object is empty: %s" % (results.test_result_css is None))
                            if "logo.png" in member.name:
                                results.test_result_image = self._extract_member(t, member)
                                logger.debug("test_result_image object is empty: %s" % (results.test_result_image is None))
                            if "tradefed-stdout.txt" in member.name:
                                results.tradefed_stdout = self._extract_member(t, member)
                                logger.debug("tradefed_stdout object is empty: %s" % (results.tradefed_stdout is None))
                            if "tradefed-logcat.txt" in member.name:
                                results.tradefed_logcat = self._extract_member(t, member)
                                logger.debug("tradefed_logcat object is empty: %s" % (results.tradefed_logcat is None))
                except tarfile.TarError as e:
                    logger.warning(e)
                except EOFError as e:
                    # this can happen when tarfile is corrupted
                    logger.warning(e)
                except requests.exceptions.Timeout as e:
                    logger.warning(e)
        return results

    def __get_paginated_objects(self, url, lava_implementation):
        # this method only applies to REST API
        object_request = requests.get(url, headers=lava_implementation.authentication)
        objects = []
        if object_request.status_code == 200:
            object_list = object_request.json()
            objects = object_list['results']
            while object_list['next']:
                object_request = requests.get(object_list['next'], headers=lava_implementation.authentication)
                if object_request.status_code == 200:
                    object_list = object_request.json()
                    objects = objects + object_list['results']
                else:
                    # don't raise exception as some results were extracted
                    break
        else:
            raise PaginatedObjectException()
        return objects

    def _get_from_artifactorial(self, testjob, suite_name):
        logger.debug("Retrieving result summary for job: %s" % testjob.job_id)
        suites = None
        lava_implementation = testjob.backend.get_implementation()
        if lava_implementation.use_xml_rpc:
            suites = lava_implementation.proxy.results.get_testjob_suites_list_yaml(testjob.job_id)
            try:
                suites = yaml.load(suites, Loader=yaml.CLoader)
            except yaml.parser.ParserError as e:
                logger.warning(e)
                return None

            if not suites:
                logger.debug("Something went wrong when calling results.get_testjob_suites_list_yaml from LAVA")
                return None
        else:
            suites_url = urljoin(testjob.backend.get_implementation().api_url_base, "jobs/{job_id}/suites/?name__contains={suite_name}".format(job_id=testjob.job_id, suite_name=suite_name))
            try:
                suites = self.__get_paginated_objects(suites_url, lava_implementation)
            except PaginatedObjectException:
                logger.error("Unable to retrieve suites for job: {job_id}".format(job_id=testjob.job_id))
                return None

        for suite in suites:
            if suite_name in suite['name']:
                if lava_implementation.use_xml_rpc:
                    limit = 500
                    offset = 0
                    results = testjob.backend.get_implementation().proxy.results.get_testsuite_results_yaml(
                        testjob.job_id,
                        suite['name'],
                        limit,
                        offset)
                    yaml_results = None
                    try:
                        yaml_results = yaml.load(results, Loader=yaml.CLoader)
                    except yaml.scanner.ScannerError as e:
                        logger.warning(e)
                        return None

                    if not yaml_results:
                        logger.debug("Something went wrong with results.get_testsuite_results_yaml from LAVA")
                        return None

                    while True:
                        if len(yaml_results) > 0:
                            for result in yaml_results:
                                if result['name'] == 'test-attachment':
                                    return self._download_results(result)
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
                else:
                    test_attachment_url = urljoin(testjob.backend.get_implementation().api_url_base, "jobs/{job_id}/suites/{suite_id}/tests/?name=test-attachment".format(job_id=testjob.job_id, suite_id=suite['id']))
                    test_attachment_request = requests.get(test_attachment_url, headers=lava_implementation.authentication)
                    if test_attachment_request.status_code == 200:
                        test_attachmet_results = test_attachment_request.json()
                        for test_result in test_attachmet_results['results']:
                            # there should be only one
                            metadata = yaml.load(test_result['metadata'], Loader=yaml.CLoader)
                            if 'reference' in metadata.keys():
                                test_result['metadata'] = metadata
                                return self._download_results(test_result)
        return None

    def _create_testrun_attachment(self, testrun, name, extracted_file, mimetype):
        extracted_file.contents.seek(0, os.SEEK_END)
        logger.debug("creating attachment with name: %s" % name)
        logger.debug("actual file size: %s" % extracted_file.contents.tell())
        extracted_file.contents.seek(0)

        testrun.attachments.create(
            filename = name,
            data = extracted_file.contents.read(),
            length = extracted_file.length,
            mimetype = mimetype
        )

    def postprocess_testjob(self, testjob):
        # get related testjob
        logger.info("Starting CTS/VTS plugin for test job: %s" % testjob)
        logging.debug("Processing test job: %s" % testjob)
        if not testjob.backend.implementation_type == 'lava':
            logger.warning("Test job %s doesn't come from LAVA" % testjob)
            logger.debug(testjob.backend.implementation_type)
            return # this plugin only applies to LAVA
        # check if testjob is a tradefed job
        if testjob.definition:
            logger.debug("Loading test job definition")
            job_definition = yaml.load(testjob.definition, Loader=yaml.CLoader)
            # find all tests
            if 'actions' in job_definition.keys():
                for test_action in [action for action in job_definition['actions'] if'test' in action.keys()]:
                    if 'definitions' not in test_action['test'].keys():
                        continue
                    for test_definition in test_action['test']['definitions']:
                        logger.debug("Processing test %s" % test_definition['name'])
                        if "tradefed.yaml" in test_definition['path']:  # is there any better heuristic?
                            # download and parse results
                            results = None
                            try:
                                results = self._get_from_artifactorial(testjob, test_definition['name'])
                            except xmlrpc.client.ProtocolError as err:
                                logger.error(err.errcode)
                                logger.error(err.errmsg)

                            logger.debug("Processing results")
                            if results is not None:
                                # add metadata key for taball download
                                testjob.testrun.metadata["tradefed_results_url_%s" % testjob.job_id] = self.tradefed_results_url
                                logger.debug("about to save testrun")
                                testjob.testrun.save()
                                logger.debug("testrun saved")
                                # only failed tests have logs
                                if testjob.testrun is not None:
                                    ps = None
                                    if testjob.target.project_settings is not None:
                                        ps = yaml.safe_load(testjob.target.project_settings)
                                    if ps and ps.get("PLUGINS_TRADEFED_EXTRACT_AGGREGATED", False) and \
                                            'params' in test_definition.keys() and \
                                            ('RESULTS_FORMAT' not in test_definition['params'] or ('RESULTS_FORMAT' in test_definition['params'] and test_definition['params']['RESULTS_FORMAT'] == 'aggregated')):
                                        # extract_cts_results also assigns the log
                                        if results.test_results is not None:
                                            self._extract_cts_results(results.test_results.contents, testjob.testrun, test_definition['name'])
                                    else:
                                        failed = testjob.testrun.tests.filter(result=False)
                                        if results.test_results is not None:
                                            self._assign_test_log(results.test_results.contents, failed)
                                    if results.test_results is not None:
                                        self._convert_paths(testjob.testrun, results)
                                        self._create_testrun_attachment(testjob.testrun, "test_results.xml", results.test_results, "application/xml")
                                    if results.test_result_xslt is not None:
                                        self._create_testrun_attachment(testjob.testrun, "compatibility_result.xsl", results.test_result_xslt, "application/xslt+xml")
                                    if results.test_result_css is not None:
                                        self._create_testrun_attachment(testjob.testrun, "compatibility_result.css", results.test_result_css, "text/css")
                                    if results.test_result_image is not None:
                                        self._create_testrun_attachment(testjob.testrun, "logo.png", results.test_result_image, "image/png")
                                    if results.tradefed_stdout is not None:
                                        self._create_testrun_attachment(testjob.testrun, "teadefed_stdout.txt", results.tradefed_stdout, "text/plain")
                                    if results.tradefed_logcat is not None:
                                        self._create_testrun_attachment(testjob.testrun, "teadefed_logcat.txt", results.tradefed_logcat, "text/plain")
                                    if results.tradefed_zipfile is not None:
                                        if results.tradefed_zipfile.mimetype is None:
                                            results.tradefed_zipfile.mimetype = "application/x-tar"
                                        if results.tradefed_zipfile.name is None:
                                            results.tradefed_zipfile.name = "tradefed.tar.gz"
                                        self._create_testrun_attachment(testjob.testrun, results.tradefed_zipfile.name, results.tradefed_zipfile, results.tradefed_zipfile.mimetype)
        logger.info("Finishing CTS/VTS plugin for test run: %s" % testjob)


