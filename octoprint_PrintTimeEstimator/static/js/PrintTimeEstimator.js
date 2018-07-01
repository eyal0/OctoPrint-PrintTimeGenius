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
    self.printerStateViewModel = parameters[1];

    self.onBeforeBinding = function() {
      self.settings = self.settingsViewModel.settings;
      self.analyzers = self.settings.plugins.PrintTimeEstimator.analyzers;
      self.exactDurations = self.settings.plugins.PrintTimeEstimator.exactDurations;
      self.originalFormatFuzzyPrintTime = formatFuzzyPrintTime;
      formatFuzzyPrintTime = function() {
        if (self.exactDurations()) {
          return formatDuration.apply(null, arguments);
        } else {
          return self.originalFormatFuzzyPrintTime.apply(null, arguments);
        }
      }

      self.exactDurations.subscribe(function (newValue) {
        self.printerStateViewModel.estimatedPrintTime.valueHasMutated();
        self.printerStateViewModel.lastPrintTime.valueHasMutated();
        self.printerStateViewModel.printTimeLeft.valueHasMutated();
      })

    }

    self.addAnalyzer = function() {
      self.analyzers.push({command: "", enabled: true});
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
    dependencies: ["settingsViewModel", "printerStateViewModel"],
    // Elements to bind to, e.g. #settings_plugin_PrintTimeEstimator, #tab_plugin_PrintTimeEstimator, ...
    elements: [ "#settings_plugin_PrintTimeEstimator" ]
  });
});
