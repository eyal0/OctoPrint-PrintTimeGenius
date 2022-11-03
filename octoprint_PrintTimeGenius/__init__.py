# coding=utf-8
from __future__ import absolute_import
from __future__ import division

import octoprint.plugin
import octoprint.filemanager.storage
from octoprint.printer.estimation import PrintTimeEstimator
from octoprint.filemanager.analysis import GcodeAnalysisQueue
from octoprint.filemanager.analysis import AnalysisAborted
from flask_babel import gettext
import logging
import bisect
from pkg_resources import parse_version
import sarge
import json
import shlex
import time
import os
import sys
import types
import yaml
import flask
import pkg_resources
import errno
from threading import Timer
from collections import defaultdict
from .printer_config import PrinterConfig
import psutil
import collections

def _interpolate(point, left, right):
  """Use the point to interpolate a value from left and right.  point should be a
  number.  left and right are each lists of the same length.  The return value
  is a new list the same length as left and right with each value in the list
  adjusted to be the weighted average between left and right such that the first
  value of the return value is equal to the point.
  """
  # ratio 0 means use the left_index one, 1 means the right_index one
  ratio = (point - left[0])/(right[0] - left[0])
  return [x[0]*(1-ratio) + x[1]*ratio
          for x in zip(left, right)]

def _interpolate_list(l, point):
  """Use the point value to interpolate a new value from the list.
  l must be a sorted list of lists.  point is a value to interpolate.
  Return None if the point is out of range.
  If the result is not None, return interpolated array."""
  # ge is the index of the first element >= point
  if point < l[0][0] or point > l[-1][0]:
    return None
  if point == l[0][0]:
    return l[0]
  if point == l[-1][0]:
    return l[-1]
  right_index = bisect.bisect_right(l, [point])
  left_index = right_index - 1
  right = l[right_index]
  left = l[left_index]
  return _interpolate(point, left, right)

