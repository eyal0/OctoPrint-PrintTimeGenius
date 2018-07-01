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

class GCodeAnalyserEstimator(PrintTimeEstimator):
  """Uses previous generated analysis to estimate print time remaining."""

  def __init__(self, job_type, printer, file_manager, logger):
    super(GCodeAnalyserEstimator, self).__init__(job_type)
    #print(printer.get_current_job())
    self._path = printer.get_current_job()["file"]["path"]
    self._origin = printer.get_current_job()["file"]["origin"]
    self._file_manager = file_manager
    self._logger = logger

  def estimate(self, progress, printTime, cleanedPrintTime, statisticalTotalPrintTime, statisticalTotalPrintTimeType):
    result = None
    try:
      # The progress is a sorted list of pairs (filepos, progress).
      # It maps from filepos to actual printing progress.
      # All values are in terms of the final values of filepos and progress.
      #print(self._file_manager)
      #print(self._file_manager.get_metadata(self._origin, self._path))
      filepos_to_progress = self._file_manager.get_metadata(self._origin, self._path)["analysis"]["progress"]
      last_pair = filepos_to_progress[-1]
      max_filepos = last_pair[0] # End of file, end of print
      current_filepos = progress*max_filepos
      ge = bisect.bisect_left(filepos_to_progress, [current_filepos, 0])
      ge_pair = last_pair # End of file, end of print
      if ge != len(filepos_to_progress):
        ge_pair = filepos_to_progress[ge]
      lt = ge - 1
      lt_pair = filepos_to_progress[0] # Start of file, start of print
      if lt:
        lt_pair = filepos_to_progress[lt]
      filepos_range = ge_pair[0] - lt_pair[0]
      # range_ratio 0 means that we're at lt_pair, 1 means that we're at ge_pair
      if filepos_range == 0:
        actual_progress = lt_pair[1]
      else:
        range_ratio = (progress*max_filepos-lt_pair[0]) / filepos_range
        actual_progress = (1-range_ratio)*lt_pair[1] + range_ratio*ge_pair[1]
      actual_progress /= last_pair[1]
      # actual_progress is the percentage of total time, in the range [0,1]
      # Convert it to the actual time remaining
      #print("cleaned is %f" % cleanedPrintTime)
      #print("printTime is %f" % printTime)
      #print("statisticalTotalPrintTime is %f" % statisticalTotalPrintTime)
      #print("actual_progress is %f" % actual_progress)
      print_time_origin = "linear"
      use_estimate = 1

      total_print_time = cleanedPrintTime/actual_progress
      total_print_time += printTime - cleanedPrintTime # Add in the heating time
      remaining_print_time = total_print_time - printTime
      print_time_origin = "estimate"
      #print("assuming total print time is: %f" % total_print_time)
      if cleanedPrintTime < 30 and actual_progress < 0.01:
        # We're just starting, maybe heating, so we'll just report use the total print time
        use_estimate = max(cleanedPrintTime/30, actual_progress/0.01)
        remaining_print_time = (use_estimate*remaining_print_time +
                                (1-use_estimate)*(statisticalTotalPrintTime - printTime))
        print_time_origin = "linear"
      result = remaining_print_time, print_time_origin
    except Exception as e:
      result = super(GCodeAnalyserEstimator, self).estimate(
          progress, printTime, cleanedPrintTime,
          statisticalTotalPrintTime, statisticalTotalPrintTimeType)
    self._logger.debug("{}, {}, {}".format(printTime, cleanedPrintTime, result[0]))
    return result

class GCodeAnalyserAnalysisQueue(GcodeAnalysisQueue):
  """Generate an analysis to use for printing time remaining later."""
  def __init__(self, finished_callback, plugin):
    super(GCodeAnalyserAnalysisQueue, self).__init__(finished_callback)
    self._plugin = plugin

  def _do_analysis(self, high_priority=False):
    logger = self._plugin._logger
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

class PrintTimeEstimatorPlugin(octoprint.plugin.SettingsPlugin,
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
	js=["js/PrintTimeEstimator.js"],
	css=["css/PrintTimeEstimator.css"],
	less=["less/PrintTimeEstimator.less"]
    )

  ##~~ Gcode Analysis Hook
  def custom_gcode_analysis_queue(self, *args, **kwargs):
    return dict(gcode=lambda finished_callback: GCodeAnalyserAnalysisQueue(
        finished_callback, self))
  def custom_estimation_factory(self, *args, **kwargs):
    return lambda job_type: GCodeAnalyserEstimator(
        job_type, self._printer, self._file_manager, self._logger)

  ##~~ Softwareupdate hook

  def get_update_information(self):
    # Define the configuration for your plugin to use with the Software Update
    # Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
    # for details.
    return dict(
	PrintTimeEstimator=dict(
	    displayName="Printtimeestimator Plugin",
	    displayVersion=self._plugin_version,

	    # version check: github repository
	    type="github_release",
	    user="eyal0",
	    repo="OctoPrint-PrintTimeEstimator",
	    current=self._plugin_version,

	    # update method: pip
	    pip="https://github.com/eyal0/OctoPrint-PrintTimeEstimator/archive/{target_version}.zip"
	)
    )


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "PrintTimeEstimator Plugin"

def __plugin_load__():
  global __plugin_implementation__
  __plugin_implementation__ = PrintTimeEstimatorPlugin()

  global __plugin_hooks__
  __plugin_hooks__ = {
      "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
      "octoprint.filemanager.analysis.factory": __plugin_implementation__.custom_gcode_analysis_queue,
      "octoprint.printer.estimation.factory": __plugin_implementation__.custom_estimation_factory
  }
