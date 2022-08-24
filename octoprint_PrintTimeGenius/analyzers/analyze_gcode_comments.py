#!/usr/bin/env python

from __future__ import division
import re
import json
import sys
from collections import defaultdict
import argparse
if float('.'.join((str(sys.version_info.major), str(sys.version_info.minor)))) < 3.3:
  from collections import Mapping as collections_Mapping
else:
  from collections.abc import Mapping as collections_Mapping

dd = lambda: defaultdict(dd)

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

def makeRegistrar():
  registry = defaultdict(list)
  def r(name):
    def registrar(func):
      registry[name].append(func)
      # normally a decorator returns a wrapped function, but here we return func
      # unmodified, after registering it
      return func
    return registrar
  r.all = registry
  return r

register_parser = makeRegistrar()

@register_parser("slic3r_pe_filament")
@register_parser("slic3r_filament")
@register_parser("slic3r")
@register_parser("slic3r_pe")
def process_slic3r_filament(gcode_line):
  """Match a slic3r PE filament line"""
  ret = dd()
  m = re.match('\s*;\s*filament used\s*=\s*([0-9.]+)\s*mm\s*\(([0-9.]+)cm3\)\s*', gcode_line)
  if m:
    ret['filament']['tool0']['length'] = float(m.group(1))
    ret['filament']['tool0']['volume'] = float(m.group(2))
  return ret

@register_parser("slic3r_pe_print_time")
@register_parser("slic3r_print_time")
@register_parser("slic3r")
@register_parser("slic3r_pe")
def process_slic3r_print_time(gcode_line):
  """Match a Slic3r PE print time estimate"""
  ret = dd()
  m = re.match('\s*;\s*estimated printing time(?:.*normal.*)?\s*=\s*(.*)\s*', gcode_line)
  if m:
    ret['estimatedPrintTime'] = process_time_text(m.group(1))
  return ret

@register_parser("slic3r_pe_print_time_remaining")
@register_parser("slic3r_pe")
def process_slic3r_print_time_remaining(gcode_line):
  """Match a Slic3r PE print time remaining estimate"""
  ret = dd()
  m = re.match('\s*M73\s+(?:P([0-9.]+)\s+)?R([0-9.]+)\s*', gcode_line)
  if m:
    minutes_text = m.group(2)
    minutes_elapsed = float(minutes_text)
    global reverse_progress
    if not reverse_progress:
      # This is the first reverse progress so it is also the first filament.
      global first_filament_filepos
      first_filament_filepos = file_position
    reverse_progress.append([file_position, minutes_elapsed*60])
  return ret

@register_parser("cura330_print_time")
@register_parser("cura330")
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

@register_parser("cura330_filament")
@register_parser("cura330")
@register_parser("cura1504")
@register_parser("cura1504_filament")
def process_cura330_filament(gcode_line):
  """Match Cura330 filament used"""
  ret = dd()
  m = re.match('\s*;\s*Filament used\s*:\s*([0-9.]+)\s*m\s*', gcode_line)
  if m:
    filament_meters_text = m.group(1)
    ret['filament']['tool0']['length'] = float(filament_meters_text) * 1000
  return ret

@register_parser("cura1504_print_time")
@register_parser("cura1504")
def process_cura1504_print_time(gcode_line):
  """Match Cura1504 time estimate"""
  ret = dd()
  m = re.match('\s*;\s*Print time\s*:\s*([0-9.]+)\s*m\s+(.*)\s*', gcode_line)
  if m:
    ret['estimatedPrintTime'] = process_time_text(m.group(1))
  return ret

@register_parser("simplify3d_print_time")
@register_parser("simplify3d")
def process_simplify3d_print_time(gcode_line):
  """Match Simplify3D time estimate"""
  ret = dd()
  m = re.match('\s*;\s*Build time\s*:\s*(.*)\s*', gcode_line)
  if m:
    ret['estimatedPrintTime'] = process_time_text(m.group(1))
  return ret

