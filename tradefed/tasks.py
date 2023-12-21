import logging
import json

from collections import defaultdict

from squad.core.models import SuiteMetadata, Test, KnownIssue, Status, TestRun, PluginScratch
from squad.celery import app as celery
from squad.core.utils import join_name
from squad.core.tasks import RecordTestRunStatus
from squad.ci.tasks import update_testjob_status


logger = logging.getLogger()


@celery.task(queue='ci_fetch')
def update_build_status(results_list, testrun_id, job_id, job_status):
    testrun = TestRun.objects.get(pk=testrun_id)

    # Compute stats all at once
    Status.objects.filter(test_run=testrun).all().delete()
    testrun.status_recorded = False
    RecordTestRunStatus()(testrun)

    update_testjob_status.delay(job_id, job_status)


@celery.task(queue='ci_fetch')
def create_testcase_tests(pluginscratch_id, suite_slug, testrun_id, suite_id):
    try:
        scratch = PluginScratch.objects.get(pk=pluginscratch_id)
        test_cases = json.loads(scratch.storage)
    except PluginScratch.DoesNotExist:
        logger.error(f"PluginScratch with ID: {pluginscratch_id} doesn't exist")
        return
    except ValueError as e:
        logger.error(f"Failed to load json for PluginScratch ({pluginscratch_id}): {e}")

    testrun = TestRun.objects.get(pk=testrun_id)
    issues = defaultdict(list)
    for issue in KnownIssue.active_by_environment(testrun.environment):
        issues[issue.test_name].append(issue)

    try:
        test_list = []
        for test_case in test_cases:
            test_case_name = test_case.get("name")

            tests = test_case['tests']
            logger.debug(f"Extracting TestCase: {test_case_name} - {len(tests)} testcases")
            for test in tests:

                test_result = None
                if test.get("result") == "pass":
                    test_result = True
                elif test.get("result") in ["fail", "ASSUMPTION_FAILURE"]:
                    test_result = False

                test_name = f"{test_case_name}.{test.get('name')}"

                # TODO: increase SQUAD's max length for test name
                #       currently it's at 256 characters
                test_name = test_name[:256]

                metadata, _ = SuiteMetadata.objects.get_or_create(suite=suite_slug, name=test_name, kind='test')
                full_name = join_name(suite_slug, test_name)
                test_issues = issues.get(full_name, [])
                test_list.append(Test(
                    test_run=testrun,
                    suite_id=suite_id,
                    metadata=metadata,
                    result=test_result,
                    log=test.get('log', ''),
                    has_known_issues=bool(test_issues),
                    build=testrun.build,
                    environment=testrun.environment,
                ))

        created_tests = Test.objects.bulk_create(test_list)
        for test in created_tests:
            if test.name in issues.keys():
                test.known_issues.add(issues[test.name])
    except Exception as e:
        logger.error(f"CTS/VTS error: {e}")

    logger.info(f"Deleting PluginScratch with ID: {scratch.pk}")
    scratch.delete()
    return 0
