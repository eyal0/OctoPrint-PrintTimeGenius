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

# TODO
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

Using advanced gcode analyzers and combining it with the printing history, generate highly accurate gcode printing time estimations.

PrintTimeGenius provides estimates that are accurate to within jsut a few minutes, even accounting for the time to heat up the nozzle/bed.  It also has an advanced algorithm to calculate the print time remaining while running so that even if the original estimate was wrong, it will still converge on the correct one.

PrintTimeGenius takes estimates embedded in your gcode, put there by slic3r or cura.  It can also run a Marlin or Smoothieware simulation to provide line-by-line accuracy, often accurate within 0.2% of actual print time.
