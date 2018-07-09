# coding=utf-8
from __future__ import absolute_import
from __future__ import division

### (Don't forget to remove me)
# This is a basic skeleton for your plugin's __init__.py. You probably want to adjust the class name of your plugin
# as well as the plugin mixins it's subclassing from. This is really just a basic skeleton to get you started,
# defining your plugin as a template plugin, settings and asset plugin. Feel free to add or remove mixins
# as necessary.
#
# Take a look at the documentation on what other plugin mixins are available.

import octoprint.plugin
import octoprint.filemanager.storage
from octoprint.printer.estimation import PrintTimeEstimator
from octoprint.filemanager.analysis import GcodeAnalysisQueue
import logging
import bisect
import subprocess
import json
import shlex
import time
from scipy import stats
import math

def _interpolate(l, point):
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
  # ratio 0 means use the left_index one, 1 means the right_index one
  ratio = (point - l[left_index][0])/(l[right_index][0] - l[left_index][0])
  return [x[0]*(1-ratio) + x[1]*ratio
          for x in zip(l[left_index], l[right_index])]

class GeniusEstimator(PrintTimeEstimator):
  """Uses previous generated analysis to estimate print time remaining."""

  def __init__(self, job_type, printer, file_manager, logger):
    super(GeniusEstimator, self).__init__(job_type)
    self._path = printer.get_current_job()["file"]["path"]
    self._origin = printer.get_current_job()["file"]["origin"]
    self._file_manager = file_manager
    self._logger = logger
    self._current_progress_index = -1 # Points to the entry that we used for remaining time
    self._current_total_printTime = None # When we started using the current_progress

  def _genius_estimate(self, progress, printTime, cleanedPrintTime, statisticalTotalPrintTime, statisticalTotalPrintTimeType):
    """Return an estimate for the total print time remaining."""
    # The progress is a sorted list of pairs [filepos, remaining_time].
    # It maps from filepos to estimated remaining time.
    # filepos is between 0 and 1, same as progress.
    # actual progress is in seconds
    metadata = self._file_manager.get_metadata(self._origin, self._path)
    if not metadata:
      return None
    if not "analysis" in metadata or not "progress" in metadata["analysis"]:
      return None
    filepos_to_progress = metadata["analysis"]["progress"]
    # Can we increment the current_progress_index?
    new_progress_index = self._current_progress_index
    while (new_progress_index + 1 < len(filepos_to_progress) and
           progress >= filepos_to_progress[new_progress_index+1][0]):
      new_progress_index += 1 # Increment
    if new_progress_index < 0:
      return None # We're not even in range yet.
    if new_progress_index != self._current_progress_index:
      # We advanced to a new index, let's use the new estimate.
      self._current_progress_index = new_progress_index
      # This is our best guess for the total print time.
      self._current_total_printTime = _interpolate(filepos_to_progress, progress)[1] + printTime
    remaining_print_time = self._current_total_printTime - printTime
    return remaining_print_time, "genius"

  def estimate(self, progress, printTime, cleanedPrintTime, statisticalTotalPrintTime, statisticalTotalPrintTimeType):
    default_result = super(GeniusEstimator, self).estimate(
        progress, printTime, cleanedPrintTime,
        statisticalTotalPrintTime, statisticalTotalPrintTimeType)
    result = default_result
    try:
      genius_result = self._genius_estimate(
          progress, printTime, cleanedPrintTime,
          statisticalTotalPrintTime, statisticalTotalPrintTimeType)
      if genius_result and statisticalTotalPrintTimeType != "average": # If we succeed.
        result = genius_result
    except Exception as e:
      self._logger.warning("Failed to estimate, ignoring.", exc_info=e)
    self._logger.debug(", ".join(map(str, [printTime, default_result[0], default_result[1], result[0], result[1], progress])))
    return result

