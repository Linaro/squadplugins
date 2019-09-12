#!/usr/bin/env python3

import unittest

loader = unittest.TestLoader()
tests = loader.discover('test')
runner = unittest.runner.TextTestRunner()
runner.run(tests)