class GeniusEstimator(PrintTimeEstimator):
  """Uses previous generated analysis to estimate print time remaining."""

  def __init__(self, job_type, printer, file_manager, logger, current_history):
    super(GeniusEstimator, self).__init__(job_type)
    self._path = printer.get_current_job()["file"]["path"]
    self._origin = printer.get_current_job()["file"]["origin"]
    self._file_manager = file_manager
    self._logger = logger
    self._current_history = current_history
    self._current_progress_index = -1 # Points to the entry that we used for remaining time
    self._called_genius_yet = False
    self.recheck_metadata = True
    self._progress = None
    self._metadata = None

  def _get_metadata(self):
    try:
      self._metadata = self._file_manager.get_metadata(self._origin, self._path)
    except octoprint.filemanager.NoSuchStorage:
      #The metadata is not found or maybe not yet written.
      self._metadata = None
    if not self._metadata or not "analysis" in self._metadata or not "progress" in self._metadata["analysis"]:
      self._progress = None
    else:
      self._progress = self._metadata["analysis"]["progress"]

  def _genius_estimate(self, progress, printTime, unused_cleanedPrintTime, unused_statisticalTotalPrintTime, unused_statisticalTotalPrintTimeType):
    """Return an estimate for the total print time remaining.
    Returns (remaining_time_in_seconds, "genius") or None if it failed.
    """
    # The progress is a sorted list of pairs [filepos, remaining_time].
    # It maps from filepos to estimated remaining time.
    # filepos is between 0 and 1, same as progress.
    # actual progress is in seconds
    if not self._called_genius_yet:
      # Pretend like the first call is always at progress 0
      progress = 0
      self._called_genius_yet = True
    if self.recheck_metadata:
      self._get_metadata()
      self.recheck_metadata = False
    if not self._progress:
      return None
    if printTime is None:
      # We don't know the printTime so far, only the progress which we want to calculate.
      return _interpolate_list(self._progress, progress)[1], "genius"

    # If we do have a printTime, we can use it.  Can we
    # increment/decrement the current_progress_index?  We do this
    # instead of a binary search because we're usually in the right
    # place already so this is faster.
    while (self._current_progress_index + 1 < len(self._progress) and
           progress >= self._progress[self._current_progress_index+1][0]):
      self._current_progress_index += 1
    while (self._current_progress_index > 0 and
           progress < self._progress[self._current_progress_index][0]):
      self._current_progress_index -= 1
    if self._current_progress_index < 0:
      return None # We're not even in range yet.
    # We advanced to a new index, let's make new estimates.
    if (not "firstFilamentPrintTime" in self._current_history and
        progress > self._metadata["analysis"]["firstFilament"]):
      self._current_history["firstFilamentPrintTime"] = printTime
    if (not "lastFilamentPrintTime" in self._current_history or
        progress <= self._metadata["analysis"]["lastFilament"]):
      self._current_history["lastFilamentPrintTime"] = printTime
    interpolation = _interpolate(progress, self._progress[self._current_progress_index], self._progress[self._current_progress_index+1])
    # This is our best guess for the total print time.
    return interpolation[1], "genius"

  def estimate(self, progress, printTime, cleanedPrintTime, statisticalTotalPrintTime, statisticalTotalPrintTimeType):
    try:
      default_result = super(GeniusEstimator, self).estimate(
          progress, printTime, cleanedPrintTime,
          statisticalTotalPrintTime, statisticalTotalPrintTimeType)
      result = default_result # This is the result that we will report.
      genius_result = default_result # Genius result defaults to the default_result
      if not self._called_genius_yet:
        self._logger.debug("*** Starting CSV output for {}:{} ***".format(self._origin, self._path))
        self._logger.debug(", " + ", ".join(map(str, ["Print Time", "Built-in Result", "Built-in Result Type", "Genius Result", "Genius Result Type", "Progress of file read"])))
      try:
        genius_result = self._genius_estimate(
            progress, printTime, cleanedPrintTime,
            statisticalTotalPrintTime, statisticalTotalPrintTimeType)
        if genius_result:
          result = genius_result # If genius worked, use it.
      except Exception as e:
        self._logger.warning("Failed to estimate, ignoring.", exc_info=e)
      if not default_result:
        default_result = (0, 'genius')
      if not genius_result:
        genius_result = (0, 'genius')
      self._logger.debug(", " + ", ".join(map(str, [printTime, default_result[0], default_result[1], genius_result[0], genius_result[1], progress])))
      return result
    except Exception as e:
      self._logger.error("Failed to estimate", exc_info=e)
      return (0, 'genius')

def _allow_analysis(printer, settings):
  """Returns true if we can analayze files currently, assuming that we are
  printing.

  This is run frequently so it shouldn't be too CPU intensive.

  Returns true if allowAnalysisWhilePrinting is set.

  Also returns true if allowAnalysisWhileHeating is set and there is a heater
  that hasn't yet reached at least 5 degrees fewer than the target temperature.
  Also, if none of the heaters have a target temperature more than 30C, allow
  analysis.
  """
  if settings.get(["allowAnalysisWhilePrinting"]):
    return True # Always allowed
  if not settings.get(['allowAnalysisWhileHeating']):
    # We don't allow while heating so no need to test all the temps below.
    return False
  if not printer._temps:
    return True # We'll allow it if there are no temps yet.
  all_temps = list(printer._temps)
  if not all_temps:
    return True # We'll allow it if there are no temps yet.
  current_temp = all_temps[-1] # They are sorted so this is the most recent.
  elements_being_heated = 0
  for thermostat in current_temp.values():
    if not isinstance(thermostat, collections.Mapping) or not 'actual' in thermostat or not 'target' in thermostat or thermostat['target'] is None:
      continue
    if thermostat['target'] < 30:
      # This element is targeted for less than room temperature so ignore it.
      continue
    elements_being_heated += 1
    if thermostat['actual'] < thermostat['target'] - 5:
      # At least one element isn't hot enough yet so we can keep analyzing.
      return True
  if not elements_being_heated:
    return True # If not heaters are on, we're not printing anyway.
  return False # All elements are hot enough to print.

