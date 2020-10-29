import django
import os


os.environ['DJANGO_SETTINGS_MODULE'] = 'squad.settings'
django.setup()


import logging
import tarfile
import unittest
import tradefed
from io import StringIO, BytesIO
from unittest.mock import PropertyMock, MagicMock, Mock, patch
from tradefed import Tradefed, ResultFiles, ExtractedResult


SUITES = """
- {id: '1', job: '999', name: 2_bar}
"""

SUITES_INVALID = """
- {id: '1', job: '999', name: 2_bar
"""

RESULTS = """
- id: '9991'
  job: '999'
  level: ''
  log_end_line: '4353'
  log_start_line: '4353'
  logged: '2018-11-07 11:11:01.341667+00:00'
  measurement: None
  metadata: {case: BOOTTIME_LOGCAT_ALL_COLLECT, definition: 2_bar, result: pass}
  name: BOOTTIME_LOGCAT_ALL_COLLECT
  result: pass
  suite: 2_bar
  unit: ''
  url: /results/testcase/9991
- id: '9992'
  job: '999'
  level: ''
  log_end_line: '4359'
  log_start_line: '4359'
  logged: '2018-11-07 11:11:01.341667+00:00'
  measurement: None
  metadata: {case: test-attachment, definition: 2_bar, result: pass, reference: "http://foo.bar.com"}
  name: test-attachment
  result: pass
  suite: 2_bar
  unit: ''
  url: /results/testcase/9991
"""

RESULTS_INVALID = """
- id: '9991'
  job: '999': 123
"""

RESULT_URL = "http://foo.bar.com"

RESULT_DICT = {
    "id": "9992",
    "job": "999",
    "level": "",
    "log_end_line": "4359",
    "log_start_line": "4359",
    "logged": "2018-11-07 11:11:01.341667+00:00",
    "measurement": None,
    "metadata": {
        "case": "test-attachment",
        "definition": "2_bar",
        "result": "pass",
        "reference": RESULT_URL,
    },
    "name": "test-attachment",
    "result": "pass",
    "suite": "2_bar",
    "unit": "",
    "url": "/results/testcase/9991",
}

XML_RESULTS = """<?xml version='1.0' encoding='UTF-8' standalone='no' ?>
<Result start="1517218412388" end="1517221873527" start_display="Mon Jan 29 09:33:32 UTC 2018" end_display="Mon Jan 29 10:31:13 UTC 2018" suite_name="CTS" suite_version="8.1_r1" suite_plan="cts-lkft" suite_build_number="687" report_version="5.0" command_line_args="cts-lkft -a arm64-v8a --disable-reboot --skip-preconditions --skip-device-info" devices="96B0201601000622" host_name="lxc-hikey-test-104120" os_name="Linux" os_version="4.9.0-5-amd64" os_arch="amd64" java_vendor="Oracle Corporation" java_version="9-internal">
  <Build build_abis_64="arm64-v8a" build_manufacturer="unknown" build_abis_32="armeabi-v7a,armeabi" build_product="hikey" build_brand="Android" build_board="hikey" build_serial="96B0201601000622" build_version_security_patch="2017-12-01" build_reference_fingerprint="" build_fingerprint="Android/hikey/hikey:P/OC-MR1/687:userdebug/test-keys" build_version_sdk="27" build_abis="arm64-v8a,armeabi-v7a,armeabi" build_device="hikey" build_abi="arm64-v8a" build_model="hikey" build_id="OC-MR1" build_abi2="" build_version_incremental="687" build_version_release="P" build_version_base_os="" build_type="userdebug" build_tags="test-keys" />
  <Summary pass="3" failed="2" modules_done="1" modules_total="1" />
  <Module name="module_foo" abi="arm64-v8a" runtime="34082" done="true" pass="1">
    <TestCase name="TestCaseBar">
      <Test result="pass" name="test_bar1" />
      <Test result="pass" name="test_bar2" />
      <Test result="pass" name="test_bar3" />
      <Test result="fail" name="test_bar4" >
        <Failure message="java.lang.Error">
          <StackTrace>java.lang.Error:
at org.junit.Assert.fail(Assert.java:88)
</StackTrace>
        </Failure>
      </Test>
      <Test result="fail" name="first_subname/second_subname.third_subname/test_bar5_64bit">
        <Failure message="java.lang.Error">
          <StackTrace>java.lang.Error:
at org.junit.Assert.fail(Assert.java:88)
</StackTrace>
        </Failure>
      </Test>
    </TestCase>
  </Module>
</Result>
"""