# Simplify3D isn't able to calculate multiple filament correctly.
@register_parser("simplify3d_filament_length")
@register_parser("simplify3d")
def process_simplify3d_filament_length(gcode_line):
  """Match Simplify3D filament length"""
  ret = dd()
  m = re.match('\s*;\s*Filament length\s*:\s*([0-9.]+)\s*mm\s*', gcode_line)
  if m:
    filament_millimeters_text = m.group(1)
    ret['filament']['tool0']['length'] = float(filament_millimeters_text)
  return ret

# Simplify3D isn't able to calculate multiple filament correctly.
@register_parser("simplify3d_filament_volume")
@register_parser("simplify3d")
def process_simplify3d_filament_volume(gcode_line):
  """Match Simplify3D filament volume"""
  ret = dd()
  m = re.match('\s*;\s*Plastic volume\s*:\s*([0-9.]+)\s*mm\^3\s*', gcode_line)
  if m:
    filament_cubic_millimeters_text = m.group(1)
    ret['filament']['tool0']['volume'] = float(filament_cubic_millimeters_text) / 1000
  return ret

file_position = 0
forward_progress = []
reverse_progress = []
first_filament_filepos = None
def update(d, u):
  """Do deep updates of dict."""
  for k, v in u.items():
    if isinstance(v, collections_Mapping):
      d[k] = update(d.get(k, dd()), v)
    else:
      d[k] = v
  return d

def get_analysis_from_gcode(machinecode_path, parsers):
  """Extracts the analysis data structure from the gocde.

  The parsers are functions that, when run on a line of gcode, return a
  defaultdict of type dd() that has results to be merged into the output
  dictionary.

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
      if not gcode_line or gcode_line[0] not in ';M':
        continue # This saves a lot of time

      for gcode_analyzer in parsers:
        new_result = gcode_analyzer(gcode_line)
        if new_result:
          # update doesn't work as we'd like on defaultdict
          analysis = update(analysis, new_result)

  # Convert forward_progress to reverse progress if we found it.
  if forward_progress:
    if 'progress' not in analysis:
      analysis['progress'] = []
    analysis['progress'] += [
        [filepos/file_position, analysis['estimatedPrintTime'] - elapsed]
        for [filepos, elapsed] in forward_progress]
  if reverse_progress:
    if 'progress' not in analysis:
      analysis['progress'] = []
    analysis['progress'] += [
        [filepos/file_position, remaining]
         for [filepos, remaining] in reverse_progress]
  if 'progress' in analysis:
    analysis['progress'] += [
        [0, analysis['estimatedPrintTime']],
        [1, 0]]
    analysis['progress'].sort()
  if first_filament_filepos:
    analysis['firstFilament'] = first_filament_filepos / file_position
  return json.dumps(analysis)

if __name__ == "__main__":
  help_epilog = ("Possible parsers and the functions that will be run:\n\n     " +
                 "\n     ".join("%s: %s" % (k, ('\n' + (len(k)+7) * ' ').join(x.__name__ for x in v))
                                for (k, v) in sorted(register_parser.all.items())))
  parser = argparse.ArgumentParser(description='Analyze gcode text for printing info.', epilog=help_epilog, formatter_class=argparse.RawDescriptionHelpFormatter)
  class ParsersAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
      super(ParsersAction, self).__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, namespace, values, option_string=None):
      funcs = []
      for v in values:
        if v not in register_parser.all:
          raise argparse.ArgumentTypeError("%s is not a valid parser" % v)
      setattr(namespace, self.dest,
              getattr(namespace, self.dest).union(u for v in values for u in register_parser.all[v]))

  parser.add_argument('--parsers', metavar='P', nargs='+', action=ParsersAction,
                      default=set(),
                      help='the parsers to use')
  parser.add_argument('infile',
                      help='the file to process')

  args = parser.parse_args()
  parsers = args.parsers
  if not parsers:
    parsers = set(u for v in register_parser.all.values() for u in v)
  print(get_analysis_from_gcode(args.infile, parsers))