class GeniusAnalysisQueue(GcodeAnalysisQueue):
  """Generate an analysis to use for printing time remaining later."""
  def __init__(self, finished_callback, plugin):
    super(GeniusAnalysisQueue, self).__init__(finished_callback)
    self._plugin = plugin

  def _do_abort(self, reenqueue=True):
    super(GeniusAnalysisQueue, self)._do_abort(reenqueue)
    if _allow_analysis(self._plugin._printer, self._plugin._settings):
      self._plugin._logger.info("Abort requested but will be ignored due to settings.")

  def compensate_analysis(self, analysis):
    logger = self._plugin._logger
    """Compensate for the analyzed print time by looking at previous statistics of
    how long it took to heat up or cool down.
    Modifies the analysis in place.
    """
    try:
      print_history = None
      print_history_path = os.path.join(self._plugin.get_plugin_data_folder(),
                                        "print_history.yaml")
      try:
        with open(print_history_path, "r") as print_history_stream:
          data = yaml.safe_load(print_history_stream)
          print_history = data["print_history"]
      except IOError as e:
        if e.errno != errno.ENOENT:
          raise
      if not print_history:
        return
      print_history = [ph for ph in print_history
                       if (all(x in ph for x in ("firstFilamentPrintTime",
                                                 "lastFilamentPrintTime",
                                                 "payload",
                                                 "analysisLastFilamentPrintTime",
                                                 "analysisFirstFilamentPrintTime")) and
                            "time" in ph["payload"])]
      if not print_history:
        return
      # How long did it take to heat up on previous prints?
      logging.info("Gathering compensation data...")
      heat_up_times = [ph["firstFilamentPrintTime"]
                       for ph in print_history]
      logger.info("Recent heat-up times in seconds: {}".format(", ".join(map(str, heat_up_times))))
      average_heat_up_time = sum(heat_up_times) / len(heat_up_times)
      logger.info("Average heat-up: {} seconds".format(average_heat_up_time))
      if self._plugin._settings.get(["compensationValues", "heating"]) is not None:
        logger.info("Forced heating value {} so we'll use that instead.".format(self._plugin._settings.get(["compensationValues", "heating"])))
        average_heat_up_time = self._plugin._settings.get(["compensationValues", "heating"])
      # How long did it take to cool down on previous prints?
      cool_down_times = [ph["payload"]["time"] - ph["lastFilamentPrintTime"]
                         for ph in print_history]
      logger.info("Recent cool-down times in seconds: {}".format(", ".join(map(str, cool_down_times))))
      average_cool_down_time = sum(cool_down_times) / len(cool_down_times)
      logger.info("Average cool-down: {} seconds".format(average_cool_down_time))
      if self._plugin._settings.get(["compensationValues", "cooling"]) is not None:
        logger.info("Forced cooling value {} so we'll use that instead.".format(self._plugin._settings.get(["compensationValues", "cooling"])))
        average_cool_down_time = self._plugin._settings.get(["compensationValues", "cooling"])
      # Factor from the time actual time spent extruding to the predicted.
      logger.info("Time spent printing, actual vs predicted: {}".format(
          ", ".join("{}/{}".format(ph["lastFilamentPrintTime"] - ph["firstFilamentPrintTime"],
                                   ph["analysisLastFilamentPrintTime"] - ph["analysisFirstFilamentPrintTime"])
                    for ph in print_history)))
      print_time_numerator = [(ph["lastFilamentPrintTime"] - ph["firstFilamentPrintTime"])
                              for ph in print_history]
      print_time_denominator = [(ph["analysisLastFilamentPrintTime"] - ph["analysisFirstFilamentPrintTime"])
                               for ph in print_history]
      average_print_time_factor = sum(print_time_numerator) / sum(print_time_denominator)
      logger.info("Average scaling factor: {}".format(average_print_time_factor))
      if self._plugin._settings.get(["compensationValues", "extruding"]) is not None:
        logger.info("Forced extruding factor {} so we'll use that instead.".format(self._plugin._settings.get(["compensationValues", "extruding"])))
        average_print_time_factor = self._plugin._settings.get(["compensationValues", "extruding"])
      # Now make a new progress map.
      new_progress = []
      last_filament_remaining_time = _interpolate_list(analysis["progress"],
                                                  analysis["lastFilament"])[1]
      for p in analysis["progress"]:
        if p[0] < analysis["firstFilament"]:
          continue # Ignore anything before the first filament.
        if p[0] > analysis["lastFilament"]:
          break # Don't add estimates from the cooldown
        remaining_time = p[1] # Starting value.
        remaining_time -= last_filament_remaining_time # Remove expected cooldown.
        remaining_time *= average_print_time_factor # Compensate for scale.
        remaining_time += average_cool_down_time # Add in average cooldown
        new_progress.append([p[0], remaining_time])
      new_progress.insert(0, [0, new_progress[0][1] + average_heat_up_time])
      new_progress.append([1,0])
      analysis["progress"] = new_progress
      analysis["estimatedPrintTime"] = new_progress[0][1]
    except Exception as e:
      logger.warning("Failed to compensate", exc_info=e)

  def _do_analysis(self, high_priority=False):
    self._aborted = False
    logger = self._plugin._logger
    results = {'analysisPending': True}
    self._finished_callback(self._current, results)
    if self._plugin._settings.get(["enableOctoPrintAnalyzer"]):
      logger.info("Running built-in analysis.")
      try:
        results.update(super(GeniusAnalysisQueue, self)._do_analysis(high_priority))
      except AnalysisAborted as e:
        logger.info("Probably starting printing, aborting built-in analysis.")
        raise # Reraise it
      logger.info("Result: {}".format(results))
      self._finished_callback(self._current, results)
    else:
      logger.info("Not running built-in analysis.")
    for analyzer in self._plugin._settings.get(["analyzers"]):
      command = analyzer["command"].format(gcode=self._current.absolute_path, mcodes=self._plugin.get_printer_config())
      if not analyzer["enabled"]:
        logger.info("Disabled: {}".format(command))
        continue
      logger.info("Running: {}".format(command))
      results_err = ""
      try:
        if parse_version(sarge.__version__) >= parse_version('0.1.5'):
          # Because in version 0.1.5 the name was changed in sarge.
          async_kwarg = 'async_'
        else:
          async_kwarg = 'async'
        sarge_job = sarge.capture_both(command, **{async_kwarg: True})
        # Wait for sarge to begin
        while not sarge_job.processes or not sarge_job.processes[0]:
          time.sleep(0.5)
        try:
          process = psutil.Process(sarge_job.processes[0].pid)
          for p in [process] + process.children(recursive=True):
            try:
              if "IDLE_PRIORITY_CLASS" in dir(psutil):
                p.nice(psutil.IDLE_PRIORITY_CLASS)
              else:
                p.nice(19)
            except psutil.NoSuchProcess:
              pass
        except psutil.NoSuchProcess:
          pass
        while sarge_job.commands[0].poll() is None:
          if self._aborted and not _allow_analysis(self._plugin._printer, self._plugin._settings):
            for p in process.children(recursive=True) + [process]:
              p.terminate()
            sarge_job.close()
            raise AnalysisAborted(reenqueue=self._reenqueue)
          time.sleep(0.5)
        sarge_job.close()
        results_text = sarge_job.stdout.text
        results_err = sarge_job.stderr.text
        if sarge_job.returncode != 0:
          raise Exception(results_err)
        logger.info("Sarge output: {}".format(results_err))
        logger.info("Result: {}".format(results_text))
        new_results = json.loads(results_text)
        bedZ = self._plugin._settings.get(["bedZ"])
        if ("printingArea" in new_results and
            "minZ" in new_results["printingArea"] and
            bedZ is not None):
          old_minZ = new_results["printingArea"]["minZ"]
          new_minZ = min(bedZ, old_minZ)
          if old_minZ != new_minZ:
            logger.info("Adjusting minZ ({}) to match bedZ ({})".format(old_minZ, bedZ))
            new_results["printingArea"]["minZ"] = new_minZ
            if ("dimensions" in new_results and
                "height" in new_results["dimensions"]):
              new_results["dimensions"]["height"] += old_minZ - new_minZ
        results.update(new_results)
        logger.info("Merged result: {}".format(results))
        self._finished_callback(self._current, results)
      except AnalysisAborted as e:
        logger.info("Probably started printing, aborting: '{}'".format(command))
        raise # Reraise it
      except Exception as e:
        logger.warning("Failed to run '{}'".format(command), exc_info=e)
      finally:
        if sarge_job:
          sarge_job.close()
    # Before we potentially modify the result from analysis, save them.
    results.update({'analysisPending': False})
    try:
      if not all(x in results
                 for x in ["progress",
                           "firstFilament",
                           "lastFilament"]):
        return results
      results["analysisPrintTime"] = results["estimatedPrintTime"]
      results["analysisFirstFilamentPrintTime"] = (
          results["analysisPrintTime"] - _interpolate_list(
              results["progress"],
              results["firstFilament"])[1])
      results["analysisLastFilamentPrintTime"] = (
          results["analysisPrintTime"] - _interpolate_list(
              results["progress"],
              results["lastFilament"])[1])
      self.compensate_analysis(results) # Adjust based on history
      logger.info("Compensated result: {}".format(results))
    except Exception as e:
      logger.warning("Failed to compensate", exc_info=e)
    results["compensatedPrintTime"] = results["estimatedPrintTime"]
    if self._plugin._printer._estimator and isinstance(self._plugin._printer._estimator, GeniusEstimator):
      self._plugin._printer._estimator.recheck_metadata = True
    return results

