/*
 * View model for OctoPrint-PrintTimeEstimator
 *
 * Author: Eyal
 * License: AGPLv3
 */
$(function() {
  function PrintTimeEstimatorViewModel(parameters) {
    var self = this;

    self.settingsViewModel = parameters[0];

    self.onBeforeBinding = function() {
      self.settings = self.settingsViewModel.settings;
      self.analyzers = self.settings.plugins.PrintTimeEstimator.analyzers;
    }

    self.addAnalyzer = function() {
      self.analyzers.push({command: "", enabled: false});
    }

    self.removeAnalyzer = function(analyzer) {
      self.analyzers.remove(analyzer);
    }
  }

  /* view model class, parameters for constructor, container to bind to
   * Please see http://docs.octoprint.org/en/master/plugins/viewmodels.html#registering-custom-viewmodels for more details
   * and a full list of the available options.
   */
  OCTOPRINT_VIEWMODELS.push({
    construct: PrintTimeEstimatorViewModel,
    // ViewModels your plugin depends on, e.g. loginStateViewModel, settingsViewModel, ...
    dependencies: ["settingsViewModel"],
    // Elements to bind to, e.g. #settings_plugin_PrintTimeEstimator, #tab_plugin_PrintTimeEstimator, ...
    elements: [ "#settings_plugin_PrintTimeEstimator" ]
  });
});
