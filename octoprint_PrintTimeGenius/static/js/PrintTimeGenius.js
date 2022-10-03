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
    self.filesViewModel = parameters[2];
    self.selectedGcodes = ko.observable();
    self.print_history = ko.observableArray();
    self.settings_visible = ko.observable(false);
    self.version = undefined;

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
    self.original_processProgressData = self.printerStateViewModel._processProgressData;
    self.printerStateViewModel._processProgressData = function(data) {
      self.original_processProgressData(data);
      if (data.printTimeLeft) {
        self.printerStateViewModel.progress(
            (data.printTime||0) /
              ((data.printTime||0) + (data.printTimeLeft))
              * 100);
      }
    };
    self.printerStateViewModel.printTimeLeftOriginString =
        self.printerStateViewModel.printTimeLeftOriginString.extend({
          addGenius: gettext("Based on a line-by-line preprocessing of the gcode (good accuracy)")});

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

    self.theFiles = function(items) {
      let results = [];
      let queue = [{children: items}];

      while (queue.length > 0) {
        item = queue.shift();
        results.push(...item.children.filter(item => (item["type"] == "machinecode" && item["origin"] == "local")));
        queue.push(...item.children.filter(item => "children" in item));
      }
      return results;
    };

    self.FileList = ko.pureComputed(function() {
        // only compute FileList when settings is visible
        if (!self.settings_visible()) {
            return [];
        }
        return self.theFiles(self.filesViewModel.allItems())
            .sort(function(a,b) {
                if (_.has(a, "gcodeAnalysis.progress") != _.has(b, "gcodeAnalysis.progress")) {
                    return (_.has(a, "gcodeAnalysis.progress") - _.has(b, "gcodeAnalysis.progress"));
                }
                return a.path.localeCompare(b.path);
            });
    });

    self.onSettingsShown = function() {
        self.settings_visible(true);
    };

    self.onSettingsHidden = function() {
        self.settings_visible(false);
    };

    self.analyzeCurrentFile = function () {
      let items = self.selectedGcodes();
      for (let item of items) {
        let gcode = item["origin"] + "/" + item["path"];
        url = OctoPrint.getBlueprintUrl("PrintTimeGenius") + "analyze/" + gcode;
        OctoPrint.get(url)
      }
    }

    self.onBeforeBinding = function() {
      let settings = self.settingsViewModel.settings;
      let printTimeGeniusSettings = settings.plugins.PrintTimeGenius;
      self.analyzers = printTimeGeniusSettings.analyzers;
      self.exactDurations = printTimeGeniusSettings.exactDurations;
      self.showStars = printTimeGeniusSettings.showStars;
      self.enableOctoPrintAnalyzer = printTimeGeniusSettings.enableOctoPrintAnalyzer;
      self.allowAnalysisWhilePrinting = printTimeGeniusSettings.allowAnalysisWhilePrinting;
      self.allowAnalysisWhileHeating = printTimeGeniusSettings.allowAnalysisWhileHeating;
      function observableFloat(x) {
        return ko.computed({
          read: function() {
            return x();
          },
          write: function(value) {
            let floatValue = parseFloat(value);
            if (isNaN(floatValue)) {
              floatValue = null;
            }
            x(floatValue);
          },
          owner: self,
        });
      }
      self.compensationValues = {
        "heating": observableFloat(printTimeGeniusSettings.compensationValues.heating),
        "extruding": observableFloat(printTimeGeniusSettings.compensationValues.extruding),
        "cooling": observableFloat(printTimeGeniusSettings.compensationValues.cooling),
      };
      OctoPrint.get(OctoPrint.getBlueprintUrl("PrintTimeGenius") + "print_history")
        .done(function (print_history) {
          self.version = (print_history && 'version' in print_history && print_history['version']) || 0;
          self.print_history(ko.mapping.fromJS(
            ((print_history && 'print_history' in print_history && print_history['print_history']) || []))());
        });
      self.print_history.subscribe(function (newValue) {
        if (!newValue) {
          return;
        }
        let to_write = {
          'print_history': ko.mapping.toJS(newValue),
          'version': self.version
        };
        OctoPrint.postJson(OctoPrint.getBlueprintUrl("PrintTimeGenius") + "print_history",
                           to_write);
      });
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
      });
      // Force an update because this is called after the format function has already run.
      self.exactDurations.valueHasMutated();

      self.originalGetSuccessClass = self.filesViewModel.getSuccessClass;
      self.filesViewModel.getSuccessClass = function(data) {
        if (!self.showStars()) {
          return self.originalGetSuccessClass(data);
        }
        let additional_css = "";
        if (_.get(data, "gcodeAnalysis.analysisPending", false)) {
          additional_css = " print-time-genius-pending";
        } else if (_.has(data, "gcodeAnalysis.progress")) {
          additional_css = " print-time-genius-after";
        }
        return self.originalGetSuccessClass(data) + additional_css;
      };
      self.showStars.subscribe(function (newValue) {
        self.filesViewModel.requestData({force: true}); // So that the file list is updated with the changes above.
      });
      self.showStars.valueHasMutated();
    }

    self.addAnalyzer = function() {
      self.analyzers.push({command: "", enabled: true});
    }

    self.removeAnalyzer = function(analyzer) {
      self.analyzers.remove(analyzer);
    }
    self.removePrintHistoryRow = function(row) {
      self.print_history.remove(row);
    }
    self.resetAnalyzersToDefault = function() {
      OctoPrint.get(OctoPrint.getBlueprintUrl("PrintTimeGenius") + "get_settings_defaults").done(
          function (defaults) {
            self.analyzers(defaults['analyzers']);
          });
    }
  }

  /* view model class, parameters for constructor, container to bind to
   * Please see http://docs.octoprint.org/en/master/plugins/viewmodels.html#registering-custom-viewmodels for more details
   * and a full list of the available options.
   */
  OCTOPRINT_VIEWMODELS.push({
    construct: PrintTimeGeniusViewModel,
    // ViewModels your plugin depends on, e.g. loginStateViewModel, settingsViewModel, ...
    dependencies: ["settingsViewModel", "printerStateViewModel", "filesViewModel"],
    // Elements to bind to, e.g. #settings_plugin_PrintTimeGenius, #tab_plugin_PrintTimeGenius, ...
    elements: [ "#settings_plugin_PrintTimeGenius" ]
  });
});