def do_later(seconds):
  """Do the decorated function only if it's been at least seconds since the last
     call.  If less than seconds elapse before another call to the decorated
     function, restart the timer.  This means that if there is a string of calls
     to the decorated function such that each call is less than 5 seconds apart,
     only the last one will happen."""
  def new_decorator(f, *args, **kwargs):
    def to_do_later(*args, **kwargs):
      if to_do_later.__timer is not None:
        to_do_later.__timer.cancel()
      to_do_later.__timer = Timer(seconds, f, args, kwargs)
      to_do_later.__timer.start()
    to_do_later.__timer = None
    return to_do_later
  return new_decorator

class PrintTimeGeniusPlugin(octoprint.plugin.SettingsPlugin,
                            octoprint.plugin.AssetPlugin,
                            octoprint.plugin.TemplatePlugin,
                            octoprint.plugin.StartupPlugin,
                            octoprint.plugin.ShutdownPlugin,
                            octoprint.plugin.EventHandlerPlugin,
                            octoprint.plugin.BlueprintPlugin):
  def __init__(self):
    self._logger = logging.getLogger(__name__)
    self._current_history = {}
    dd = lambda: defaultdict(dd)
    self._current_config = PrinterConfig() # dict of timing-relevant config commands
    self._old_printer_config = self._current_config.as_list() # Cache of the config that is on disk.

  ##~~ SettingsPlugin mixin
  def get_settings_defaults(self):
    current_path = os.path.dirname(os.path.realpath(__file__))
    built_in_analyzers = [
        (gettext("All gcode analyzers (usually not as good as marlin-calc)"),
         '"{{python}}" "{analyzer}" "{{{{gcode}}}}"'.format(
             analyzer=os.path.join(current_path, "analyzers/analyze_gcode_comments.py")),
         False),
        (gettext("Marlin firmware simulation (replaces Octoprint built-in, faster and more accurate)"),
         '"{{python}}" "{analyzer}" marlin-calc "{{{{gcode}}}}" "{{{{mcodes}}}}"'.format(
             analyzer=os.path.join(current_path, "analyzers/analyze_progress.py")),
         True),
        (gettext("Use Slic3r PE M73 time remaining"),
         '"{{python}}" "{analyzer}" "{{{{gcode}}}}" --parsers slic3r_pe_print_time slic3r_pe_print_time_remaining'.format(
             analyzer=os.path.join(current_path, "analyzers/analyze_gcode_comments.py")),
         False),
    ]
    return {
      "analyzers": [
        {"description": description,
         "command": command.format(python=sys.executable),
         "enabled": enabled}
        for (description, command, enabled) in built_in_analyzers],
      "exactDurations": True,
      "enableOctoPrintAnalyzer": False,
      "allowAnalysisWhilePrinting": False,
      "allowAnalysisWhileHeating": True,
      "showStars": True,
      "bedZ": 0,
      "compensationValues": {"cooling": None, "extruding": 1.0, "heating": None},
    }

  def is_blueprint_csrf_protected(self):
    return True

  @octoprint.plugin.BlueprintPlugin.route("/get_settings_defaults", methods=["GET"])
  def get_settings_defaults_as_string(self):
    return json.dumps(self.get_settings_defaults())

  @octoprint.plugin.BlueprintPlugin.route("/print_history", methods=["POST", "GET"])
  def print_history_request(self):
    print_history_path = os.path.join(self.get_plugin_data_folder(),
                                      "print_history.yaml")
    data = None
    if flask.request.method == "GET":
      try:
        with open(print_history_path, "r") as print_history_stream:
          data = yaml.safe_load(print_history_stream)
      except IOError as e:
        if e.errno != errno.ENOENT:
          raise
      return json.dumps(data)
    elif flask.request.method == "POST":
      try:
        data = json.loads(flask.request.data)
        with open(print_history_path, "w") as print_history_stream:
          yaml.safe_dump(data, print_history_stream)
      except:
        self._logger.exception("Save print_history.yaml failed")
        abort()
      return flask.make_response("", 200)

  ##~~ EventHandlerPlugin API
  def on_event(self, event, payload):
    """Record how long print's actually took when they succeed.

    We want to record how long it took to finish this print so that we can make
    future estimates more accurate using linear regression.
    """
    if event == "PrintDone":
      # Store the details and also the timestamp.
      print_history = []
      print_history_path = os.path.join(self.get_plugin_data_folder(),
                                        "print_history.yaml")
      data = {}
      try:
        with open(print_history_path, "r") as print_history_stream:
          data = yaml.safe_load(print_history_stream) or {}
          print_history = data["print_history"]
      except IOError as e:
        if e.errno != errno.ENOENT:
          raise
      metadata = self._file_manager.get_metadata(payload["origin"], payload["path"])
      if not "analysis" in metadata or not "analysisPrintTime" in metadata["analysis"]:
        return
      self._current_history["payload"] = payload
      self._current_history["timestamp"] = time.time()
      for x in ("analysisPrintTime",
                "analysisFirstFilamentPrintTime",
                "analysisLastFilamentPrintTime",
                "compensatedPrintTime"):
        if x in metadata["analysis"]:
          self._current_history[x] = metadata["analysis"][x]
      print_history.append(self._current_history)
      self._current_history = {}
      print_history.sort(key=lambda x: x["timestamp"], reverse=True)
      MAX_HISTORY_ITEMS = 5
      del print_history[MAX_HISTORY_ITEMS:]
      data['print_history'] = print_history
      data['version'] = self._plugin_version
      try:
        with open(print_history_path, "w") as print_history_stream:
          yaml.safe_dump(data, print_history_stream)
      except:
        self._logger.exception("Save print_history.yaml failed")

  @octoprint.plugin.BlueprintPlugin.route("/analyze/<origin>/<path:path>", methods=["GET"]) # Different spellings
  @octoprint.plugin.BlueprintPlugin.route("/analyse/<origin>/<path:path>", methods=["GET"])
  def analyze_file(self, origin, path):
    """Add a file to the analysis queue."""
    if self._printer.is_printing() and not _allow_analysis(self._printer, self._settings):
      self._file_manager._analysis_queue.pause()
    else:
      self._file_manager._analysis_queue.resume()

    queue_entry = self._file_manager._analysis_queue_entry(origin, path)
    if queue_entry is None:
      return ""
    results = self._file_manager.analyse(origin, path)
    return ""

  def unmark_all_pending(self, dest, all_files):
    for k, v in all_files.items():
      if 'analysis' in v and 'analysisPending' in v['analysis'] and v['analysis']['analysisPending']:
        self._file_manager.set_additional_metadata(dest, v['path'], 'analysis', {'analysisPending': False}, merge=True)
      if 'children' in v:
        self.unmark_all_pending(dest, v['children'])

  ##~~ StartupPlugin API

  def on_startup(self, host, port):
    # setup our custom logger
    from octoprint.logging.handlers import CleaningTimedRotatingFileHandler
    logging_handler = CleaningTimedRotatingFileHandler(self._settings.get_plugin_logfile_path(postfix="engine"), when="D", backupCount=3)
    logging_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging_handler.setLevel(logging.DEBUG)

    self._logger.addHandler(logging_handler)
    self._logger.propagate = False

    self._logger.info("Starting PrintTimeGenius")
    # Unmark all pending analyses.
    all_files = self._file_manager.list_files()
    for dest in all_files.keys():
      self.unmark_all_pending(dest, all_files[dest])

    # TODO: Remove the below after https://github.com/foosel/OctoPrint/pull/2723 is merged.
    self._file_manager.original_add_file = self._file_manager.add_file
    def new_add_file(destination, path, file_object, links=None, allow_overwrite=False, printer_profile=None, analysis=None, display=None):
      return self._file_manager.original_add_file(destination, path, file_object, links, allow_overwrite, printer_profile, None, display)
    self._file_manager.add_file = new_add_file
    # Work around for broken rc2
    if pkg_resources.parse_version(octoprint._version.get_versions()['version']) == pkg_resources.parse_version("1.3.9rc2"):
      self._printer.old_on_comm = self._printer.on_comm_file_selected
      def new_on_comm(self, *args, **kwargs):
        self.old_on_comm(*args, **kwargs)
        self._create_estimator()
      self._printer.on_comm_file_selected = types.MethodType(new_on_comm, self._printer)

    # Get printer_config from printer_config.yaml
    printer_config_path = os.path.join(self.get_plugin_data_folder(),
                                       "printer_config.yaml")
    try:
      with open(printer_config_path, "r") as printer_config_stream:
        data = yaml.safe_load(printer_config_stream)
        for line in data["printer_config"]:
          self._current_config += line
    except IOError as e:
      if e.errno != errno.ENOENT:
        raise
    self._old_printer_config = self._current_config.as_list()

  def save_settings(self):
    self._logger.info("Saving settings to config.yaml")
    try:
      success = self._settings.save() # This might also save settings that we didn't intend to save...
      self._logger.info("Was saving needed? " + str(success))
    except:
      self._logger.exception("Save settings failed")

  ##~~ ShutdownPlugin API

  def on_shutdown(self):
    self._logger.info("Shutting down")
    self.save_settings()

  ##~~ AssetPlugin mixin

  def get_assets(self):
    # Define your plugin's asset files to automatically include in the
    # core UI here.
    return dict(
	js=["js/PrintTimeGenius.js"],
	css=["css/PrintTimeGenius.css"],
	less=["less/PrintTimeGenius.less"]
    )

  ##~~ Gcode Analysis Hook
  def custom_gcode_analysis_queue(self, *args, **kwargs):
    return dict(gcode=lambda finished_callback: GeniusAnalysisQueue(
        finished_callback, self))
  def custom_estimation_factory(self, *args, **kwargs):
    def make_genius_estimator(job_type):
      self._current_history = {}
      return GeniusEstimator(
          job_type, self._printer, self._file_manager, self._logger, self._current_history)
    return make_genius_estimator

  def update_printer_config(self, line):
    """Extract print config from the line."""
    old_config_as_list = self._current_config.as_list()
    self._current_config += line
    new_config_as_list = self._current_config.as_list()
    if new_config_as_list != old_config_as_list:
      # There has been a change that affects the config.
      self.write_printer_config()

  @do_later(5)
  def write_printer_config(self):
    """Write the printer_config out to disk."""
    # Get printer_config from printer_config.yaml
    new_config_as_list = self._current_config.as_list()
    if new_config_as_list != self._old_printer_config:
      self._logger.info("New printer config: {}".format(str(self._current_config)))
      # Set printer_config to printer_config.yaml
      printer_config_path = os.path.join(self.get_plugin_data_folder(),
                                         "printer_config.yaml")
      data = {}
      data['version'] = self._plugin_version
      data['printer_config'] = new_config_as_list
      try:
        with open(printer_config_path, "w") as printer_config_stream:
          yaml.safe_dump(data, printer_config_stream)
          self._old_printer_config = self._current_config.as_list()
      except:
        logger.exception("Save printer_config.yaml failed")

  def get_printer_config(self):
    """Return the latest printer config."""
    return str(self._current_config)

  ##~~ Gcode Hook
  def command_sent_hook(self, comm_instance, phase, cmd, cmd_type, gcode, subcode=None, tags=None, *args, **kwargs):
    if self._printer.is_printing():
      return
    strip_cmd = cmd
    strip_cmd = strip_cmd.strip()
    self.update_printer_config(strip_cmd)
  def line_received_hook(self, comm_instance, line, *args, **kwargs):
    if self._printer.is_printing():
      return line
    strip_line = line
    if strip_line.startswith("echo:"):
      strip_line = strip_line[len("echo:"):]
    strip_line = strip_line.strip()
    if strip_line.find("Invalid extruder") >= 0:
        return line
    if strip_line.startswith("FR:") and strip_line.endswith("%"):
      feed_rate = strip_line[len("FR:"):-1]
      strip_line = "M220 S" + feed_rate
    elif strip_line.startswith("E") and strip_line[2:9] == " Flow: " and strip_line.endswith("%"):
      index = strip_line[1]
      flow = strip_line[9:-1]
      strip_line = "M221 S" + flow + " T" + index
    self.update_printer_config(strip_line)
    return line

  ##~~ Softwareupdate hook

  def get_update_information(self):
    # Define the configuration for your plugin to use with the Software Update
    # Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
    # for details.
    return dict(
	PrintTimeGenius=dict(
	    displayName="Print Time Genius Plugin",
	    displayVersion=self._plugin_version,

	    # version check: github repository
	    type="github_release",
	    user="eyal0",
	    repo="OctoPrint-PrintTimeGenius",
	    current=self._plugin_version,

	    # update method: pip
	    pip="https://github.com/eyal0/OctoPrint-PrintTimeGenius/archive/{target_version}.zip"
	)
    )


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "PrintTimeGenius Plugin"
__plugin_pythoncompat__ = ">=2.7,<4"

def __plugin_load__():
  global __plugin_implementation__
  __plugin_implementation__ = PrintTimeGeniusPlugin()

  global __plugin_hooks__
  __plugin_hooks__ = {
      "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
      "octoprint.filemanager.analysis.factory": __plugin_implementation__.custom_gcode_analysis_queue,
      "octoprint.printer.estimation.factory": __plugin_implementation__.custom_estimation_factory,
      "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.command_sent_hook,
      "octoprint.comm.protocol.gcode.received": __plugin_implementation__.line_received_hook
  }
