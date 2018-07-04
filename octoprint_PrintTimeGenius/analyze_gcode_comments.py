#!/usr/bin/env python

from __future__ import division
import re
import json
import sys
from collections import defaultdict

def get_analysis_from_gcode(machinecode_path):
  """Extracts the analysis data structure from the gocde.

  The analysis structure should look like this:
  http://docs.octoprint.org/en/master/modules/filemanager.html#octoprint.filemanager.analysis.GcodeAnalysisQueue
  (There is a bug in the documentation, estimatedPrintTime should be in seconds.)
  Return '{}' if there is no analysis information in the file.
  """
  dd = lambda: defaultdict(dd)
  analysis = dd()
  file_position = 0
  forward_progress = []
  with open(machinecode_path) as gcode_lines:
    for gcode_line in gcode_lines:
      file_position += len(gcode_line)
      if not gcode_line[0].startswith(";"):
        continue # This saves a lot of time

      # Match a slic3r PE filament line
      m = re.match('\s*;\s*filament used\s*=\s*([0-9.]+)\s*mm\s*\(([0-9.]+)cm3\)\s*', gcode_line)
      if m:
        analysis['filament']['tool0']['length'] = float(m.group(1))
        analysis['filament']['tool0']['volume'] = float(m.group(2))

      # Match a Slic3r PE print time estimate
      m = re.match('\s*;\s*estimated printing time\s*=\s(.*)\s*', gcode_line)
      if m:
        time_text = m.group(1)
        # Now extract the days, hours, minutes, and seconds
        analysis['estimatedPrintTime'] = 0
        for time_part in time_text.split(' '):
          for unit in [("h", 60*60),
                       ("m", 60),
                       ("s", 1),
                       ("d", 24*60*60)]:
            m = re.match('\s*([0-9.]+)' + re.escape(unit[0]), time_part)
            if m:
              analysis['estimatedPrintTime'] += float(m.group(1)) * unit[1]

      # Match Cura330 time estimate
      m = re.match('\s*;\s*TIME_ELAPSED\s*:\s*([0-9.]+)\s*', gcode_line)
      if m:
        time_text = m.group(1)
        time_elapsed = float(time_text)
        analysis['estimatedPrintTime'] = time_elapsed
        # We'll later convert forward_progress to reverse progress
        forward_progress.append([file_position, time_elapsed])

      # Match Cura330 filament used
      m = re.match('\s*;\s*Filament used\s*:\s*([0-9.]+)\s*m\s*', gcode_line)
      if m:
        filament_meters_text = m.group(1)
        analysis['filament']['tool0']['length'] = float(filament_meters_text) * 1000

  # Convert forward_progress to reverse progress if we found it.
  if forward_progress:
    analysis['progress'] = (
        [[0, analysis['estimatedPrintTime']]] +
        [[filepos/file_position, analysis['estimatedPrintTime'] - remaining]
          for [filepos, remaining] in forward_progress] +
        [[1, 0]])

  return json.loads(json.dumps(analysis))

if __name__ == "__main__":
  print(get_analysis_from_gcode(sys.argv[1]))