JOB_DEFINITION = """
device_type: hi6220-hikey-r2
job_name: lkft-android-android-hikey-linaro-4.4-efd576b19eac-51-cts-armeabi-v7a
timeouts:
  job:
    minutes: 360
  action:
    minutes: 15
  connection:
    minutes: 2
priority: medium
visibility:
  group:
  - lkft

secrets:
  ARTIFACTORIAL_TOKEN: 3a861de8371936ecd03c0a342b3cb9b4
  AP_SSID: LAVATEST
  AP_KEY: NepjqGbq

metadata:
  android.url: http://testdata.linaro.org/lkft/aosp-stable/android-8.1.0_r29/
  android.version: Android 8.1
  build-location: http://snapshots.linaro.org/android/lkft/android-8.1-tracking/51
  git branch: android-hikey-linaro-4.4-efd576b19eac
  git repo: hikey-linaro
  git commit: '51'
  git describe: efd576b19eac
  build-url: https://ci.linaro.org/job/lkft-android-8.1-tracking/51/
  cts-manifest: http://testdata.linaro.org/cts/android-cts-8.1_r6//pinned-manifest.xml
  cts-version: android-cts-8.1_r6
  cts-plan: cts-lkft
  toolchain: clang
  series: lkft

protocols:
  lava-lxc:
    name: lxc-hikey-test
    distribution: ubuntu
    release: xenial
    arch: amd64
    verbose: true

actions:
- deploy:
    namespace: tlxc
    timeout:
      minutes: 5
    to: lxc
    packages:
    - systemd
    - systemd-sysv
    - ca-certificates
    - wget
    - unzip
    os: debian

- boot:
    namespace: tlxc
    prompts:
    - root@(.*):/#
    - :/
    timeout:
      minutes: 5
    method: lxc

- test:
    namespace: tlxc
    timeout:
      minutes: 10
    definitions:
    - from: inline
      name: install-google-fastboot
      path: inline/install-google-fastboot.yaml
      repository:
        metadata:
          format: Lava-Test Test Definition 1.0
          name: install-fastboot
          description: Install fastboot provided by google
        run:
          steps:
          - wget https://dl.google.com/android/repository/platform-tools_r26.0.0-linux.zip
          - unzip platform-tools_r26.0.0-linux.zip
          - ln -s `pwd`/platform-tools/fastboot /usr/bin/fastboot
          - ln -s `pwd`/platform-tools/adb /usr/bin/adb
          - fastboot --version

- deploy:
    timeout:
      minutes: 30
    to: fastboot
    namespace: droid
    connection: lxc

- boot:
    namespace: droid
    connection: serial
    prompts:
    - root@(.*):/#
    - :/
    timeout:
      minutes: 15
    method: fastboot

- test:
    namespace: tlxc
    connection: lxc
    timeout:
      minutes: 300
    definitions:
    - from: inline
      path: android-boot.yaml
      name: android-boot
      repository:
        metadata:
          format: Lava-Test Test Definition 1.0
          name: android-boot
          description: android-boot
        run:
          steps:
          - lava-test-case "android-boot" --shell adb getprop sys.boot_completed

- test:
    namespace: tlxc
    connection: lxc
    timeout:
      minutes: 300
    definitions:
    - repository: https://git.linaro.org/qa/test-definitions.git
      from: git
      path: automated/android/noninteractive-tradefed/tradefed.yaml
      params:
        TEST_PARAMS: cts-lkft -a armeabi-v7a --disable-reboot --skip-preconditions
          --skip-device-info --exclude-filter CtsDisplayTestCases
        TEST_URL: http://testdata.linaro.org/cts/android-cts-8.1_r6//android-cts.zip
        TEST_PATH: android-cts
        RESULTS_FORMAT: atomic
        ANDROID_VERSION: Android 8.1
      name: cts-lkft-armeabi-v7a
"""

