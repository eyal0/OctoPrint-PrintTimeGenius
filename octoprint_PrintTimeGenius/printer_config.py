"""
Stores the printer config.

To test this file use:

python printer_config.py
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

def get_code(line, code):
  """Returns the code with the value attached, or "" if not found.  If the code is
  empty, it'll return it like that, too.

  >>> from printer_config import get_code
  >>> get_code("M1 X2 Y3", "M")
  'M1'
  >>> get_code("M1 X2 Y3", "Q")
  ''
  >>> get_code("M1 X2 Y3", "X")
  'X2'
  >>> get_code("M1 X2 Y3 MULTI99", "MULTI")
  'MULTI99'
  >>> get_code("M1 X2 Y3 MULTI99 E", "E")
  'E'
  >>> get_code("M200 D1.75", "D")
  'D1.75'
  """
  pos = line.find(code)
  if pos < 0:
    return ""
  ret = line[pos:].partition(" ")
  return ret[0]

def float_or_0(text):
  """Convert text to float or 0 if unable.

  >>> from printer_config import float_or_0
  >>> float_or_0("1.5")
  1.5
  >>> float_or_0("")
  0
  """
  try:
    return float(text)
  except ValueError:
    return 0

def codes_match(code0, code1, codes):
  """Given two lines stripped of spaces and comments, a and b, determine if they
  are the same for all the codes provided.  codes is a list of codes.  For each
  code, the code with value must match between the two lines for there to be a
  match.  If one line has the code but the other doesn't, that is a mismatch.
  If both are missing, that's a match.

  >>> from printer_config import codes_match
  >>> codes_match("A1 B2 C3", "A1 B2 C4", "AB")
  True
  >>> codes_match("A1 B2 C3", "A1 B2 C4", "ABC")
  False
  >>> codes_match("A1 B2 C3", "A1 B2 C4", ["A", "X"])
  True
  """
  for code in codes:
    if get_code(code0, code) != get_code(code1, code):
      return False
  return True

def merge_codes(code0, code1, codes):
  """For each code listed in codes, get the value from a and b and merge them,
  such that b can override the values in a.  codes not listed in codes aren't
  added at all.

  >>> from printer_config import merge_codes
  >>> merge_codes("A1 B2 C3", "A1 B5", "AC")
  'A1 C3'
  >>> merge_codes("A1 B2 C3", "A1 B5", "ABCD")
  'A1 B5 C3'
  """
  ret = []
  for code in codes:
    ret.append(get_code(code1, code) or get_code(code0, code))
  return " ".join(r for r in ret if r)

def clean_line(line):
  """Remove all comments and trim a line.

  >>> from printer_config import clean_line
  >>> clean_line("  foo ; bar  ;")
  'FOO'
  """
  return line.partition(";")[0].strip().upper()

class PrinterConfig:
  """Store just the lines needs for a printer's configuration.  This only stores
  the lines that we expect that we'll need to get accurate gcode analysis.

  >>> from printer_config import PrinterConfig
  >>> p = PrinterConfig()
  >>> p
  <class 'printer_config.PrinterConfig'>({'lines': []})
  >>> p += "M92 X1 Y2 Z3"
  >>> str(p)
  'M92 X1 Y2 Z3'
  >>> p += "M93"; str(p)
  'M92 X1 Y2 Z3'
  >>> p += "M92 X5"; str(p)
  'M92 X5 Y2 Z3'
  >>> p += "M92 T1 X5"; str(p)
  'M92 X5 Y2 Z3\\nM92 T1 X5'
  >>> p += "M92 X10"; str(p)
  'M92 T1 X5\\nM92 X10 Y2 Z3'

  >>> p = PrinterConfig()
  >>> p += "M200 D1.75"; str(p)
  'M200 D1.75'
  >>> p += "M200 D"; str(p)
  'M200 D1.75\\nM200 D'
  >>> p += "M200 D0 "; str(p)
  'M200 D1.75\\nM200 D0'
  >>> p += "M205 X1 Y2 Z3"; str(p)
  'M200 D1.75\\nM200 D0\\nM205 X1 Y2 Z3'
  >>> p += "M900 K12 J1"; str(p)
  'M200 D1.75\\nM200 D0\\nM205 X1 Y2 Z3\\nM900 K12'
  >>> p += "M200 S0 D1.99"; str(p)
  'M200 D0\\nM205 X1 Y2 Z3\\nM900 K12\\nM200 S0 D1.99'
  >>> p += "M200 S1 D456"; str(p)
  'M200 D0\\nM205 X1 Y2 Z3\\nM900 K12\\nM200 S1 D456'
  >>> p += "M200 S1 D0"; str(p)
  'M205 X1 Y2 Z3\\nM900 K12\\nM200 S1 D456\\nM200 S1 D0'

  >>> p = PrinterConfig()
  >>> p += "M204 X1"; str(p)
  'M204'

  >>> p = PrinterConfig()
  >>> p += "M220"; str(p)
  'M220'
  >>> p += "M220 S100"; str(p)
  'M220 S100'
  >>> p += "M220 S80"; str(p)
  'M220 S80'
  >>> p += "M220"; str(p)
  'M220 S80'
  >>> p += "M221 S100"; str(p)
  'M220 S80\\nM221 T0 S100'
  >>> p += "M221 S110"; str(p)
  'M220 S80\\nM221 T0 S110'
  >>> p += "M221 T0 S120"; str(p)
  'M220 S80\\nM221 T0 S120'
  >>> p += "M221 T1 S90"; str(p)
  'M220 S80\\nM221 T0 S120\\nM221 T1 S90'
  >>> p += "M221 T2 S80"; str(p)
  'M220 S80\\nM221 T0 S120\\nM221 T1 S90\\nM221 T2 S80'
  >>> p += "M221 S70"; str(p)
  'M220 S80\\nM221 T1 S90\\nM221 T2 S80\\nM221 T0 S70'
  >>> p += "M221 T1"; str(p)
  'M220 S80\\nM221 T2 S80\\nM221 T0 S70\\nM221 T1 S90'
  >>> p += "M221"; str(p)
  'M220 S80\\nM221 T2 S80\\nM221 T1 S90\\nM221 T0 S70'
  >>> p += "M221 T2"; str(p)
  'M220 S80\\nM221 T1 S90\\nM221 T0 S70\\nM221 T2 S80'
  >>> p += "M221 T3"; str(p)
  'M220 S80\\nM221 T1 S90\\nM221 T0 S70\\nM221 T2 S80\\nM221 T3'
  >>> p += "M221 T0"; str(p)
  'M220 S80\\nM221 T1 S90\\nM221 T2 S80\\nM221 T3\\nM221 T0 S70'
  >>> p += "M220"; str(p)
  'M221 T1 S90\\nM221 T2 S80\\nM221 T3\\nM221 T0 S70\\nM220 S80'
  """
  def __init__(self, lines=None):
    """Creates a new PrintConfig starting with the lines provided."""
    self.lines = lines or []

  def __iadd__(self, new_line):
    """Take a new line and add it into the config."""
    new_line = clean_line(new_line)
    mcode = get_code(new_line, "M")
    if not mcode:
      return self  #Save time by quiting early
    # add T0 when extruder index is ommited to correctly merge the mcodes
    if mcode == "M221":
      if get_code(new_line, "T") == "":
        new_line += " T0"
    for (mcodes, unique, merge) in [(["M92", "M201", "M203"], "MT", "MTXYZE"),
                                    (["M204"], "M", "MSPRT"),
                                    (["M205"], "M", "MBESTXYZJ"),
                                    (["M207"], "M", "MFSWZ"),
                                    (["M208"], "M", "MFRSW"),
                                    (["M220"], "M", "MS"),
                                    (["M221"], "MT", "MTS"),
                                    (["M900"], "M", "MK")]:
      if mcode in mcodes:
        new_lines = []
        for line in self.lines:
          # removes values saved without extruder index
          line_mcode = get_code(line, "M")
          if line_mcode == "M221":
            if get_code(line, "T") == "":
              line += " T0"
          if codes_match(line, new_line, unique):
            new_line = merge_codes(line, new_line, merge)
          else:
            new_lines.append(line)
        new_lines.append(merge_codes("", new_line, merge))
        self.lines = new_lines
        return self
    if mcode == "M200":
      #M200 is special because we need to save both the on and off
      new_lines = []
      for line in self.lines:
        if (codes_match(line, new_line, "MT") and
            (not float_or_0(get_code(line, "D")[1:])) ==
            (not float_or_0(get_code(new_line, "D")[1:]))):
          # We merge if the M and T match and also the value for D must be both
          # present or both absent or 0.
          new_line = merge_codes(line, new_line, "MTSD")
        else:
          new_lines.append(line)
      new_lines.append(merge_codes("", new_line, "MTSD"))
      self.lines = new_lines
      return self
    return self

  def __str__(self):
    return ''.join(c for c in "\n".join(self.lines)
                   if c.isdigit() or c.isalpha() or c.isspace() or c == '.')

  def __repr__(self):
    return "%s(%r)" % (self.__class__, self.__dict__)

  def as_list(self):
    """Return all the config as a list."""
    return list(self.lines)

if __name__ == '__main__':
  import doctest
  doctest.testmod()
