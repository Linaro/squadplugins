# 1.33.1

This release fixes a corner case from past release when a job
has a failed test-attachment case.

# 1.33

This release refactors the tradefed plugin a bit. It also add a condition
where the tradefed file might come from squad, avoiding an extra download.

# 1.32

This release adds a missing update to job status when jobs
do not have tradefed artefacts

# 1.31.2

This release logs xml parsing as error

# 1.31.1

This release lowers the number of tests batch when queueing tasks.
It should go easier on DB if multiple workers are bashing it.

# 1.31

This release reverts the change from release 1.30 and rework
the fix by simply calling a callback task from SQUAD that
updates testjob status.

# 1.30

This release changes how tradefed handles subtasks. It used
to spawn many celery subtasks, updating project status when
all subtasks are finished. The problem is that the main thread
returned right away, making SQUAD think that tradefed is
ready, causing inconsistencies. Now, the release makes the main
thread wait for all subtasks to finish before returning back
to SQUAD.

# 1.29.1

This release adds the mmtests properly to the setup of plugins.

# 1.29

This release adds the mmtests plugin. For now, it'll attempt
downloading attachments from tuxsuite backend.

# 1.28.3

This release adds a retry strategy when requesting files.

# 1.28.2

This release wraps test insertion with a try-except block to prevent
unknown behaviors to affect SQUAD. The release also temporarily
truncate test name to 256 characters.

# 1.28.1

This release removed parallel processing log lines. Apparently
it is not OK to have daemon processes to have children.

# 1.28

This release reduces the amount of queries to the database by
saving a test only when its log lines have finished matching,
thus saving lots of db time and performance.

# 1.27

This release fixes a bug when parsing tradefed results. In the latest
release there was a significant change that started parsing the xml
iteratively and this introduced a bug that would assing only a few
suites to all tests, depending on the number of modules present.

This release fixes that bug and also parses ASSUME_FAILURE tests
as expected failure.

# 1.26

This release fixes the excessive memory compsumption when parsing
the CTS XML results file. It now iteractively parses it, avoiding
allocating almost 1G of memory.

# 1.25

This release improves speed when processing tradefed testjobs by creating
batched of PluginScratch, instead of sending them one by one to the queue.

# 1.24

This release forces tradefed subtasks to use ci_fetch queue instead
of it fall in other quick queues.

# 1.23

This release fixes an undefined errmessage in tradefed plugin.

# 1.22

This release adds attachments file contents to files only. It was saving
to the database as well.

# 1.21

This release makes tradefed plugin add tests using build
and environment ids.


# 1.20.1

This release fixes again the bug that inserts wrong suite for
SuiteMetadata objects in tradefed plugin, and also hides url
tokens when logging 5XX server errors.
