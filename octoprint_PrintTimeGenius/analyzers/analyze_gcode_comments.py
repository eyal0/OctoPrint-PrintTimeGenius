#!/usr/bin/env python

from __future__ import division
import re
import json
import sys
from collections import defaultdict
import collections

dd = lambda: defaultdict(dd)

ALL_GCODE_LINE_ANALYZERS = []
TIME_UNITS_TO_SECONDS = defaultdict(
    lambda: 0,
    {
        "s": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "minute": 60,
        "minutes": 60,
        "h": 60*60,
        "hour": 60*60,
        "hours": 60*60,
        "d": 24*60*60,
        "day": 24*60*60,
        "days": 24*60*60,
    })

def process_time_text(time_text):
  """Given a string like "5 minutes, 4 seconds + 82 hours" return the total in seconds"""
  total = 0
  for time_part in re.finditer('([0-9.]+)\s*([a-zA-Z]+)', time_text):
    quantity = float(time_part.group(1))
    units = TIME_UNITS_TO_SECONDS[time_part.group(2)]
    total += quantity * units
  return total

def process_slic3r_filament(gcode_line):
  """Match a slic3r PE filament line"""
  ret = dd()
  m = re.match('\s*;\s*filament used\s*=\s*([0-9.]+)\s*mm\s*\(([0-9.]+)cm3\)\s*', gcode_line)
  if m:
    ret['filament']['tool0']['length'] = float(m.group(1))
    ret['filament']['tool0']['volume'] = float(m.group(2))
  return ret
ALL_GCODE_LINE_ANALYZERS.append(process_slic3r_filament)

def process_slic3r_print_time(gcode_line):
  """Match a Slic3r PE print time estimate"""
  ret = dd()
  m = re.match('\s*;\s*estimated printing time\s*=\s*(.*)\s*', gcode_line)
  if m:
    ret['estimatedPrintTime'] = process_time_text(m.group(1))
  return ret
ALL_GCODE_LINE_ANALYZERS.append(process_slic3r_print_time)

def process_cura330_print_time(gcode_line):
  """Match Cura330 time estimate"""
  ret = dd()
  m = re.match('\s*;\s*TIME_ELAPSED\s*:\s*([0-9.]+)\s*', gcode_line)
  if m:
    time_text = m.group(1)
    time_elapsed = float(time_text)
    ret['estimatedPrintTime'] = time_elapsed
    # We'll later convert forward_progress to reverse progress
    global forward_progress
    forward_progress.append([file_position, time_elapsed])
  return ret
ALL_GCODE_LINE_ANALYZERS.append(process_cura330_print_time)

def process_cura330_filament(gcode_line):
  """Match Cura330 filament used"""
  ret = dd()
  m = re.match('\s*;\s*Filament used\s*:\s*([0-9.]+)\s*m\s*', gcode_line)
  if m:
    filament_meters_text = m.group(1)
    ret['filament']['tool0']['length'] = float(filament_meters_text) * 1000
  return ret
ALL_GCODE_LINE_ANALYZERS.append(process_cura330_filament)

def process_cura1504_print_time(gcode_line):
  """Match Cura1504 time estimate"""
  ret = dd()
  m = re.match('\s*;\s*Print time\s*:\s*([0-9.]+)\s*m\s+(.*)\s*', gcode_line)
  if m:
    ret['estimatedPrintTime'] = process_time_text(m.group(1))
  return ret
ALL_GCODE_LINE_ANALYZERS.append(process_slic3r_print_time)

def process_simplify3d_print_time(gcode_line):
  """Match Simplify3D time estimate"""
  ret = dd()
  m = re.match('\s*;\s*Build time\s*:\s*(.*)\s*', gcode_line)
  if m:
    ret['estimatedPrintTime'] = process_time_text(m.group(1))
  return ret
ALL_GCODE_LINE_ANALYZERS.append(process_simplify3d_print_time)

def process_simplify3d_filament_length(gcode_line):
  """Match Simplify3D filament length"""
  ret = dd()
  m = re.match('\s*;\s*Filament length\s*:\s*([0-9.]+)\s*mm\s*', gcode_line)
  if m:
    filament_millimeters_text = m.group(1)
    ret['filament']['tool0']['length'] = float(filament_millimeters_text)
  return ret
ALL_GCODE_LINE_ANALYZERS.append(process_simplify3d_filament_length)

def process_simplify3d_filament_volume(gcode_line):
  """Match Simplify3D filament volume"""
  ret = dd()
  m = re.match('\s*;\s*Plastic volume\s*:\s*([0-9.]+)\s*mm\^3\s*', gcode_line)
  if m:
    filament_cubic_millimeters_text = m.group(1)
    ret['filament']['tool0']['volume'] = float(filament_cubic_millimeters_text) / 1000
  return ret
ALL_GCODE_LINE_ANALYZERS.append(process_simplify3d_filament_volume)

file_position = 0
forward_progress = []
def update(d, u):
  """Do deep updates of dict."""
  for k, v in u.iteritems():
    if isinstance(v, collections.Mapping):
      d[k] = update(d.get(k, dd()), v)
    else:
      d[k] = v
  return d

def get_analysis_from_gcode(machinecode_path):
  """Extracts the analysis data structure from the gocde.

  The analysis structure should look like this:
  http://docs.octoprint.org/en/master/modules/filemanager.html#octoprint.filemanager.analysis.GcodeAnalysisQueue
  (There is a bug in the documentation, estimatedPrintTime should be in seconds.)
  Return '{}' if there is no analysis information in the file.
  """
  analysis = dd()
  with open(machinecode_path) as gcode_lines:
    for gcode_line in gcode_lines:
      global file_position
      file_position += len(gcode_line)
      if not gcode_line.startswith(";"):
        continue # This saves a lot of time

      for gcode_analyzer in ALL_GCODE_LINE_ANALYZERS:
        new_result = gcode_analyzer(gcode_line)
        if new_result:
          # update doesn't work as we'd like on defaultdict
          analysis = update(analysis, new_result)

  # Convert forward_progress to reverse progress if we found it.
  if forward_progress:
    analysis['progress'] = (
        [[0, analysis['estimatedPrintTime']]] +
        [[filepos/file_position, analysis['estimatedPrintTime'] - remaining]
          for [filepos, remaining] in forward_progress] +
        [[1, 0]])
  return json.dumps(analysis)

if __name__ == "__main__":
  print(get_analysis_from_gcode(sys.argv[1]))
