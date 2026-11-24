import json
import platform
import shlex
import subprocess

import pytest

from conftest import fixture_path

pytest.importorskip("octoprint")

import octoprint_PrintTimeGenius as plugin_module  # noqa: E402


@pytest.fixture(scope="module")
def plugin():
  plugin_module.__plugin_load__()
  implementation = plugin_module.__plugin_implementation__
  # Normally injected by OctoPrint's plugin manager.
  implementation._plugin_version = "0.0.0-test"
  return implementation


def test_plugin_registers_its_hooks(plugin):
  assert set(plugin_module.__plugin_hooks__) == {
      "octoprint.plugin.softwareupdate.check_config",
      "octoprint.filemanager.analysis.factory",
      "octoprint.printer.estimation.factory",
      "octoprint.comm.protocol.gcode.sent",
      "octoprint.comm.protocol.gcode.received",
      "octoprint.printer.handle_connect",
  }


def test_marlin_calc_is_the_only_analyzer_enabled_by_default(plugin):
  analyzers = plugin.get_settings_defaults()["analyzers"]
  assert len(analyzers) == 3
  enabled = [a for a in analyzers if a["enabled"]]
  assert len(enabled) == 1
  assert "marlin-calc" in enabled[0]["command"]


def run_default_analyzer(plugin, index, mcodes=""):
  command = plugin.get_settings_defaults()["analyzers"][index]["command"]
  command = command.format(gcode=fixture_path("prusaslicer.gcode"), mcodes=mcodes)
  proc = subprocess.run(shlex.split(command), stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, universal_newlines=True)
  assert proc.returncode == 0, proc.stderr
  return json.loads(proc.stdout)


@pytest.mark.skipif(platform.system() == "Windows",
                    reason="commands are split with POSIX shell rules")
@pytest.mark.parametrize("index", [0, 2])
def test_default_comment_analyzer_commands_run(plugin, index):
  assert run_default_analyzer(plugin, index)["estimatedPrintTime"] == 3723


@pytest.mark.skipif(
    not (platform.system() == "Linux" and platform.machine() == "x86_64"),
    reason="the bundled marlin-calc.x86_64 only runs on Linux x86_64")
def test_default_marlin_calc_command_runs(plugin):
  result = run_default_analyzer(plugin, 1, mcodes="M92 X80 Y80 Z400 E93")
  assert result["estimatedPrintTime"] > 0
  assert result["progress"][-1] == [1, 0]


def test_update_information_points_at_github(plugin):
  info = plugin.get_update_information()["PrintTimeGenius"]
  assert info["type"] == "github_release"
  assert info["user"] == "eyal0"
  assert info["repo"] == "OctoPrint-PrintTimeGenius"
