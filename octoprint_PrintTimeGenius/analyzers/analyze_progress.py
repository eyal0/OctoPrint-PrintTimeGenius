#!/usr/bin/env python

from __future__ import print_function
import subprocess
import sys
import json
import os
import platform

def main():
  binary_base_name = sys.argv[1]
  machine = platform.machine()
  if platform.system() == "Darwin":
    machine = "darwin-" + machine
  elif platform.system() == "Windows":
    machine = "windows-" + machine + ".exe"
  gcode = sys.argv[2]
  mcodes = None
  if len(sys.argv) > 3:
    mcodes = sys.argv[3]
  cmd = [
      os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                   "{}.{}".format(binary_base_name, machine)),
      gcode]
  if mcodes:
    cmd += [mcodes]
  print("Running: {}".format(" ".join('"{}"'.format(c) for c in cmd)), file=sys.stderr)
  if not os.path.isfile(cmd[0]):
    print("Can't find: {}".format(cmd[0]), file=sys.stderr)
    sys.exit(2)
  if not os.access(cmd[0], os.X_OK):
    print("Not executable: {}".format(cmd[0]), file=sys.stderr)
    sys.exit(3)
  try:
    output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
  except Exception as e:
    print(e, file=sys.stderr)
    sys.exit(1)
  progress = []
  result = {}
  first_filament = None
  last_filament = None
  max_filament = None
  most_recent_progress = float("-inf")
  last_row = None
  for line in output.stdout:
    if not line:
      continue
    if line.startswith(b"Progress:"):
      line = line[len("Progress:"):]
      (filepos, filament, time) = map(float, line.split(b","))
      if filament > 0 and not first_filament:
        first_filament = filepos
      if not max_filament or filament > max_filament:
        last_filament = filepos
        max_filament = filament
        last_filament_row = [filepos, time]
      if filepos == first_filament or most_recent_progress+60 < time:
        most_recent_progress = time
        progress.append([filepos, time])
        last_row = None
      else:
        last_row = [filepos, time]
    elif line.startswith(b"Analysis:"):
      line = line[len("Analysis:"):]
      result.update(json.loads(line))
  if last_row:
    progress.append(last_row)
  result["firstFilament"] = first_filament
  result["lastFilament"] = last_filament
  total_time = progress[-1][1]
  result["progress"] = [[0, total_time]]
  for progress_entry in progress:
    if last_filament_row and progress_entry[0] > last_filament_row[0]:
      # Squeeze this row into the right spot.
      result["progress"].append([last_filament_row[0],
                                 total_time-last_filament_row[1]])
      last_filament_row = None
    if not last_filament_row or progress_entry[0] != last_filament_row[0]:
      if result["progress"][-1][0] == progress_entry[0]:
        # Overwrite instead of append.
        result["progress"][-1] = ([progress_entry[0],
                                   total_time-progress_entry[1]])
      else:
        result["progress"].append(
            [progress_entry[0],
             total_time-progress_entry[1]])
  if last_filament_row:
    # We didn't ge to add it earlier so add it now.
    result["progress"].append([last_filament_row[0],
                               total_time-last_filament_row[1]])
  result["progress"].append([1, 0])
  result["estimatedPrintTime"] = total_time
  print(json.dumps(result))
  sys.exit(output.wait())

if __name__ == "__main__":
  main()
