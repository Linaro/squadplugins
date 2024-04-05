import logging
import os
import re
import requests
import tarfile
import xmlrpc
import yaml
import json
import xml.etree.ElementTree as ET
from celery import chord as celery_chord
from django.conf import settings
from io import BytesIO
from requests.adapters import HTTPAdapter, Retry
from squad.core.models import Suite, SuiteMetadata, PluginScratch, KnownIssue, TestRun
from squad.ci.tasks import update_testjob_status
from squad.plugins import Plugin as BasePlugin
from urllib.parse import urljoin, urlparse, parse_qs

from .tasks import create_testcase_tests, update_build_status


logger = logging.getLogger()
__session__ = None


def get_session():
    global __session__
    if __session__ is None:
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        __session__ = requests.Session()
        __session__.mount('http://', adapter)
        __session__.mount('https://', adapter)
    return __session__


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

    def has_subtasks(self):
        return True

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
        base_url = f"{settings.BASE_URL}/{testrun.build.project.group.slug}/{testrun.build.project.slug}/build/{testrun.build.version}/attachments/testrun/{testrun.id}"
        results_stringio = BytesIO()
        for line in results.test_results.contents:
            line_to_write = line.decode().replace("compatibility_result.xsl", f"{base_url}/compatibility_result.xsl")
            results_stringio.write(line_to_write.encode('utf-8'))
        results_stringio.seek(0, os.SEEK_END)
        results.test_results.length = results_stringio.tell()
        results_stringio.seek(0)
        results.test_results.contents = results_stringio
        if results.test_result_xslt is None:
            return

        result_xslt_stringio = BytesIO()
        for line in results.test_result_xslt.contents:
            result_xslt_stringio.write(line.decode().replace("compatibility_result.css", f"{base_url}/compatibility_result.css").replace("logo.png", f"{base_url}/logo.png").encode('utf-8'))
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

    def _enqueue_testcases_chunk(self, testcases, testrun, suite):
        plugin_scratch = PluginScratch.objects.create(
            build=testrun.build,
            storage=json.dumps(testcases),
        )

        logger.debug(f"Created plugin scratch with ID: {plugin_scratch}")
        task = create_testcase_tests.s(plugin_scratch.id, suite.slug, testrun.id, suite.id)
        del plugin_scratch
        return task

    def _extract_cts_results(self, buf, testrun, suite_prefix):
        """
            This function reads in buf and iteractively parses the XML file so that
            it does not eat up lots of memory (+1G). The tags are grouped in chunks
            of 1000 TestCase and then sent to the queue for sub-tasks to process them.

            The PluginScratch serves as a helper to share data among the sub-tasks. Data
            will be transformed to JSON when saved to plugin scratch.
        """

        chunk_size = 100
        module_name = ''
        testcases = []
        testcase = None
        test = None
        task_list = []
        suite = None
        suite_slug = ''

        try:
            for event, element in ET.iterparse(buf, events=['start']):
                if element.tag == 'Module':

                    # When changing modules, enqueue whatever testcases might be in buffer
                    if len(testcases) > 0:
                        task = self._enqueue_testcases_chunk(testcases, testrun, suite)
                        task_list.append(task)
                        testcases = []

                    module_name = element.attrib['name']
                    logger.debug(f"Module: {module_name}")

                    if 'abi' in element.attrib.keys():
                        module_name = element.attrib['abi'] + '.' + module_name

                    suite_slug = f"{suite_prefix}/{module_name}"
                    logger.debug(f"Creating suite metadata: {suite_slug}")

                    metadata, _ = SuiteMetadata.objects.get_or_create(suite=suite_slug, kind='suite')
                    suite, _ = Suite.objects.get_or_create(slug=suite_slug, project=testrun.build.project, defaults={"metadata": metadata})

                if element.tag == 'TestCase':
                    # Check if there's enough test cases to send to the queue
                    if len(testcases) == chunk_size:
                        logger.debug(f'Enqueueing {len(testcases)} TestCase tags')
                        task = self._enqueue_testcases_chunk(testcases, testrun, suite)
                        task_list.append(task)
                        testcases = []

                    testcase = element.attrib
                    testcase['tests'] = []
                    testcase['suite'] = suite_slug
                    testcases.append(testcase)

                if element.tag == 'Test':
                    test = element.attrib
                    testcase['tests'].append(test)

                    if test.get("result") == "ASSUMPTION_FAILURE":

                        # ASSUMPTION_FAILURE will be added to the known issues list so they can show up
                        # as xfail tests
                        test_full_name = f"{suite_slug}/{testcase.get('name')}.{test.get('name')}"
                        issue, _ = KnownIssue.objects.get_or_create(
                            title=f'Tradefed/{test_full_name}',
                            test_name=test_full_name,
                        )

                        issue.environments.add(testrun.environment)
                        issue.save()

                if element.tag == 'StackTrace':
                    test['log'] = element.text

                # Release tag resources
                element.clear()

        except ET.ParseError as e:
            logger.error(f"[CTS/VTS] Error extracting cases: {e}")
            return None

        # Process remaining test cases that didn't make to the last chunk
        if len(testcases) > 0:
            task = self._enqueue_testcases_chunk(testcases, testrun, suite)
            task_list.append(task)

        celery_chord(task_list)(update_build_status.s(testrun.pk, self.extra_args.get("job_id"), self.extra_args.get("job_status")))

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

    def _extract_tarball_filename_from_url(self, url):
        # Tradefed filename regex
        regex = re.compile(r".*?([\w.-]+tar.xz)$")

        # Look at url path
        parsed = urlparse(url)
        candidate_filename = os.path.basename(parsed.path)
        logger.debug(f"Looking for filename in {candidate_filename}")
        matches = regex.match(candidate_filename)
        if matches is not None:
            return matches.group(1)

        # Look at any querystring parameter
        logger.debug(f"Looking for filename in {parsed.query}")
        query = parse_qs(parsed.query)
        for _, values in query.items():
            for value in values:
                if regex.match(value):
                    return value

        logger.debug("Giving up trying to look for tradefed filename in {url}")
        return None

    def _download_results(self, url):
        results = ResultFiles()
        session = get_session()
        try:
            logger.debug(f"Downloading CTS/VTS log from: {url}")
            self.tradefed_results_url = url

            contents = None
            mime_type = None
            filename = None
            if url.startswith(settings.BASE_URL):
                regex = r".*?/testruns/(\d+)/attachments/?\?filename=(.*?)$"
                matches = re.match(regex, url)
                if matches is None:
                    logger.error(f"The tradefed url \"{url}\" belongs to this instance of SQUAD, but it does not look valid")
                    return results

                testrun_id, filename = matches.groups()

                queryset = TestRun.objects.filter(id=testrun_id)
                if not queryset.exists():
                    logger.error(f"The tradefed url \"{url}\" belongs to this instance of SQUAD, but this testrun does not exist")
                    return results

                testrun = queryset.first()
                attachments = testrun.attachments.filter(filename=filename)
                if attachments.count() == 0:
                    logger.error(f"The tradefed url \"{url}\" belongs to this instance of SQUAD, but the attachment does not exist within the testrun")
                    return results

                attachment = attachments.first()
                contents = attachment.data
                mime_type = attachment.mimetype
                filename = os.path.basename(attachment.filename)

            else:
                response = session.get(self.tradefed_results_url)
                if response.status_code != 200:
                    logger.error(f"Failed to download tradefed file {self.tradefed_results_url}")
                    return results

                response.raw.decode_content = True
                contents = response.content
                filename = self._extract_tarball_filename_from_url(response.url)
                mime_type = response.headers.get("Content-Type")

            r = BytesIO(contents)
            results.tradefed_zipfile = ExtractedResult()
            results.tradefed_zipfile.contents = r
            results.tradefed_zipfile.length = len(contents)
            results.tradefed_zipfile.name = filename
            results.tradefed_zipfile.mimetype = mime_type

            logger.debug(f"Retrieved {results.tradefed_zipfile.length} bytes")

            t = tarfile.open(fileobj=r, mode='r:xz')
            for member in t.getmembers():

                logger.debug(f"Available member: {member.name}")
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

            logger.debug('Done extracting members')
        except tarfile.TarError as e:
            logger.error(e)
        except EOFError as e:
            # this can happen when tarfile is corrupted
            logger.error(e)
        except requests.exceptions.Timeout as e:
            logger.error(e)
        return results

    def __get_paginated_objects(self, url, lava_implementation):
        session = get_session()
        # this method only applies to REST API
        object_request = session.get(url, headers=lava_implementation.authentication)
        objects = []
        if object_request.status_code == 200:
            object_list = object_request.json()
            objects = object_list['results']
            while object_list['next']:
                object_request = session.get(object_list['next'], headers=lava_implementation.authentication)
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
        # TODO: consider Tuxsuite backend
        session = get_session()
        if lava_implementation.use_xml_rpc:
            suites = lava_implementation.proxy.results.get_testjob_suites_list_yaml(testjob.job_id)
            try:
                suites = yaml.load(suites, Loader=yaml.CLoader)
            except yaml.parser.ParserError as e:
                logger.error(f"Failed to parse suited for job {testjob.id}: {e}")
                return None

            if not suites:
                logger.error("Something went wrong when calling results.get_testjob_suites_list_yaml from LAVA for job {testjob.id}")
                return None
        else:
            suites_url = urljoin(testjob.backend.get_implementation().api_url_base, f"jobs/{testjob.job_id}/suites/?name__contains={suite_name}")
            try:
                suites = self.__get_paginated_objects(suites_url, lava_implementation)
            except PaginatedObjectException:
                logger.error("Unable to retrieve suites for job: {testjob.job_id}")
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
                        logger.error(f"Failed to load {suite_name} results for job {testjob.id}: {e}")
                        return None

                    if not yaml_results:
                        logger.error("Something went wrong with results.get_testsuite_results_yaml from LAVA for job {testjob.id}")
                        return None

                    while True:
                        if len(yaml_results) > 0:
                            for result in yaml_results:
                                if result['name'] == 'test-attachment':
                                    if result['result'] == 'pass' and 'reference' in result['metadata']:
                                        return self._download_results(result['metadata']['reference'])
                                    return None
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
                    test_attachment_request = session.get(test_attachment_url, headers=lava_implementation.authentication)
                    if test_attachment_request.status_code == 200:
                        test_attachmet_results = test_attachment_request.json()
                        for test_result in test_attachmet_results['results']:
                            # there should be only one
                            metadata = yaml.load(test_result['metadata'], Loader=yaml.CLoader)
                            if 'reference' in metadata.keys():
                                return self._download_results(metadata['reference'])
        return None

    def _create_testrun_attachment(self, testrun, name, extracted_file, mimetype):
        extracted_file.contents.seek(0, os.SEEK_END)
        logger.debug("creating attachment with name: %s" % name)
        logger.debug("actual file size: %s" % extracted_file.contents.tell())
        extracted_file.contents.seek(0)

        data = extracted_file.contents.read()
        attachment = testrun.attachments.create(
            filename=name,
            length=extracted_file.length,
            mimetype=mimetype
        )

        attachment.save_file(name, data)

    def _extract_tradefed_from_job_definition(self, testjob):
        """
        This function looks up in job definition and return 2 things
          * the tradefed yaml file name
          * the results format

        Here's a snippet of a definition that contain that information

        ```
            actions:
            - test:
                docker:
                  image: linaro/lava-android-test:focal-2024.02.20-01
                  local: true
                timeout:
                  minutes: 900
                definitions:
                - repository: https://github.com/Linaro/test-definitions.git
          >>>>>>> name: cts-lkft
                  from: git
          >>>>>>> path: automated/android/noninteractive-tradefed/tradefed.yaml
                  params:
                    TEST_PARAMS: cts --abi arm64-v8a -m CtsDeqpTestCases --disable-reboot
                    TEST_URL:
                      http://lkft-cache.lkftlab/api/v1/fetch?url=http://testdata.linaro.org/lkft/aosp-stable/android/lkft/lkft-aosp-android13-    cts/2113/android-cts.zip
                    TEST_PATH: android-cts
          >>>>>>>>> RESULTS_FORMAT: aggregated
        ```

        If there is a `tradefed.yaml` in a `test` block, extract `name` and `RESULTS_FORMAT`.

        """

        if not testjob.definition:
            logger.warning("Test job %s doesn't have a definition" % testjob)
            update_testjob_status.delay(testjob.id, self.extra_args.get("job_status"))
            return []

        logger.debug("Loading test job definition")
        job_definition = yaml.load(testjob.definition, Loader=yaml.CLoader)
        if 'actions' not in job_definition.keys():
            logger.warning("Test job %s definition doesn't have 'actions'" % testjob)
            update_testjob_status.delay(testjob.id, self.extra_args.get("job_status"))
            return []

        tradefed_files = []
        test_actions = [a for a in job_definition['actions'] if 'test' in a.keys()]
        for action in test_actions:
            if 'definitions' not in action['test'].keys():
                continue

            for test_definition in action['test']['definitions']:
                if "tradefed.yaml" in test_definition['path']:
                    try:
                        name = test_definition['name']
                        results_format = test_definition['params']['RESULTS_FORMAT']
                        tradefed_files.append((name, results_format))
                    except KeyError:
                        pass

        return tradefed_files

    def postprocess_testjob(self, testjob):
        self.extra_args["job_id"] = testjob.id

        logger.info("Starting CTS/VTS plugin for test job: %s" % testjob)
        if not testjob.backend.implementation_type == 'lava':
            logger.error(f"Test job {testjob.id} doesn't come from LAVA")
            update_testjob_status.delay(testjob.id, self.extra_args.get("job_status"))
            return

        tradefed_files = self._extract_tradefed_from_job_definition(testjob)
        if len(tradefed_files) != 1:
            logger.info(f"Job {testjob.id} has {len(tradefed_files)} tradefed files in the definition, it should have 1, aborting")
            update_testjob_status.delay(testjob.id, self.extra_args.get("job_status"))
            logger.info("Finishing CTS/VTS plugin for test run: %s" % testjob)
            return

        tradefed_name, results_format = tradefed_files[0]

        results_extracted = False
        results = None
        try:
            results = self._get_from_artifactorial(testjob, tradefed_name)
        except xmlrpc.client.ProtocolError as err:
            error_cleaned = 'Failed to process CTS/VTS tests: %s - %s' % (err.errcode, testjob.backend.get_implementation().url_remove_token(str(err.errmsg)))
            logger.error(error_cleaned)

            testjob.failure += error_cleaned
            testjob.save()

        if results is None:
            logger.info("Aborting CTS/VTS, no tradefed file found")
            update_testjob_status.delay(testjob.id, self.extra_args.get("job_status"))
            return

        logger.debug("Processing results")
        testjob.testrun.metadata["tradefed_results_url_%s" % testjob.job_id] = self.tradefed_results_url
        testjob.testrun.save()

        if results.test_results is not None:
            if testjob.target.get_setting("PLUGINS_TRADEFED_EXTRACT_AGGREGATED", False) and results_format == "aggregated":
                self._extract_cts_results(results.test_results.contents, testjob.testrun, tradefed_name)
                results_extracted = True
            else:
                failed = testjob.testrun.tests.filter(result=False)
                self._assign_test_log(results.test_results.contents, failed)

            self._convert_paths(testjob.testrun, results)

        attachments = [
            ("test_results.xml", results.test_results, "application/xml"),
            ("compatibility_result.xsl", results.test_result_xslt, "application/xslt+xml"),
            ("compatibility_result.css", results.test_result_css, "text/css"),
            ("logo.png", results.test_result_image, "image/png"),
            ("teadefed_stdout.txt", results.tradefed_stdout, "text/plain"),
            ("teadefed_logcat.txt", results.tradefed_logcat, "text/plain"),
        ]

        if results.tradefed_zipfile is not None:
            attachments.append(
                (results.tradefed_zipfile.name or "tradefed.tar.gz", results.tradefed_zipfile, results.tradefed_zipfile.mimetype or "application/x-tar")
            )

        for filename, attr, mimetype in attachments:
            if attr is not None:
                self._create_testrun_attachment(testjob.testrun, filename, attr, mimetype)

        # Update the status even if the job does not have a proper tradefed file to process
        if not results_extracted:
            update_testjob_status.delay(testjob.id, self.extra_args.get("job_status"))

        logger.info("Finishing CTS/VTS plugin for test run: %s" % testjob)
