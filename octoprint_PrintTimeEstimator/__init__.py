# coding=utf-8
from __future__ import absolute_import

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

class GCodeAnalyserEstimator(PrintTimeEstimator):
  """Uses previous generated analysis to estimate print time remaining."""

  def __init__(self, job_type, printer, file_manager):
    super(GCodeAnalyserEstimator, self).__init__(job_type)
    #print(printer.get_current_job())
    path = printer.get_current_job()["file"]["path"]
    origin = printer.get_current_job()["file"]["origin"]
    #file_manager.set_additional_metadata(self.origin, self.path, "foo", "bar")
    #print(file_manager.get_metadata(self.origin, self.path))
    #print(self.path)
    self._logger = logging.getLogger(__name__)

  def estimate(self, progress, printTime, cleanedPrintTime,  statisticalTotalPrintTime, statisticalTotalPrintTimeType):
    # always reports 3h as printTimeLeft
    return 3 * 60 * 60, "GCodeAnalyser"

class GCodeAnalyserAnalysisQueue(GcodeAnalysisQueue):
  """Generate an analysis to use for printing time remaining later."""
  pass

class PrintTimeEstimatorPlugin(octoprint.plugin.SettingsPlugin,
                               octoprint.plugin.AssetPlugin,
                               octoprint.plugin.TemplatePlugin):
  def __init__(self):
    self._logger = logging.getLogger(__name__)
  ##~~ SettingsPlugin mixin

  def get_settings_defaults(self):
    return dict(
      # put your plugin's default settings here
    )

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
    return dict(gcode=GCodeAnalyserAnalysisQueue)
  def custom_estimation_factory(self, *args, **kwargs):
    return lambda job_type: GCodeAnalyserEstimator(
        job_type, self._printer, self._file_manager)

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
