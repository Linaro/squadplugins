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