JOB_DEFINITION_INTERACTIVE = """
device_type: hi6220-hikey-r2
job_name: lkft-android-android-hikey-linaro-4.4-efd576b19eac-51-cts-armeabi-v7a
timeouts:
  job:
    minutes: 360
  action:
    minutes: 15
  connection:
    minutes: 2
priority: medium
visibility:
  group:
  - lkft

secrets:
  ARTIFACTORIAL_TOKEN: 3a861de8371936ecd03c0a342b3cb9b4
  AP_SSID: LAVATEST
  AP_KEY: NepjqGbq

metadata:
  android.url: http://testdata.linaro.org/lkft/aosp-stable/android-8.1.0_r29/
  android.version: Android 8.1
  build-location: http://snapshots.linaro.org/android/lkft/android-8.1-tracking/51
  git branch: android-hikey-linaro-4.4-efd576b19eac
  git repo: hikey-linaro
  git commit: '51'
  git describe: efd576b19eac
  build-url: https://ci.linaro.org/job/lkft-android-8.1-tracking/51/
  cts-manifest: http://testdata.linaro.org/cts/android-cts-8.1_r6//pinned-manifest.xml
  cts-version: android-cts-8.1_r6
  cts-plan: cts-lkft
  toolchain: clang
  series: lkft

protocols:
  lava-lxc:
    name: lxc-hikey-test
    distribution: ubuntu
    release: xenial
    arch: amd64
    verbose: true

actions:
- deploy:
    namespace: tlxc
    timeout:
      minutes: 5
    to: lxc
    packages:
    - systemd
    - systemd-sysv
    - ca-certificates
    - wget
    - unzip
    os: debian

- boot:
    namespace: tlxc
    prompts:
    - root@(.*):/#
    - :/
    timeout:
      minutes: 5
    method: lxc

- test:
    namespace: tlxc
    timeout:
      minutes: 10
    definitions:
    - from: inline
      name: install-google-fastboot
      path: inline/install-google-fastboot.yaml
      repository:
        metadata:
          format: Lava-Test Test Definition 1.0
          name: install-fastboot
          description: Install fastboot provided by google
        run:
          steps:
          - wget https://dl.google.com/android/repository/platform-tools_r26.0.0-linux.zip
          - unzip platform-tools_r26.0.0-linux.zip
          - ln -s `pwd`/platform-tools/fastboot /usr/bin/fastboot
          - ln -s `pwd`/platform-tools/adb /usr/bin/adb
          - fastboot --version

- deploy:
    timeout:
      minutes: 30
    to: fastboot
    namespace: droid
    connection: lxc

- boot:
    namespace: droid
    connection: serial
    prompts:
    - root@(.*):/#
    - :/
    timeout:
      minutes: 15
    method: fastboot

- test:
    namespace: droid
    timeout:
      minutes: 10
    interactive:
    - name: write-presistdata
      prompts: ["=>", "/ # "]
      script:
      - command: "mmc list"
        name: mmc_list
      - command: "mmc dev 0"
        name: mmc_dev_0
      - command: "mmc part"
        name: mmc_part
      - command: "mw.b ****"
        name: mw_b
      - command: "mmc write ****"
        name: mmc_write
      - command: "fastboot 0"
        name: fastboot_

- test:
    namespace: tlxc
    connection: lxc
    timeout:
      minutes: 300
    definitions:
    - from: inline
      path: android-boot.yaml
      name: android-boot
      repository:
        metadata:
          format: Lava-Test Test Definition 1.0
          name: android-boot
          description: android-boot
        run:
          steps:
          - lava-test-case "android-boot" --shell adb getprop sys.boot_completed

- test:
    namespace: tlxc
    connection: lxc
    timeout:
      minutes: 300
    definitions:
    - repository: https://git.linaro.org/qa/test-definitions.git
      from: git
      path: automated/android/noninteractive-tradefed/tradefed.yaml
      params:
        TEST_PARAMS: cts-lkft -a armeabi-v7a --disable-reboot --skip-preconditions
          --skip-device-info --exclude-filter CtsDisplayTestCases
        TEST_URL: http://testdata.linaro.org/cts/android-cts-8.1_r6//android-cts.zip
        TEST_PATH: android-cts
        RESULTS_FORMAT: atomic
        ANDROID_VERSION: Android 8.1
      name: cts-lkft-armeabi-v7a
"""

