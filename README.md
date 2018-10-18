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

After first installing, you should test that it works by going into settings and analyzing a file.  Then look at the log and make sure that there are no errors.  If you see errors, report them here.
