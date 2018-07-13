---
layout: plugin

id: PrintTimeGenius
title: OctoPrint-PrintTimeGenius
description: Use a gcode pre-analysis to provide better print time estimation
author: Eyal
license: AGPLv3

date: 2018-07-12

homepage: https://github.com/eyal0/OctoPrint-PrintTimeGenius
source: https://github.com/eyal0/OctoPrint-PrintTimeGenius
archive: https://github.com/eyal0/OctoPrint-PrintTimeGenius/archive/master.zip

follow_dependency_links: false

tags:
- helper
- estimator
- estimation
- time
- print time
- analysis

screenshots:
- url: /assets/img/plugins/PrintTimeGenius/precise.png
  alt: Time remaining with a gold star next to it
  caption: The time remaining is shown with seconds and a gold star is visible when Genius is working
- url: /assets/img/plugins/PrintTimeGenius/estimates_vs_actual.png
  alt: alt-text of another screenshot
  caption: caption of another screenshot

featuredimage: /assets/img/plugins/PrintTimeGenius/precise.png

compatibility:
  octoprint:
  - 1.3.9rc1

---

Generate highly accurate gcode printing time estimations using advanced gcode analyzers combined with the printing history.

PrintTimeGenius provides estimates that are accurate to within just minutes, sometimes even seconds!  It can even account for the time to heat up the nozzle/bed.  It uses an algorithm to calculate the print time remaining while running so that even if the original estimate was wrong, it will still converge on the correct one.

PrintTimeGenius uses the estimates embedded in your gcode, put there by slic3r or cura.  It also runs a Marlin or Smoothieware simulation to provide line-by-line accuracy, often accurate within 0.2% of actual print time.
