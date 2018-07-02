#!/usr/bin/env python

import re
import json
import sys
from collections import defaultdict

def get_analysis_from_gcode(machinecode_path):
  """Extracts the analysis data structure from the gocde.

  The analysis structure should look like this:
  http://docs.octoprint.org/en/master/modules/filemanager.html#octoprint.filemanager.analysis.GcodeAnalysisQueue
  (There is a bug in the documentation, estimatedPrintTime should be in seconds.)
  Return None if there is no analysis information in the file.
  """
  filament_length = None
  filament_volume = None
  printing_seconds = None
  with open(machinecode_path) as gcode_lines:
    for gcode_line in gcode_lines:
      if not gcode_line[0].startswith(";"):
        continue # This saves a lot of time
      m = re.match('\s*;\s*filament used\s*=\s*([0-9.]+)\s*mm\s*\(([0-9.]+)cm3\)\s*', gcode_line)
      if m:
        filament_length = float(m.group(1))
        filament_volume = float(m.group(2))
      m = re.match('\s*;\s*estimated printing time\s*=\s(.*)\s*', gcode_line)
      if m:
        time_text = m.group(1)
        # Now extract the days, hours, minutes, and seconds
        printing_seconds = 0
        for time_part in time_text.split(' '):
          for unit in [("h", 60*60),
                       ("m", 60),
                       ("s", 1),
                       ("d", 24*60*60)]:
            m = re.match('\s*([0-9.]+)' + re.escape(unit[0]), time_part)
            if m:
              printing_seconds += float(m.group(1)) * unit[1]
  # Now build up the analysis struct
  analysis = None
  if printing_seconds is not None or filament_length is not None or filament_volume is not None:
    dd = lambda: defaultdict(dd)
    analysis = dd()
    if printing_seconds is not None:
      analysis['estimatedPrintTime'] = printing_seconds
    if filament_length is not None:
      analysis['filament']['tool0']['length'] = filament_length
    if filament_volume is not None:
      analysis['filament']['tool0']['volume'] = filament_volume
    # Convert it to a regular string.
    return json.loads(json.dumps(analysis))
  return None

if __name__ == "__main__":
  print(get_analysis_from_gcode(sys.argv[1]))
