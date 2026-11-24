import doctest

import pytest

import printer_config
from printer_config import (PrinterConfig, clean_line, codes_match, float_or_0,
                            get_code, merge_codes)


def test_doctests():
  result = doctest.testmod(printer_config)
  assert result.attempted > 0
  assert result.failed == 0


@pytest.mark.parametrize("line,code,expected", [
    ("G1 X10 Y20", "G", "G1"),
    ("G1 X10 Y20", "Y", "Y20"),
    ("G1 X10 Y20", "Z", ""),
    ("M221 T1 S90", "T", "T1"),
    ("", "M", ""),
])
def test_get_code(line, code, expected):
  assert get_code(line, code) == expected


@pytest.mark.parametrize("text,expected", [
    ("3", 3.0),
    ("-2.5", -2.5),
    ("abc", 0),
    ("", 0),
])
def test_float_or_0(text, expected):
  assert float_or_0(text) == expected


def test_codes_match_missing_in_both_is_a_match():
  assert codes_match("M92 X1", "M92 X1", "MT")


def test_codes_match_missing_in_one_is_a_mismatch():
  assert not codes_match("M92 T0 X1", "M92 X1", "MT")


def test_merge_codes_second_line_overrides():
  assert merge_codes("M203 X1 Y2 Z3", "M203 Y9", "MXYZ") == "M203 X1 Y9 Z3"


def test_merge_codes_drops_unlisted_codes():
  assert merge_codes("M204 S1 Q7", "", "MS") == "M204 S1"


@pytest.mark.parametrize("line,expected", [
    ("m92 x80 ; steps", "M92 X80"),
    ("; only a comment", ""),
    ("   G28   ", "G28"),
])
def test_clean_line(line, expected):
  assert clean_line(line) == expected


def test_non_m_lines_are_ignored():
  p = PrinterConfig()
  p += "G1 X10 Y10"
  p += "; M92 X1"
  p += ""
  assert p.as_list() == []


def test_unknown_mcodes_are_ignored():
  p = PrinterConfig()
  p += "M104 S200"
  p += "M106 S255"
  assert p.as_list() == []


def test_steps_per_unit_are_merged_per_tool():
  p = PrinterConfig()
  p += "M92 X80 Y80 Z400 E93"
  p += "M92 T1 E100"
  p += "M92 E95"
  assert p.as_list() == ["M92 T1 E100", "M92 X80 Y80 Z400 E95"]


@pytest.mark.parametrize("first,second,expected", [
    ("M201 X1000 Y1000", "M201 Z100", "M201 X1000 Y1000 Z100"),
    ("M203 X300 Y300", "M203 X200", "M203 X200 Y300"),
    ("M204 P500 T1000", "M204 R800", "M204 P500 R800 T1000"),
    ("M205 X8 Y8", "M205 J0.02", "M205 X8 Y8 J0.02"),
    ("M207 S4 F2400", "M207 Z0.2", "M207 F2400 S4 Z0.2"),
    ("M208 S1 F1800", "M208 R2400", "M208 F1800 R2400 S1"),
    ("M900 K0.05", "M900 K0.1", "M900 K0.1"),
])
def test_later_settings_override_earlier_ones(first, second, expected):
  p = PrinterConfig()
  p += first
  p += second
  assert str(p).split("\n")[-1].split() == expected.split()
  assert len(p.as_list()) == 1


def test_as_list_returns_a_copy():
  p = PrinterConfig(["M92 X80"])
  lines = p.as_list()
  lines.append("M92 X1")
  assert p.as_list() == ["M92 X80"]


def test_round_trip_through_as_list():
  p = PrinterConfig()
  for line in ["M92 X80 Y80", "M203 X300", "M221 T1 S95", "M900 K0.04"]:
    p += line
  restored = PrinterConfig()
  for line in p.as_list():
    restored += line
  assert restored.as_list() == p.as_list()
