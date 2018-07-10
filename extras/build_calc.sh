#!/bin/bash

SCRIPT=`realpath $0`
SCRIPTPATH=`dirname $SCRIPT`
git submodule update --remote --recursive
pushd "${SCRIPTPATH}/Marlin/Marlin"
make -f Makefile.calc
cp -f "calc" "${SCRIPTPATH}/../octoprint_PrintTimeGenius/marlin-calc"
cp -f "analyze.py" "${SCRIPTPATH}/../octoprint_PrintTimeGenius/analyze_marlin.py"
popd
