import importlib.util
import json
import os
import subprocess
import sys

import pytest

from conftest import ANALYZERS_DIR, fixture_path

SCRIPT = os.path.join(ANALYZERS_DIR, "analyze_gcode_comments.py")


@pytest.fixture
def analyzer():
  """A freshly imported copy of the module, because it keeps state in globals."""
  spec = importlib.util.spec_from_file_location("analyze_gcode_comments", SCRIPT)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def all_parsers(module):
  return set(f for funcs in module.register_parser.all.values() for f in funcs)


def run_cli(*args):
  return subprocess.run([sys.executable, SCRIPT] + list(args),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        universal_newlines=True)


@pytest.mark.parametrize("text,seconds", [
    ("", 0),
    ("42s", 42),
    ("1h 2m 3s", 3723),
    ("1d 1h", 90000),
    ("1 hour 30 minutes", 5400),
    ("2 days, 3 hours + 4 minutes 5 seconds", 2 * 86400 + 3 * 3600 + 4 * 60 + 5),
    ("1.5 minutes", 90),
    ("5 fortnights", 0),
])
def test_process_time_text(analyzer, text, seconds):
  assert analyzer.process_time_text(text) == seconds


def test_registry_has_expected_parser_groups(analyzer):
  for name in ["slic3r", "slic3r_pe", "cura330", "cura1504", "simplify3d",
               "slic3r_pe_print_time", "slic3r_pe_print_time_remaining"]:
    assert analyzer.register_parser.all[name], name


@pytest.mark.parametrize("line,expected", [
    ("; filament used = 1234.5mm (2.9cm3)", {"length": 1234.5, "volume": 2.9}),
    ("; filament used [mm] = 1500.25", {"length": 1500.25}),
    ("; filament used [cm3] = 3.5", {"volume": 3.5}),
])
def test_slic3r_filament(analyzer, line, expected):
  assert analyzer.process_slic3r_filament(line)["filament"]["tool0"] == expected


@pytest.mark.parametrize("line,seconds", [
    ("; estimated printing time = 1h 2m 3s", 3723),
    ("; estimated printing time (normal mode) = 10m 5s", 605),
])
def test_slic3r_print_time(analyzer, line, seconds):
  assert analyzer.process_slic3r_print_time(line)["estimatedPrintTime"] == seconds


def test_slic3r_print_time_remaining_records_progress(analyzer):
  analyzer.file_position = 100
  assert analyzer.process_slic3r_print_time_remaining("M73 P10 R5") == {}
  analyzer.file_position = 200
  analyzer.process_slic3r_print_time_remaining("M73 R2")
  assert analyzer.reverse_progress == [[100, 300.0], [200, 120.0]]
  assert analyzer.first_filament_filepos == 100


def test_cura330_print_time_records_forward_progress(analyzer):
  analyzer.file_position = 50
  result = analyzer.process_cura330_print_time(";TIME_ELAPSED:123.5")
  assert result["estimatedPrintTime"] == 123.5
  assert analyzer.forward_progress == [[50, 123.5]]


def test_cura330_filament_converts_meters(analyzer):
  result = analyzer.process_cura330_filament(";Filament used: 2.5m")
  assert result["filament"]["tool0"]["length"] == 2500


@pytest.mark.xfail(strict=True, reason=(
    "process_cura1504_print_time passes only the number to process_time_text, "
    "dropping the unit, so the estimate is always 0"))
def test_cura1504_print_time(analyzer):
  result = analyzer.process_cura1504_print_time(";Print time: 90 m whatever")
  assert result["estimatedPrintTime"] == 90 * 60


def test_simplify3d_parsers(analyzer):
  assert analyzer.process_simplify3d_print_time(
      ";   Build time: 2 hours 5 minutes")["estimatedPrintTime"] == 7500
  assert analyzer.process_simplify3d_filament_length(
      ";   Filament length: 4567.8 mm (4.57 m)")["filament"]["tool0"]["length"] == 4567.8
  assert analyzer.process_simplify3d_filament_volume(
      ";   Plastic volume: 10987.6 mm^3 (10.99 cc)")["filament"]["tool0"]["volume"] == pytest.approx(10.9876)


def test_parsers_ignore_unrelated_lines(analyzer):
  for parser in all_parsers(analyzer):
    assert not parser("G1 X10 Y10 E1"), parser.__name__
    assert not parser("; just a comment"), parser.__name__


def test_update_merges_nested_dicts(analyzer):
  d = {"filament": {"tool0": {"length": 1}}, "a": 1}
  analyzer.update(d, {"filament": {"tool0": {"volume": 2}, "tool1": {"length": 3}}})
  assert d == {"a": 1, "filament": {"tool0": {"length": 1, "volume": 2},
                                    "tool1": {"length": 3}}}


def test_analysis_of_file_without_metadata_is_empty(analyzer):
  assert json.loads(analyzer.get_analysis_from_gcode(
      fixture_path("square.gcode"), all_parsers(analyzer))) == {}


def test_analysis_of_prusaslicer_file(analyzer):
  result = json.loads(analyzer.get_analysis_from_gcode(
      fixture_path("prusaslicer.gcode"), all_parsers(analyzer)))
  assert result["estimatedPrintTime"] == 3723
  assert result["filament"]["tool0"] == {"length": 1234.5, "volume": 2.97}
  progress = result["progress"]
  assert progress[0] == [0, 3723]
  assert progress[-1] == [1, 0]
  assert [remaining for _, remaining in progress[1:-1]] == [600, 300, 0]
  assert 0 < result["firstFilament"] < 1
  assert progress == sorted(progress)


def test_analysis_of_cura_file(analyzer):
  result = json.loads(analyzer.get_analysis_from_gcode(
      fixture_path("cura.gcode"), all_parsers(analyzer)))
  assert result["estimatedPrintTime"] == 600
  assert result["filament"]["tool0"]["length"] == 1500
  assert [remaining for _, remaining in result["progress"]] == [600, 500, 200, 0, 0]


def test_analysis_of_simplify3d_file(analyzer):
  result = json.loads(analyzer.get_analysis_from_gcode(
      fixture_path("simplify3d.gcode"), all_parsers(analyzer)))
  assert result["estimatedPrintTime"] == 5400
  assert result["filament"]["tool0"]["length"] == 4567.8
  assert "progress" not in result


def test_cli_uses_all_parsers_by_default():
  proc = run_cli(fixture_path("prusaslicer.gcode"))
  assert proc.returncode == 0, proc.stderr
  result = json.loads(proc.stdout)
  assert result["estimatedPrintTime"] == 3723
  assert result["filament"]["tool0"]["length"] == 1234.5


def test_cli_with_parser_subset_as_the_plugin_calls_it():
  proc = run_cli(fixture_path("prusaslicer.gcode"), "--parsers",
                 "slic3r_pe_print_time", "slic3r_pe_print_time_remaining")
  assert proc.returncode == 0, proc.stderr
  result = json.loads(proc.stdout)
  assert result["estimatedPrintTime"] == 3723
  assert "filament" not in result
  assert result["progress"][0] == [0, 3723]


def test_cli_rejects_unknown_parser():
  proc = run_cli(fixture_path("prusaslicer.gcode"), "--parsers", "bogus")
  assert proc.returncode != 0
  assert "bogus is not a valid parser" in proc.stderr