logger = logging.getLogger()
logger.setLevel(logging.ERROR)


class TradefedLogsPluginTest(unittest.TestCase):
    def setUp(self):
        self.plugin = Tradefed()
        self.tarfile_path = os.path.abspath("./test/test_output.tar.xz")
        self.tarfile = open(self.tarfile_path, "rb")

    def tearDown(self):
        self.tarfile.close()

    @patch("tradefed.Tradefed._create_testrun_attachment")
    @patch("tradefed.Tradefed._assign_test_log")
    @patch("tradefed.Tradefed._get_from_artifactorial")
    @patch("tradefed.Tradefed.tradefed_results_url", new_callable=PropertyMock)
    def test_postprocess_testjob(
        self,
        results_url_mock,
        get_from_artifactorial_mock,
        assign_test_log_mock,
        create_testrun_attachment_mock,
    ):
        results_url_mock.return_value = "http://foo.com"
        get_from_artifactorial_mock.return_value = ResultFiles()
        testjob_mock = MagicMock()
        id_mock = PropertyMock(return_value="999111")
        type(testjob_mock).pk = id_mock
        job_id_mock = PropertyMock(return_value="1234")
        type(testjob_mock).job_id = job_id_mock
        testjob_mock.backend = MagicMock()
        implementation_type_mock = PropertyMock(return_value="lava")
        type(testjob_mock.backend).implementation_type = implementation_type_mock
        definition_mock = PropertyMock(return_value=JOB_DEFINITION)
        type(testjob_mock).definition = definition_mock
        testjob_target = MagicMock()
        project_settings_mock = PropertyMock(return_value='{}')
        type(testjob_target).project_settings = project_settings_mock
        type(testjob_mock).target = testjob_target
        self.plugin.postprocess_testjob(testjob_mock)
        implementation_type_mock.assert_called_once_with()
        definition_mock.assert_called_with()
        results_url_mock.assert_called_with()
        testjob_mock.testrun.metadata.__setitem__.assert_called_with('tradefed_results_url_1234', 'http://foo.com')
        testjob_mock.testrun.save.assert_called_with()
        assign_test_log_mock.assert_not_called()
        create_testrun_attachment_mock.assert_not_called()

    @patch("tradefed.Tradefed._create_testrun_attachment")
    @patch("tradefed.Tradefed._assign_test_log")
    @patch("tradefed.Tradefed._get_from_artifactorial")
    @patch("tradefed.Tradefed.tradefed_results_url", new_callable=PropertyMock)
    def test_postprocess_testjob_interactive(
        self,
        results_url_mock,
        get_from_artifactorial_mock,
        assign_test_log_mock,
        create_testrun_attachment_mock,
    ):
        results_url_mock.return_value = "http://foo.com"
        get_from_artifactorial_mock.return_value = ResultFiles()
        testjob_mock = MagicMock()
        id_mock = PropertyMock(return_value="999111")
        type(testjob_mock).pk = id_mock
        job_id_mock = PropertyMock(return_value="1234")
        type(testjob_mock).job_id = job_id_mock
        testjob_mock.backend = MagicMock()
        implementation_type_mock = PropertyMock(return_value="lava")
        type(testjob_mock.backend).implementation_type = implementation_type_mock
        definition_mock = PropertyMock(return_value=JOB_DEFINITION_INTERACTIVE)
        type(testjob_mock).definition = definition_mock
        testjob_target = MagicMock()
        project_settings_mock = PropertyMock(return_value='{}')
        type(testjob_target).project_settings = project_settings_mock
        type(testjob_mock).target = testjob_target
        self.plugin.postprocess_testjob(testjob_mock)
        implementation_type_mock.assert_called_once_with()
        definition_mock.assert_called_with()
        results_url_mock.assert_called_with()
        testjob_mock.testrun.metadata.__setitem__.assert_called_with('tradefed_results_url_1234', 'http://foo.com')
        testjob_mock.testrun.save.assert_called_with()
        assign_test_log_mock.assert_not_called()
        create_testrun_attachment_mock.assert_not_called()

    @patch("tradefed.Tradefed._create_testrun_attachment")
    @patch("tradefed.Tradefed._assign_test_log")
    @patch("tradefed.Tradefed._get_from_artifactorial")
    @patch("tradefed.Tradefed.tradefed_results_url", new_callable=PropertyMock)
    def test_postprocess_testjob_save_attachments(
        self,
        results_url_mock,
        get_from_artifactorial_mock,
        assign_test_log_mock,
        create_testrun_attachment_mock,
    ):
        results_url_mock.return_value = "http://foo.com"
        result_files = ResultFiles()
        result_files.test_results = ExtractedResult()
        result_files.test_results.contents = BytesIO("abc".encode("utf-8"))
        result_files.test_results.length = 3
        get_from_artifactorial_mock.return_value = result_files
        testjob_mock = MagicMock()
        id_mock = PropertyMock(return_value="999111")
        type(testjob_mock).pk = id_mock
        job_id_mock = PropertyMock(return_value="1234")
        type(testjob_mock).job_id = job_id_mock
        testjob_mock.backend = MagicMock()
        implementation_type_mock = PropertyMock(return_value="lava")
        type(testjob_mock.backend).implementation_type = implementation_type_mock
        definition_mock = PropertyMock(return_value=JOB_DEFINITION)
        type(testjob_mock).definition = definition_mock
        testjob_target = MagicMock()
        project_settings_mock = PropertyMock(return_value='{}')
        type(testjob_target).project_settings = project_settings_mock
        type(testjob_mock).target = testjob_target
        self.plugin.postprocess_testjob(testjob_mock)
        implementation_type_mock.assert_called_once_with()
        definition_mock.assert_called_with()
        results_url_mock.assert_called_with()
        testjob_mock.testrun.metadata.__setitem__.assert_called_with('tradefed_results_url_1234', 'http://foo.com')
        testjob_mock.testrun.save.assert_called_with()
        # uncomment when moving to python 3.6
        #assign_test_log_mock.assert_called()
        create_testrun_attachment_mock.assert_called_with(
            testjob_mock.testrun,
            'test_results.xml',
            result_files.test_results,
            'application/xml')

    def test_create_testrun_attachment(self):
        testrun_mock = Mock()
        name = "name"
        extracted_file_mock = Mock()
        type(extracted_file_mock).length = PropertyMock(return_value=2)
        content_mock = Mock()
        #read_mock = Mock()
        type(content_mock).read = lambda s: 'abc'
        type(extracted_file_mock).contents = content_mock
        self.plugin._create_testrun_attachment(testrun_mock, name, extracted_file_mock, "text/plain")
        testrun_mock.attachments.create.assert_called_with(data='abc', filename='name', length=2, mimetype='text/plain')

    @patch("tradefed.Tradefed._download_results")
    def test_get_from_artifactorial(self, download_results_mock):
        suite_name = "2_bar"
        download_results_mock.return_value = ResultFiles()
        testjob_mock = Mock()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.return_value = (
            SUITES
        )
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.return_value = (
            RESULTS
        )
        job_id_mock = PropertyMock(return_value=999)
        type(testjob_mock).job_id = job_id_mock
        result = self.plugin._get_from_artifactorial(testjob_mock, suite_name)
        job_id_mock.assert_called_with()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.assert_called_once_with(999)
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.assert_called_with(999, '2_bar', 500, 0)
        self.assertIsNotNone(result)

    @patch("tradefed.Tradefed._download_results")
    def test_get_from_artifactorial_invalid_suite_list(self, download_results_mock):
        suite_name = "2_bar"
        download_results_mock.return_value = ResultFiles()
        testjob_mock = Mock()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.return_value = (
            SUITES_INVALID
        )
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.return_value = (
            RESULTS
        )
        job_id_mock = PropertyMock(return_value=999)
        type(testjob_mock).job_id = job_id_mock
        result = self.plugin._get_from_artifactorial(testjob_mock, suite_name)
        job_id_mock.assert_called_with()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.assert_called_once_with(999)
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.assert_not_called()
        self.assertIsNone(result)

    @patch("tradefed.Tradefed._download_results")
    def test_get_from_artifactorial_empty_suite_list(self, download_results_mock):
        suite_name = "2_bar"
        download_results_mock.return_value = ResultFiles()
        testjob_mock = Mock()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.return_value = (
            "[]"
        )
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.return_value = (
            RESULTS
        )
        job_id_mock = PropertyMock(return_value=999)
        type(testjob_mock).job_id = job_id_mock
        result = self.plugin._get_from_artifactorial(testjob_mock, suite_name)
        job_id_mock.assert_called_with()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.assert_called_once_with(999)
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.assert_not_called()
        self.assertIsNone(result)

    @patch("tradefed.Tradefed._download_results")
    def test_get_from_artifactorial_invalid_results(self, download_results_mock):
        suite_name = "2_bar"
        download_results_mock.return_value = ResultFiles()
        testjob_mock = Mock()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.return_value = (
            SUITES
        )
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.return_value = (
            RESULTS_INVALID
        )
        job_id_mock = PropertyMock(return_value=999)
        type(testjob_mock).job_id = job_id_mock
        result = self.plugin._get_from_artifactorial(testjob_mock, suite_name)
        job_id_mock.assert_called_with()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.assert_called_once_with(999)
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.assert_called_with(999, '2_bar', 500, 0)
        self.assertIsNone(result)

    @patch("tradefed.Tradefed._download_results")
    def test_get_from_artifactorial_empty_results(self, download_results_mock):
        suite_name = "2_bar"
        download_results_mock.return_value = ResultFiles()
        testjob_mock = Mock()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.return_value = (
            SUITES
        )
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.return_value = (
            "[]"
        )
        job_id_mock = PropertyMock(return_value=999)
        type(testjob_mock).job_id = job_id_mock
        result = self.plugin._get_from_artifactorial(testjob_mock, suite_name)
        job_id_mock.assert_called_with()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.assert_called_once_with(999)
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.assert_called_with(999, '2_bar', 500, 0)
        self.assertIsNone(result)

    @patch("requests.get")
    def test_download_results(self, get_mock):
        requests_result_mock = Mock()
        status_code_mock = PropertyMock(return_value=200)
        type(requests_result_mock).status_code = status_code_mock
        content_mock = PropertyMock(return_value=self.tarfile.read())
        type(requests_result_mock).content = content_mock
        url_mock = PropertyMock(return_value="http://foo.bar.com/file.tar.xz")
        type(requests_result_mock).url = url_mock
        headers_mock = PropertyMock(return_value={"Content-Type": "application/x-tar"})
        type(requests_result_mock).headers = headers_mock
        get_mock.return_value = requests_result_mock
        results = self.plugin._download_results(RESULT_DICT)
        status_code_mock.assert_called_once_with()
        self.assertEqual(content_mock.call_count, 2)
        self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
        self.assertIsNotNone(results.test_results)
        self.assertIsNotNone(results.tradefed_stdout)
        self.assertIsNotNone(results.tradefed_logcat)

    @patch("tarfile.TarFile.getmembers")
    @patch("requests.get")
    def test_download_results_short_file(self, get_mock, tarfile_mock):
        requests_result_mock = Mock()
        status_code_mock = PropertyMock(return_value=200)
        type(requests_result_mock).status_code = status_code_mock
        content_mock = PropertyMock(return_value=self.tarfile.read())
        type(requests_result_mock).content = content_mock
        url_mock = PropertyMock(return_value="http://foo.bar.com/file.tar.xz")
        type(requests_result_mock).url = url_mock
        headers_mock = PropertyMock(return_value={"Content-Type": "application/x-tar"})
        type(requests_result_mock).headers = headers_mock
        get_mock.return_value = requests_result_mock
        tarfile_mock.side_effect = EOFError()
        results = self.plugin._download_results(RESULT_DICT)
        status_code_mock.assert_called_once_with()
        self.assertEqual(content_mock.call_count, 2)
        self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
        self.assertIsNone(results.test_results)
        self.assertIsNone(results.tradefed_stdout)
        self.assertIsNone(results.tradefed_logcat)

    @patch("tarfile.TarFile.getmembers")
    @patch("requests.get")
    def test_download_results_corrupted_compression_readerror(self, get_mock, tarfile_mock):
        requests_result_mock = Mock()
        status_code_mock = PropertyMock(return_value=200)
        type(requests_result_mock).status_code = status_code_mock
        content_mock = PropertyMock(return_value=self.tarfile.read())
        type(requests_result_mock).content = content_mock
        url_mock = PropertyMock(return_value="http://foo.bar.com/file.tar.xz")
        type(requests_result_mock).url = url_mock
        headers_mock = PropertyMock(return_value={"Content-Type": "application/x-tar"})
        type(requests_result_mock).headers = headers_mock
        get_mock.return_value = requests_result_mock
        tarfile_mock.side_effect = tarfile.ReadError()
        results = self.plugin._download_results(RESULT_DICT)
        status_code_mock.assert_called_once_with()
        self.assertEqual(content_mock.call_count, 2)
        self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
        self.assertIsNone(results.test_results)
        self.assertIsNone(results.tradefed_stdout)
        self.assertIsNone(results.tradefed_logcat)

    @patch("tarfile.TarFile.getmembers")
    @patch("requests.get")
    def test_download_results_corrupted_compression_headererror(self, get_mock, tarfile_mock):
        requests_result_mock = Mock()
        status_code_mock = PropertyMock(return_value=200)
        type(requests_result_mock).status_code = status_code_mock
        content_mock = PropertyMock(return_value=self.tarfile.read())
        type(requests_result_mock).content = content_mock
        url_mock = PropertyMock(return_value="http://foo.bar.com/file.tar.xz")
        type(requests_result_mock).url = url_mock
        headers_mock = PropertyMock(return_value={"Content-Type": "application/x-tar"})
        type(requests_result_mock).headers = headers_mock
        get_mock.return_value = requests_result_mock
        tarfile_mock.side_effect = tarfile.HeaderError()
        results = self.plugin._download_results(RESULT_DICT)
        status_code_mock.assert_called_once_with()
        self.assertEqual(content_mock.call_count, 2)
        self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
        self.assertIsNone(results.test_results)
        self.assertIsNone(results.tradefed_stdout)
        self.assertIsNone(results.tradefed_logcat)

    @patch("requests.get")
    def test_download_results_no_tarball(self, get_mock):
        requests_result_mock = Mock()
        status_code_mock = PropertyMock(return_value=200)
        type(requests_result_mock).status_code = status_code_mock
        content_mock = PropertyMock(return_value=bytes())
        type(requests_result_mock).content = content_mock
        url_mock = PropertyMock(return_value="http://foo.bar.com/file.tar.xz")
        type(requests_result_mock).url = url_mock
        headers_mock = PropertyMock(return_value={"Content-Type": "application/x-tar"})
        type(requests_result_mock).headers = headers_mock
        get_mock.return_value = requests_result_mock
        results = self.plugin._download_results(RESULT_DICT)
        status_code_mock.assert_called_once_with()
        self.assertEqual(content_mock.call_count, 2)
        self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
        self.assertIsNone(results.test_results)
        self.assertIsNone(results.tradefed_stdout)
        self.assertIsNone(results.tradefed_logcat)

    @patch("requests.get")
    def test_download_results_expired_url(self, get_mock):
        requests_result_mock = Mock()
        status_code_mock = PropertyMock(return_value=404)
        type(requests_result_mock).status_code = status_code_mock
        content_mock = PropertyMock(return_value=bytes())
        type(requests_result_mock).content = content_mock
        url_mock = PropertyMock(return_value="http://foo.bar.com/file.tar.xz")
        type(requests_result_mock).url = url_mock
        headers_mock = PropertyMock(return_value={"Content-Type": "application/x-tar"})
        type(requests_result_mock).headers = headers_mock
        get_mock.return_value = requests_result_mock
        results = self.plugin._download_results(RESULT_DICT)
        status_code_mock.assert_called_once_with()
        content_mock.assert_not_called()
        self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
        self.assertIsNone(results.test_results)
        self.assertIsNone(results.tradefed_stdout)
        self.assertIsNone(results.tradefed_logcat)

    def test_assign_test_log(self):
        test_mock = Mock()
        suite_mock = PropertyMock(return_value="cts-lkft/arm64-v8a.module_foo")
        type(test_mock).suite = suite_mock
        name_mock = PropertyMock(return_value="TestCaseBar.test_bar4")
        type(test_mock).name = name_mock
        self.plugin._assign_test_log(StringIO(XML_RESULTS), [test_mock])
        self.assertIn("java.lang.Error", test_mock.log)
        test_mock.save.assert_called_once_with()

    def test_assign_test_log_no_slash(self):
        test_mock = Mock()
        suite_mock = PropertyMock(return_value="cts-lkft.arm64-v8a.module_foo")
        type(test_mock).suite = suite_mock
        name_mock = PropertyMock(return_value="TestCaseBar.test_bar4")
        type(test_mock).name = name_mock
        self.plugin._assign_test_log(StringIO(XML_RESULTS), [test_mock])
        test_mock.save.assert_not_called()

    def test_assign_test_log_complex_name(self):
        test_mock = Mock()
        suite_mock = PropertyMock(return_value="cts-lkft/arm64-v8a.module_foo/TestCaseBar.first_subname/second_subname.third_subname")
        type(test_mock).suite = suite_mock
        name_mock = PropertyMock(return_value="test_bar5_64bit")
        type(test_mock).name = name_mock
        self.plugin._assign_test_log(StringIO(XML_RESULTS), [test_mock])
        self.assertIn("java.lang.Error", test_mock.log)
        test_mock.save.assert_called_once_with()

    def test_assign_test_log_empty_list(self):
        buf = StringIO(XML_RESULTS)
        self.plugin._assign_test_log(buf, [])
        self.assertEqual(0, buf.tell())

    def test_assign_test_log_missing_trace(self):
        test_mock = Mock()
        suite_mock = PropertyMock(return_value="cts-lkft/arm64-v8a.module_foo")
        type(test_mock).suite = suite_mock
        name_mock = PropertyMock(return_value="TestCaseBar.test_bar5")
        type(test_mock).name = name_mock
        self.plugin._assign_test_log(StringIO(XML_RESULTS), [test_mock])
        test_mock.save.assert_not_called()

    def test_assign_test_log_missing_xml(self):
        test_mock = Mock()
        suite_mock = PropertyMock(return_value="cts-lkft/arm64-v8a.module_foo")
        type(test_mock).suite = suite_mock
        name_mock = PropertyMock(return_value="TestCaseBar.test_bar5")
        type(test_mock).name = name_mock
        self.plugin._assign_test_log(StringIO(), [test_mock])
        test_mock.save.assert_not_called()

    def test_assign_test_log_missing_module(self):
        test_mock = Mock()
        suite_mock = PropertyMock(return_value="cts-lkft/arm64-v8a.module_foo1")
        type(test_mock).suite = suite_mock
        name_mock = PropertyMock(return_value="TestCaseBar.test_bar5")
        type(test_mock).name = name_mock
        self.plugin._assign_test_log(StringIO(XML_RESULTS), [test_mock])
        test_mock.save.assert_not_called()
