/*
 * View model for OctoPrint-PrintTimeGenius
 *
 * Author: Eyal
 * License: AGPLv3
 */
$(function() {
  function PrintTimeGeniusViewModel(parameters) {
    var self = this;

    self.settingsViewModel = parameters[0];
    self.printerStateViewModel = parameters[1];

    // Overwrite the printTimeLeftOriginString function
    ko.extenders.addGenius = function(target, option) {
      let result = ko.pureComputed(function () {
        let value = self.printerStateViewModel.printTimeLeftOrigin();
        switch (value) {
          case "genius": {
            return option;
          }
          default: {
            return target();
          }
        }
      })
      return result;
    };
    self.printerStateViewModel.printTimeLeftOriginString =
        self.printerStateViewModel.printTimeLeftOriginString.extend({
          addGenius: gettext("Based on a line-by-line preprocessing of the gcode (excellent accuracy)")});

    // Overwrite the printTimeLeftOriginClass function
    self.originalPrintTimeLeftOriginClass = self.printerStateViewModel.printTimeLeftOriginClass;
    self.printerStateViewModel.printTimeLeftOriginClass = ko.pureComputed(function() {
      let value = self.printerStateViewModel.printTimeLeftOrigin();
      switch (value) {
        case "genius": {
          return "print-time-genius";
        }
        default: {
          return self.originalPrintTimeLeftOriginClass();
        }
      }
    });
    self.printerStateViewModel.printTimeLeftOrigin.valueHasMutated();


    self.onBeforeBinding = function() {
      let settings = self.settingsViewModel.settings;
      let printTimeGeniusSettings = settings.plugins.PrintTimeGenius;
      self.analyzers = printTimeGeniusSettings.analyzers;
      self.exactDurations = printTimeGeniusSettings.exactDurations;
      self.enableOctoPrintAnalyzer = printTimeGeniusSettings.enableOctoPrintAnalyzer;
      // Overwrite the formatFuzzyPrintTime as needed.
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
    construct: PrintTimeGeniusViewModel,
    // ViewModels your plugin depends on, e.g. loginStateViewModel, settingsViewModel, ...
    dependencies: ["settingsViewModel", "printerStateViewModel"],
    // Elements to bind to, e.g. #settings_plugin_PrintTimeGenius, #tab_plugin_PrintTimeGenius, ...
    elements: [ "#settings_plugin_PrintTimeGenius" ]
  });
});
