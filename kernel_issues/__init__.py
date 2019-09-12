import logging
import re
from squad.plugins import Plugin as BasePlugin


logger = logging.getLogger()

# Tip: broader regexes should come first
REGEXES = [
    ('kernel_panic', 'Kernel panic - not syncing.*?end Kernel panic - not syncing'),
    ('kernel_exception', '------------\[ cut here \]------------.*?------------\[ cut here \]------------'),
    ('kernel_trace', 'Stack:.*?---\[ end trace \w* \]---'),
    ('kernel_oops', 'Oops:.*?$'),
    ('kernel_fault', 'Unhandled fault.*?$'),
    ('kernel_warning','WARNING:.*?$'),
]


class KernelIssues(BasePlugin):
    name = "Kernel Issues"    

    def __prepare_regexes(self):
        combined = [r'(%s)' % r[1] for r in REGEXES]
        return re.compile(r'|'.join(combined), re.S | re.M)

    def __kernel_msgs_only(self, log):
        kernel_msgs = re.findall(r'^\[[ \d]+\.[ \d]+\] .*?$', log, re.S | re.M)
        return '\n'.join(kernel_msgs)

    def postprocess_testrun(self, testrun):
        log = self.__kernel_msgs_only(testrun.log)
        regex = self.__prepare_regexes()
        matches = regex.findall(log)
        snippets = {regex_id: [] for regex_id in range(len(REGEXES))}
        for match in matches:
            for regex_id in range(len(REGEXES)):
                if len(match[regex_id]) > 0:
                    snippets[regex_id].append(match[regex_id])

        suite, _ = testrun.build.project.suites.get_or_create(slug='kernel-issues')
        for regex_id in range(len(REGEXES)):
            testrun.tests.create(
                suite=suite,
                name=REGEXES[regex_id][0],
                result=(len(snippets[regex_id]) == 0),
                log='\n'.join(snippets[regex_id]),
            )