class GCodeAnalyserAnalysisQueue(GcodeAnalysisQueue):
  """Generate an analysis to use for printing time remaining later."""
  def __init__(self, finished_callback, plugin):
    super(GCodeAnalyserAnalysisQueue, self).__init__(finished_callback)
    self._plugin = plugin

  def _compensate_print_time(self, estimate, estimate_to_actual):
    """Find the actual based on the estimate and the history.

    Given an estimate and a list of (estimate, actual) pairs, use a linear
    regression on the pairs to find the actual corresponding to the estimate.
    """
    try:
      if len(estimate_to_actual) < 1:
        return estimate
      if len(estimate_to_actual) < 2:
        # Let's just assume scaling only
        estimate_to_actual.append((0, 0))
      slope, intercept, r_value, p_value, std_err = stats.linregress([e for (e, a) in estimate_to_actual],
                                                                     [a for (e, a) in estimate_to_actual])
      new_estimate = estimate * slope + intercept
      if math.isnan(new_estimate):
        return estimate
      self._plugin._logger.debug("Slope: {}, Intercept: {}, r_value: {}, p_value: {}, std_err: {}".format(
                                 slope, intercept, r_value, p_value, std_err))
      self._plugin._logger.info("Compensating print time, from {} to {}.".format(estimate, new_estimate))
      return new_estimate
    except:
      return estimate

  def _do_analysis(self, high_priority=False):
    logger = self._plugin._logger
    results = None
    if self._plugin._settings.get(["enableOctoPrintAnalyzer"]):
      logger.info("Running built-in analysis.")
      results = super(GCodeAnalyserAnalysisQueue, self)._do_analysis(high_priority)
      logger.info("Result: {}".format(results))
      self._finished_callback(self._current, results)
    else:
      logger.info("Not running built-in analysis.")
    for analyzer in self._plugin._settings.get(["analyzers"]):
      command = analyzer["command"].format(gcode=self._current.absolute_path)
      if not analyzer["enabled"]:
        logger.info("Disabled: {}".format(command))
        continue
      logger.info("Running: {}".format(command))
      try:
        results_text = subprocess.check_output(shlex.split(command))
        new_results = json.loads(results_text)
        logger.info("Result: {}".format(new_results))
        results.update(new_results)
        logger.info("Merged result: {}".format(results))
        self._finished_callback(self._current, results)
      except Exception as e:
        logger.warning("Failed to run '{}'".format(command), exc_info=e)
    if "estimatedPrintTime" in results:
      # Before we potentially modify the result from analysis, save it.
      results["analysisPrintTime"] = results["estimatedPrintTime"]
      # Possibly adjust the estimatedPrintTime using print_history.
      results["estimatedPrintTime"] = self._compensate_print_time(
          results["estimatedPrintTime"],
          [(print_history_entry["analysisPrintTime"], print_history_entry["payload"]["time"])
           for print_history_entry in self._plugin._settings.get(["print_history"])
           if ("analysisPrintTime" in print_history_entry and
               "payload" in print_history_entry and
               "time" in print_history_entry["payload"])])
    return results

class PrintTimeGeniusPlugin(octoprint.plugin.SettingsPlugin,
                            octoprint.plugin.AssetPlugin,
                            octoprint.plugin.TemplatePlugin,
                            octoprint.plugin.StartupPlugin,
                            octoprint.plugin.EventHandlerPlugin):
  def __init__(self):
    self._logger = logging.getLogger(__name__)
  ##~~ SettingsPlugin mixin

  def get_settings_defaults(self):
    return dict(
        analyzers=[],
        exactDurations=True,
        enableOctoPrintAnalyzer=True,
        print_history=[],
    )

  ##~~ StartupPlugin API

  def on_startup(self, host, port):
    # setup our custom logger
    logging_handler = logging.handlers.RotatingFileHandler(self._settings.get_plugin_logfile_path(postfix="engine"), maxBytes=2*1024*1024)
    logging_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging_handler.setLevel(logging.DEBUG)

    self._logger.addHandler(logging_handler)
    self._logger.propagate = False

  ##~~ EventHandlerPlugin API
  def on_event(self, event, payload):
    """Record how long print's actually took when they succeed.

    We want to record how long it took to finish this print so that we can make
    future estimates more accurate using linear regression.
    """
    if event == "PrintDone":
      # Store the details and also the timestamp.
      if not self._settings.has(["print_history"]):
        print_history = []
      else:
        print_history = self._settings.get(["print_history"])
      metadata = self._file_manager.get_metadata(payload["origin"], payload["path"])
      if not "analysis" in metadata or not "analysisPrintTime" in metadata["analysis"]:
        return
      analysis_print_time = metadata["analysis"]["analysisPrintTime"]
      print_history.append({
          "payload": payload, # This includes the time, which is the actualPrintTime
          "timestamp": time.time(),
          "analysisPrintTime": analysis_print_time
      })
      print_history.sort(key=lambda x: x["timestamp"], reverse=True)
      MAX_HISTORY_ITEMS = 5
      del print_history[MAX_HISTORY_ITEMS:]
      self._settings.set(["print_history"], print_history)
      self._settings.save() # This might also save settings that we didn't intend to save...

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
    return dict(gcode=lambda finished_callback: GCodeAnalyserAnalysisQueue(
        finished_callback, self))
  def custom_estimation_factory(self, *args, **kwargs):
    return lambda job_type: GeniusEstimator(
        job_type, self._printer, self._file_manager, self._logger)

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

def __plugin_load__():
  global __plugin_implementation__
  __plugin_implementation__ = PrintTimeGeniusPlugin()

  global __plugin_hooks__
  __plugin_hooks__ = {
      "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
      "octoprint.filemanager.analysis.factory": __plugin_implementation__.custom_gcode_analysis_queue,
      "octoprint.printer.estimation.factory": __plugin_implementation__.custom_estimation_factory
  }
