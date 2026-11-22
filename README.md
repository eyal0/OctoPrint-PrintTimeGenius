# OctoPrint-PrintTimeGenius

[![Crowdin](https://d322cqt584bo4o.cloudfront.net/octoprint-printtimegenius/localized.svg)](https://crowdin.com/project/octoprint-printtimegenius)

**Provide better estimations on print time in OctoPrint.**

In the chart, we see that the print time remaining is never off by more than 3 minutes using the GeniusEstimator, under 3%. The estimator built-in to OctoPrint is off by 19 minutes at worst, which is a 16% error.

![total time graphs in minutes actual vs estimated vs geniusestimator](https://user-images.githubusercontent.com/109809/42283452-28fba0d8-7fb2-11e8-9fde-7e09c844582e.png)

## Setup

Install via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager)
or manually using this URL:

    https://github.com/eyal0/OctoPrint-PrintTimeGenius/archive/master.zip

## Configuration

After first installing, you must run M503 in order to import your printer's configuration:
1. Open OctoPrint
2. Make sure your printer is connected and turned on.
3. Click on the "Terminal" tab in Octoprint to get to the GCode Terminal. 
4. You will see an area under the terminal window where you can enter the Code and click the "Send" button.   
In that text box, type M503 and click send.

Next, you should test that the plugin works by going into settings and analyzing a file.  Then look at the log and make sure that there are no errors.  If you see errors, report them here.

### OctoPrint 2.0 and M73

OctoPrint 2.0 and later show the time remaining from the `M73` commands that many slicers add to the gcode instead of asking PrintTimeGenius.  So that PrintTimeGenius is used, it sets `trustM73` of OctoPrint's Serial Connector to false.  The printer still receives the `M73` commands.  You can turn this off in the settings with "Use PrintTimeGenius instead of M73 time remaining from the slicer".  If you uninstall PrintTimeGenius, remove `trustM73` under `plugins: serial_connector:` in `config.yaml` to restore OctoPrint's default.
