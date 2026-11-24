import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TESTS_DIR)
PACKAGE_DIR = os.path.join(REPO_DIR, "octoprint_PrintTimeGenius")
ANALYZERS_DIR = os.path.join(PACKAGE_DIR, "analyzers")
FIXTURES_DIR = os.path.join(TESTS_DIR, "fixtures")

# printer_config's doctests expect it to be importable as a top-level module,
# and importing it through the package would pull in OctoPrint.
if PACKAGE_DIR not in sys.path:
  sys.path.insert(0, PACKAGE_DIR)


def fixture_path(name):
  return os.path.join(FIXTURES_DIR, name)
