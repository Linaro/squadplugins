import os
import logging
import requests_mock
import tarfile
import unittest
from io import StringIO, BytesIO
from unittest.mock import PropertyMock, MagicMock, Mock, patch
from tradefed import Tradefed, ResultFiles, ExtractedResult
from collections import defaultdict


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

RESULTS_BAD = """
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
  metadata: {case: test-attachment, definition: 2_bar, result: fail}
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
  <Module name="module_bar" abi="arm64-v8a" runtime="34082" done="true" pass="1">
    <TestCase name="TestCaseFoo">
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
      <Test result="fail" name="xfirst_subname/second_subname.third_subname/test_bar5_64bit">
        <Failure message="java.lang.Error">
          <StackTrace>java.lang.Error:
at org.junit.Assert.fail(Assert.java:88)
</StackTrace>
        </Failure>
      </Test>
      <Test result="ASSUMPTION_FAILURE" name="ztestSetAndGetBrightnessConfiguration">
        <Failure message="org.junit.AssumptionViolatedException: got: &amp;lt;false&amp;gt;, expected: is &amp;lt;true&amp;gt;&#13;">
          <StackTrace>org.junit.AssumptionViolatedException: got: false, expected: is true
                  at org.junit.Assume.assumeThat(Assume.java:106)
                  at org.junit.Assume.assumeTrue(Assume.java:50)
                  at android.display.cts.BrightnessTest.testSetAndGetBrightnessConfiguration(BrightnessTest.java:398)
                  at java.lang.reflect.Method.invoke(Native Method)
                  at org.junit.runners.model.FrameworkMethod$1.runReflectiveCall(FrameworkMethod.java:59)
                  at org.junit.internal.runners.model.ReflectiveCallable.run(ReflectiveCallable.java:12)
                  at org.junit.runners.model.FrameworkMethod.invokeExplosively(FrameworkMethod.java:61)
                  at org.junit.internal.runners.statements.InvokeMethod.evaluate(InvokeMethod.java:17)
                  at org.junit.internal.runners.statements.FailOnTimeout$CallableStatement.call(FailOnTimeout.java:148)
                  at org.junit.internal.runners.statements.FailOnTimeout$CallableStatement.call(FailOnTimeout.java:142)
                  at java.util.concurrent.FutureTask.run(FutureTask.java:264)
                  at java.lang.Thread.run(Thread.java:1012)
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
knownissue = None


class TradefedLogsPluginTest(unittest.TestCase):
    def setUp(self):
        self.plugin = Tradefed()
        self.tarfile_path = os.path.abspath("./test/test_output.tar.xz")
        self.tarfile = open(self.tarfile_path, "rb")

    def tearDown(self):
        self.tarfile.close()

    @patch("tradefed.Tradefed._extract_cts_results")
    @patch("tradefed.Tradefed._create_testrun_attachment")
    @patch("tradefed.Tradefed._assign_test_log")
    @patch("tradefed.Tradefed._get_from_artifactorial")
    @patch("tradefed.update_testjob_status.delay")
    @patch("tradefed.Tradefed.tradefed_results_url", new_callable=PropertyMock)
    def test_postprocess_testjob(
        self,
        results_url_mock,
        update_testjob_status_mock,
        get_from_artifactorial_mock,
        assign_test_log_mock,
        create_testrun_attachment_mock,
        extract_cts_results_mock,
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
        update_testjob_status_mock.assert_called()

    @patch("tradefed.Tradefed._create_testrun_attachment")
    @patch("tradefed.Tradefed._assign_test_log")
    @patch("tradefed.Tradefed._get_from_artifactorial")
    @patch("tradefed.update_testjob_status.delay")
    @patch("tradefed.Tradefed.tradefed_results_url", new_callable=PropertyMock)
    def test_postprocess_testjob_interactive(
        self,
        results_url_mock,
        update_testjob_status_mock,
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
        update_testjob_status_mock.assert_called()

    @patch("tradefed.Tradefed._create_testrun_attachment")
    @patch("tradefed.Tradefed._assign_test_log")
    @patch("tradefed.Tradefed._get_from_artifactorial")
    @patch("tradefed.update_testjob_status.delay")
    @patch("tradefed.Tradefed.tradefed_results_url", new_callable=PropertyMock)
    def test_postprocess_testjob_save_attachments(
        self,
        results_url_mock,
        update_testjob_status_mock,
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
        assign_test_log_mock.assert_called()
        create_testrun_attachment_mock.assert_called_with(
            testjob_mock.testrun,
            'test_results.xml',
            result_files.test_results,
            'application/xml')
        update_testjob_status_mock.assert_called()

    @patch("tradefed.Tradefed._create_testrun_attachment")
    @patch("tradefed.Tradefed._assign_test_log")
    @patch("tradefed.Tradefed._get_from_artifactorial")
    @patch("tradefed.update_testjob_status.delay")
    @patch("tradefed.Tradefed.tradefed_results_url", new_callable=PropertyMock)
    def test_postprocess_testjob_empty_artifactorial_results(
        self,
        results_url_mock,
        update_testjob_status_mock,
        get_from_artifactorial_mock,
        assign_test_log_mock,
        create_testrun_attachment_mock,
    ):
        get_from_artifactorial_mock.return_value = None
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
        results_url_mock.assert_not_called()
        create_testrun_attachment_mock.assert_not_called()
        update_testjob_status_mock.assert_called()

    def test_create_testrun_attachment(self):
        testrun_mock = Mock()
        name = "name"
        extracted_file_mock = Mock()
        type(extracted_file_mock).length = PropertyMock(return_value=2)
        content_mock = Mock()
        type(content_mock).read = lambda s: 'abc'
        type(extracted_file_mock).contents = content_mock
        self.plugin._create_testrun_attachment(testrun_mock, name, extracted_file_mock, "text/plain")
        testrun_mock.attachments.create.assert_called_with(filename='name', length=2, mimetype='text/plain')

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

    @patch("tradefed.Tradefed._download_results")
    def test_get_from_artifactorial_no_url(self, download_results_mock):
        suite_name = "2_bar"
        download_results_mock.return_value = ResultFiles()
        testjob_mock = Mock()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.return_value = (
            SUITES
        )
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.return_value = (
            RESULTS_BAD
        )
        job_id_mock = PropertyMock(return_value=999)
        type(testjob_mock).job_id = job_id_mock
        result = self.plugin._get_from_artifactorial(testjob_mock, suite_name)
        job_id_mock.assert_called_with()
        testjob_mock.backend.get_implementation().proxy.results.get_testjob_suites_list_yaml.assert_called_once_with(999)
        testjob_mock.backend.get_implementation().proxy.results.get_testsuite_results_yaml.assert_called_with(999, '2_bar', 500, 0)
        self.assertIsNone(result)

    def test_download_results(self):
        with requests_mock.Mocker() as fake_request:
            fake_request.get(
                "http://foo.bar.com",
                status_code=200,
                content=self.tarfile.read(),
                headers={"Content-Type": "application/x-tar"},
            )

            results = self.plugin._download_results(RESULT_URL)
            self.assertTrue(fake_request.called)
            self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
            self.assertIsNotNone(results.test_results)
            self.assertIsNotNone(results.tradefed_stdout)
            self.assertIsNotNone(results.tradefed_logcat)

    @patch("tarfile.TarFile.getmembers")
    def test_download_results_short_file(self, tarfile_mock):
        tarfile_mock.side_effect = EOFError()

        with requests_mock.Mocker() as fake_request:
            fake_request.get(
                "http://foo.bar.com",
                status_code=200,
                content=self.tarfile.read(),
                headers={"Content-Type": "application/x-tar"},
            )

            results = self.plugin._download_results(RESULT_URL)
            self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
            self.assertIsNone(results.test_results)
            self.assertIsNone(results.tradefed_stdout)
            self.assertIsNone(results.tradefed_logcat)

    @patch("tarfile.TarFile.getmembers")
    def test_download_results_corrupted_compression_readerror(self, tarfile_mock):
        tarfile_mock.side_effect = tarfile.ReadError()

        with requests_mock.Mocker() as fake_request:
            fake_request.get(
                "http://foo.bar.com",
                status_code=200,
                content=self.tarfile.read(),
                headers={"Content-Type": "application/x-tar"},
            )

            results = self.plugin._download_results(RESULT_URL)
            self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
            self.assertIsNone(results.test_results)
            self.assertIsNone(results.tradefed_stdout)
            self.assertIsNone(results.tradefed_logcat)

    @patch("tarfile.TarFile.getmembers")
    def test_download_results_corrupted_compression_headererror(self, tarfile_mock):
        tarfile_mock.side_effect = tarfile.HeaderError()

        with requests_mock.Mocker() as fake_request:
            fake_request.get(
                "http://foo.bar.com",
                status_code=200,
                content=self.tarfile.read(),
                headers={"Content-Type": "application/x-tar"},
            )

            results = self.plugin._download_results(RESULT_URL)
            self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
            self.assertIsNone(results.test_results)
            self.assertIsNone(results.tradefed_stdout)
            self.assertIsNone(results.tradefed_logcat)

    def test_download_results_no_tarball(self):
        with requests_mock.Mocker() as fake_request:
            fake_request.get(
                "http://foo.bar.com",
                status_code=200,
                content=bytes(),
                headers={"Content-Type": "application/x-tar"},
            )

            results = self.plugin._download_results(RESULT_URL)
            self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
            self.assertIsNone(results.test_results)
            self.assertIsNone(results.tradefed_stdout)
            self.assertIsNone(results.tradefed_logcat)

    def test_download_results_expired_url(self):
        with requests_mock.Mocker() as fake_request:
            fake_request.get(
                "http://foo.bar.com",
                status_code=404,
                content=bytes(),
                headers={"Content-Type": "application/x-tar"},
            )

            results = self.plugin._download_results(RESULT_URL)
            self.assertEqual(self.plugin.tradefed_results_url, RESULT_URL)
            self.assertIsNone(results.test_results)
            self.assertIsNone(results.tradefed_stdout)
            self.assertIsNone(results.tradefed_logcat)

    @patch("tradefed.settings")
    def test_download_results_from_squad_bad_url(self, mock_settings):
        mock_settings.BASE_URL = "http://squad.com"
        url = "http://squad.com/not-really-valid"
        results = self.plugin._download_results(url)
        self.assertEqual(self.plugin.tradefed_results_url, url)
        self.assertIsNone(results.test_results)
        self.assertIsNone(results.tradefed_stdout)
        self.assertIsNone(results.tradefed_logcat)

    @patch("tradefed.TestRun")
    @patch("tradefed.settings")
    def test_download_results_from_squad_testrun_not_found(self, mock_settings, mock_testrun):
        queryset = MagicMock()
        queryset.exists.return_value = False

        objects = MagicMock()
        objects.filter.return_value = queryset

        mock_testrun.objects = objects
        mock_settings.BASE_URL = "http://squad.com"

        url = "http://squad.com/api/testruns/1/attachments?filename=tradefed.tar.xz"
        results = self.plugin._download_results(url)
        self.assertEqual(self.plugin.tradefed_results_url, url)
        self.assertIsNone(results.test_results)
        self.assertIsNone(results.tradefed_stdout)
        self.assertIsNone(results.tradefed_logcat)

    @patch("tradefed.TestRun")
    @patch("tradefed.settings")
    def test_download_results_from_squad_attachment_not_found(self, mock_settings, mock_testrun):
        attachments_queryset = MagicMock()
        attachments_queryset.count.return_value = 0

        attachments = MagicMock()
        attachments.filter.return_value = attachments_queryset

        testrun = MagicMock()
        testrun.attachments = attachments

        queryset = MagicMock()
        queryset.exists.return_value = True
        queryset.first.return_value = testrun

        objects = MagicMock()
        objects.filter.return_value = queryset

        mock_testrun.objects = objects
        mock_settings.BASE_URL = "http://squad.com"

        url = "http://squad.com/api/testruns/1/attachments?filename=tradefed.tar.xz"
        results = self.plugin._download_results(url)
        self.assertEqual(self.plugin.tradefed_results_url, url)
        self.assertIsNone(results.test_results)
        self.assertIsNone(results.tradefed_stdout)
        self.assertIsNone(results.tradefed_logcat)

    @patch("tradefed.TestRun")
    @patch("tradefed.settings")
    def test_download_results_from_squad(self, mock_settings, mock_testrun):
        attachment = MagicMock()
        attachment.data = b"1"
        attachment.mimetype.return_value = "text/plain"
        attachment.filename.return_value = "tradefed.tar.xz"

        attachments_queryset = MagicMock()
        attachments_queryset.count.return_value = 1
        attachments_queryset.first.return_value = attachment

        attachments = MagicMock()
        attachments.filter.return_value = attachments_queryset

        testrun = MagicMock()
        testrun.attachments = attachments

        queryset = MagicMock()
        queryset.exists.return_value = True
        queryset.first.return_value = testrun

        objects = MagicMock()
        objects.filter.return_value = queryset

        mock_testrun.objects = objects
        mock_settings.BASE_URL = "http://squad.com"

        url = "http://squad.com/api/testruns/1/attachments?filename=tradefed.tar.xz"
        results = self.plugin._download_results(url)
        self.assertEqual(self.plugin.tradefed_results_url, url)
        results.tradefed_zipfile.contents.seek(0)
        self.assertEqual(b"1", results.tradefed_zipfile.contents.read())

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

    def test_extract_results_correctly(self):
        testrun = Mock()
        build = Mock()
        type(build).project = PropertyMock(return_value="MyProject")
        type(testrun).build = PropertyMock(return_value=build)
        type(testrun).pk = PropertyMock(return_value=1)

        def chord_mock_return_func(tasklist):
            pass

        def chord_mock_func(task):
            return chord_mock_return_func

        def update_s(testrun_pk, job_id, job_status):
            return {}

        def goc_mock(*args, **kwargs):
            return kwargs, False

        class KnownIssueMock:
            def __init__(self, title, test_name):
                self.environments = set()
                self.title = title
                self.test_name = test_name
                self.saved = False

            def save(self):
                self.saved = True

        def goc_knownissues(*args, **kwargs):
            global knownissue
            knownissue = KnownIssueMock(kwargs['title'], kwargs['test_name'])
            return knownissue, False

        tasks = defaultdict(list)

        def enqueue_testcases(self, testcases, testrun, suite):
            for testcase in testcases:
                tasks[suite['slug']].append(testcase)

        xmlbuf = StringIO(XML_RESULTS)
        with patch("squad.core.models.SuiteMetadata.objects.get_or_create", goc_mock), \
                patch("squad.core.models.Suite.objects.get_or_create", goc_mock), \
                patch("squad.core.models.KnownIssue.objects.get_or_create", goc_knownissues), \
                patch("tradefed.celery_chord", chord_mock_func), \
                patch("tradefed.tasks.update_build_status.s", update_s), \
                patch("tradefed.Tradefed._enqueue_testcases_chunk", enqueue_testcases):
            self.plugin._extract_cts_results(xmlbuf, testrun, 'cts')

        self.assertEqual(knownissue.title, 'Tradefed/cts/arm64-v8a.module_bar/TestCaseFoo.ztestSetAndGetBrightnessConfiguration')
        self.assertEqual(knownissue.test_name, 'cts/arm64-v8a.module_bar/TestCaseFoo.ztestSetAndGetBrightnessConfiguration')
        self.assertEqual(len(knownissue.environments), 1)
        self.assertTrue(knownissue.saved)
        self.assertEqual(tasks['cts/arm64-v8a.module_foo'], [
            {
                'name': 'TestCaseBar',
                'tests': [
                    {
                        'result': 'pass',
                        'name': 'test_bar1'
                    },
                    {
                        'result': 'pass',
                        'name': 'test_bar2'
                    },
                    {
                        'result': 'pass',
                        'name': 'test_bar3'
                    },
                    {
                        'result': 'fail',
                        'name': 'test_bar4',
                        'log': 'java.lang.Error:\nat org.junit.Assert.fail(Assert.java:88)\n'
                    },
                    {
                        'result': 'fail',
                        'name': 'first_subname/second_subname.third_subname/test_bar5_64bit',
                        'log': 'java.lang.Error:\nat org.junit.Assert.fail(Assert.java:88)\n'
                    }
                ],
                'suite': 'cts/arm64-v8a.module_foo'
            }
        ])

        self.assertEqual(tasks['cts/arm64-v8a.module_bar'][0]['name'], 'TestCaseFoo')
        self.assertEqual(tasks['cts/arm64-v8a.module_bar'][0]['suite'], 'cts/arm64-v8a.module_bar')

        tests = sorted(tasks['cts/arm64-v8a.module_bar'][0]['tests'], key=lambda d: d['name'])
        self.assertEqual(tests[0], {
            'result': 'pass',
            'name': 'test_bar1'
        })
        self.assertEqual(tests[1], {
            'result': 'pass',
            'name': 'test_bar2'
        })
        self.assertEqual(tests[2], {
            'result': 'pass',
            'name': 'test_bar3'
        })
        self.assertEqual(tests[3], {
            'result': 'fail',
            'name': 'test_bar4',
            'log': 'java.lang.Error:\nat org.junit.Assert.fail(Assert.java:88)\n'
        })
        self.assertEqual(tests[4], {
            'result': 'fail',
            'name': 'xfirst_subname/second_subname.third_subname/test_bar5_64bit',
            'log': 'java.lang.Error:\nat org.junit.Assert.fail(Assert.java:88)\n'
        })
        self.assertEqual(tests[5], {
            'result': 'ASSUMPTION_FAILURE',
            'name': 'ztestSetAndGetBrightnessConfiguration',
            'log': """org.junit.AssumptionViolatedException: got: false, expected: is true
                  at org.junit.Assume.assumeThat(Assume.java:106)
                  at org.junit.Assume.assumeTrue(Assume.java:50)
                  at android.display.cts.BrightnessTest.testSetAndGetBrightnessConfiguration(BrightnessTest.java:398)
                  at java.lang.reflect.Method.invoke(Native Method)
                  at org.junit.runners.model.FrameworkMethod$1.runReflectiveCall(FrameworkMethod.java:59)
                  at org.junit.internal.runners.model.ReflectiveCallable.run(ReflectiveCallable.java:12)
                  at org.junit.runners.model.FrameworkMethod.invokeExplosively(FrameworkMethod.java:61)
                  at org.junit.internal.runners.statements.InvokeMethod.evaluate(InvokeMethod.java:17)
                  at org.junit.internal.runners.statements.FailOnTimeout$CallableStatement.call(FailOnTimeout.java:148)
                  at org.junit.internal.runners.statements.FailOnTimeout$CallableStatement.call(FailOnTimeout.java:142)
                  at java.util.concurrent.FutureTask.run(FutureTask.java:264)
                  at java.lang.Thread.run(Thread.java:1012)\n"""
        })

    def test_extract_tarball_filename_from_url(self):

        # Make sure it returns None if no valid filenames are found
        self.assertIsNone(self.plugin._extract_tarball_filename_from_url("not-really-valid"))
        self.assertIsNone(self.plugin._extract_tarball_filename_from_url("https://nothing.com/here"))
        self.assertIsNone(self.plugin._extract_tarball_filename_from_url("https://nothing.com/here?nor=there"))
        self.assertIsNone(self.plugin._extract_tarball_filename_from_url("https://nothing.com/invalid-extension.zip"))
        self.assertIsNone(self.plugin._extract_tarball_filename_from_url("https://nothing.com/invalid-compression.tar.gz"))

        filename = self.plugin._extract_tarball_filename_from_url("http://some.url/tradefed.tar.xz")
        self.assertEqual("tradefed.tar.xz", filename)

        filename = self.plugin._extract_tarball_filename_from_url("http://some.url/?param1=val1&filename=tradefed.tar.xz")
        self.assertEqual("tradefed.tar.xz", filename)
