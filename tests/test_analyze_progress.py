import json
import os
import platform
import shutil
import stat
import subprocess
import sys

import pytest

from conftest import ANALYZERS_DIR, fixture_path

SCRIPT = os.path.join(ANALYZERS_DIR, "analyze_progress.py")

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="the fake calculator relies on a shebang line")


def binary_suffix():
  """Mirrors how analyze_progress.py picks the binary for this machine."""
  machine = platform.machine()
  if platform.system() == "Darwin":
    return "darwin-" + machine
  return machine


def run(script, *args):
  return subprocess.run([sys.executable, script] + list(args),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        universal_newlines=True)


@pytest.fixture
def fake_calc(tmp_path):
  """Copy analyze_progress.py next to a fake calculator that prints canned output.

  Returns a function that writes the fake with the given stdout lines and exit
  code, and returns the path of the copied script.
  """
  script = str(tmp_path / "analyze_progress.py")
  shutil.copy(SCRIPT, script)

  def make(lines, exit_code=0, executable=True):
    binary = tmp_path / ("fake-calc." + binary_suffix())
    binary.write_text(
        "#!{python}\n"
        "import json, sys\n"
        "for line in {lines!r}:\n"
        "  print(line.replace('ARGV', json.dumps(sys.argv[1:])))\n"
        "sys.exit({exit_code})\n".format(python=sys.executable, lines=lines,
                                         exit_code=exit_code))
    mode = stat.S_IRUSR | stat.S_IWUSR
    if executable:
      mode |= stat.S_IXUSR
    binary.chmod(mode)
    return script
  return make


def test_progress_is_converted_to_time_remaining(fake_calc):
  script = fake_calc([
      "Some log line",
      "Progress: 0.1, 0.0, 10.0",
      "Progress: 0.2, 0.0, 20.0",
      "Progress: 0.5, 5.0, 100.0",
      "Progress: 0.9, 10.0, 200.0",
      "Progress: 1.0, 10.0, 210.0",
      'Analysis: {"estimatedPrintTime": 210.0, "filament": {"tool0": {"length": 10.0}}}',
  ])
  proc = run(script, "fake-calc", fixture_path("square.gcode"))
  assert proc.returncode == 0, proc.stderr
  result = json.loads(proc.stdout)
  assert result["estimatedPrintTime"] == 210.0
  assert result["filament"]["tool0"]["length"] == 10.0
  assert result["firstFilament"] == 0.5
  assert result["lastFilament"] == 0.9
  assert result["progress"] == [
      [0, 210.0], [0.1, 200.0], [0.5, 110.0], [0.9, 10.0], [1.0, 0.0], [1, 0]]


def test_infinite_and_nan_values_become_null(fake_calc):
  script = fake_calc([
      "Progress: 1.0, 1.0, 5.0",
      'Analysis: {"printingArea": {"minX": inf, "maxX": -inf, "minY": nan}}',
  ])
  proc = run(script, "fake-calc", fixture_path("square.gcode"))
  assert proc.returncode == 0, proc.stderr
  assert json.loads(proc.stdout)["printingArea"] == {
      "minX": None, "maxX": None, "minY": None}


def test_gcode_and_mcodes_are_passed_to_the_calculator(fake_calc):
  script = fake_calc([
      "Progress: 1.0, 1.0, 5.0",
      'Analysis: {"argv": ARGV}',
  ])
  gcode = fixture_path("square.gcode")
  proc = run(script, "fake-calc", gcode, "M92 X80\nM203 X100")
  assert proc.returncode == 0, proc.stderr
  assert json.loads(proc.stdout)["argv"] == [gcode, "M92 X80\nM203 X100"]


def test_calculator_exit_code_is_propagated(fake_calc):
  script = fake_calc(["Progress: 1.0, 1.0, 5.0"], exit_code=4)
  proc = run(script, "fake-calc", fixture_path("square.gcode"))
  assert proc.returncode == 4


def test_missing_calculator_exits_2(fake_calc):
  script = fake_calc([])
  proc = run(script, "no-such-calc", fixture_path("square.gcode"))
  assert proc.returncode == 2
  assert "Can't find" in proc.stderr


def test_non_executable_calculator_exits_3(fake_calc):
  script = fake_calc([], executable=False)
  proc = run(script, "fake-calc", fixture_path("square.gcode"))
  assert proc.returncode == 3
  assert "Not executable" in proc.stderr


real_marlin_calc = pytest.mark.skipif(
    not (platform.system() == "Linux" and platform.machine() == "x86_64"),
    reason="the bundled marlin-calc.x86_64 only runs on Linux x86_64")


@real_marlin_calc
def test_bundled_marlin_calc_runs_directly():
  binary = os.path.join(ANALYZERS_DIR, "marlin-calc.x86_64")
  proc = subprocess.run([binary, fixture_path("square.gcode")],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        universal_newlines=True)
  assert proc.returncode == 0, proc.stderr
  lines = proc.stdout.splitlines()
  assert any(line.startswith("Progress:") for line in lines)
  assert any(line.startswith("Analysis:") for line in lines)


@real_marlin_calc
def test_bundled_marlin_calc_through_analyze_progress():
  proc = run(SCRIPT, "marlin-calc", fixture_path("square.gcode"))
  assert proc.returncode == 0, proc.stderr
  result = json.loads(proc.stdout)

  total = result["estimatedPrintTime"]
  assert 5 < total < 60
  assert result["filament"]["tool0"]["length"] == pytest.approx(15.0)
  assert result["filament"]["tool0"]["volume"] > 0
  assert result["printingArea"]["minX"] == pytest.approx(10.0)
  assert result["printingArea"]["maxX"] == pytest.approx(50.0)
  assert result["dimensions"]["width"] == pytest.approx(40.0)

  progress = result["progress"]
  assert progress[0] == [0, total]
  assert progress[-1] == [1, 0]
  positions = [pos for pos, _ in progress]
  remaining = [rem for _, rem in progress]
  assert positions == sorted(positions)
  assert remaining == sorted(remaining, reverse=True)
  assert 0 < result["firstFilament"] <= result["lastFilament"] <= 1


@real_marlin_calc
def test_bundled_marlin_calc_honours_printer_config():
  gcode = fixture_path("square.gcode")
  default = run(SCRIPT, "marlin-calc", gcode)
  slow = run(SCRIPT, "marlin-calc", gcode, "M203 X5 Y5\nM201 X50 Y50")
  assert default.returncode == 0, default.stderr
  assert slow.returncode == 0, slow.stderr
  assert (json.loads(slow.stdout)["estimatedPrintTime"] >
          json.loads(default.stdout)["estimatedPrintTime"])
