import logging
import json

from collections import defaultdict

from squad.core.models import SuiteMetadata, Test, KnownIssue, Status, TestRun, ProjectStatus, PluginScratch
from squad.celery import app as celery
from squad.core.utils import join_name
from squad.core.tasks import RecordTestRunStatus


logger = logging.getLogger()


@celery.task(queue='ci_fetch')
def update_build_status(results_list, testrun_id):
    testrun = TestRun.objects.get(pk=testrun_id)

    # Comput stats all at once
    Status.objects.filter(test_run=testrun).all().delete()
    testrun.status_recorded = False
    RecordTestRunStatus()(testrun)

    ProjectStatus.create_or_update(testrun.build)


@celery.task(queue='ci_fetch')
def create_testcase_tests(pluginscratch_id, suite_slug, testrun_id, suite_id):
    try:
        scratch = PluginScratch.objects.get(pk=pluginscratch_id)
        test_cases = json.loads(scratch.storage)
    except PluginScratch.DoesNotExist:
        logger.warning(f"PluginScratch with ID: {pluginscratch_id} doesn't exist")
        return
    except ValueError as e:
        logger.warning(f"Failed to load json for PluginScratch ({pluginscratch_id}): {e}")

    testrun = TestRun.objects.get(pk=testrun_id)
    issues = defaultdict(list)
    for issue in KnownIssue.active_by_environment(testrun.environment):
        issues[issue.test_name].append(issue)

    test_list = []
    for test_case in test_cases:
        test_case_name = test_case.get("name")

        tests = test_case['tests']
        logger.debug(f"Extracting TestCase: {test_case_name} - {len(tests)} testcases")
        for test in tests:

            test_result = test.get("result")
            test_result = test_result == 'pass'
            if test_result == 'skip' or test.get("skipped") == "true":
                test_result = None

            test_name = f"{test_case_name}.{test.get('name')}"

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

    logger.info(f"Deleting PluginScratch with ID: {scratch.pk}")
    scratch.delete()
    return 0
