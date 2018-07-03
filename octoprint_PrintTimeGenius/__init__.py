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

class GCodeAnalyserGenius(PrintTimeEstimator):
  """Uses previous generated analysis to estimate print time remaining."""

  def __init__(self, job_type, printer, file_manager, logger):
    super(GCodeAnalyserGenius, self).__init__(job_type)
    #print(printer.get_current_job())
    self._path = printer.get_current_job()["file"]["path"]
    self._origin = printer.get_current_job()["file"]["origin"]
    self._file_manager = file_manager
    self._logger = logger
    self._first_progress = None # Actual [progress, printTime] that is measured

  def _interpolate(self, l, point):
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

  def _genius_estimate(self, progress, printTime, cleanedPrintTime, statisticalTotalPrintTime, statisticalTotalPrintTimeType):
    """Return an estimate for the total print time remaining."""
    # The progress is a sorted list of pairs [filepos, progress].
    # It maps from filepos to actual printing progress.
    # filepos is between 0 and 1, same as progress.
    # actual progress is in seconds
    metadata = self._file_manager.get_metadata(self._origin, self._path)
    if not metadata:
      return None
    if not "analysis" in metadata or not "progress" in metadata["analysis"]:
      return None
    filepos_to_progress = metadata["analysis"]["progress"]
    if progress < filepos_to_progress[0][0]:
      return None # We're not yet in range so we have no genius estimate yet.
    if not self._first_progress:
      self._first_progress = [progress, printTime]
      self._first_interpolated = self._interpolate(filepos_to_progress, progress)
    interpolated = self._interpolate(filepos_to_progress, progress)
    if not interpolated:
      return None # We're out of range.
    if interpolated[1] == self._first_interpolated[1]:
      return None # To prevent dividing by zero.
    # This is how much time we predicted would.
    predicted_printed = (interpolated[1] - self._first_interpolated[1])
    # This is how much time we predict will pass from _first in total
    predicted_total = filepos_to_progress[-1][1]
    # This is how much time we actually spent.
    actual_printed = printTime - self._first_progress[1]
    actual_total = actual_printed * predicted_total / predicted_printed
    # Add in the time since the start.
    actual_total += self._first_progress[1]
    remaining_print_time = actual_total - printTime
    return remaining_print_time, "genius"

  def estimate(self, progress, printTime, cleanedPrintTime, statisticalTotalPrintTime, statisticalTotalPrintTimeType):
    default_result = super(GCodeAnalyserGenius, self).estimate(
        progress, printTime, cleanedPrintTime,
        statisticalTotalPrintTime, statisticalTotalPrintTimeType)
    result = default_result
    genius_result = result # If genius fails, just use the original result for printing below.
    try:
      new_result = self._genius_estimate(
          progress, printTime, cleanedPrintTime,
          statisticalTotalPrintTime, statisticalTotalPrintTimeType)
      if new_result: # If we succeed.
        genius_result = new_result
        result = new_result
    except Exception as e:
      self._logger.warning("Failed to estimate, ignoring.", exc_info=e)
    self._logger.debug(", ".join(map(str, [printTime, default_result[0], default_result[1], genius_result[0], genius_result[1], progress])))
    return result

class GCodeAnalyserAnalysisQueue(GcodeAnalysisQueue):
  """Generate an analysis to use for printing time remaining later."""
  def __init__(self, finished_callback, plugin):
    super(GCodeAnalyserAnalysisQueue, self).__init__(finished_callback)
    self._plugin = plugin

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
    return results

class PrintTimeGeniusPlugin(octoprint.plugin.SettingsPlugin,
                               octoprint.plugin.AssetPlugin,
                               octoprint.plugin.TemplatePlugin,
                               octoprint.plugin.StartupPlugin):
  def __init__(self):
    self._logger = logging.getLogger(__name__)
  ##~~ SettingsPlugin mixin

  def get_settings_defaults(self):
    return dict(
        analyzers=[],
        exactDurations=True,
        enableOctoPrintAnalyzer=True
    )

  ##~~ StartupPlugin API

  def on_startup(self, host, port):
    # setup our custom logger
    logging_handler = logging.handlers.RotatingFileHandler(self._settings.get_plugin_logfile_path(postfix="engine"), maxBytes=2*1024*1024)
    logging_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging_handler.setLevel(logging.DEBUG)

    self._logger.addHandler(logging_handler)
    #self._logger.setLevel(logging.DEBUG if self._settings.get_boolean(["debug_logging"]) else logging.CRITICAL)
    self._logger.setLevel(logging.DEBUG)
    self._logger.propagate = False


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
    return lambda job_type: GCodeAnalyserGenius(
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
