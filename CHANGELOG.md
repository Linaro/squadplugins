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
