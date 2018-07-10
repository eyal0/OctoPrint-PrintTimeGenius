#!/bin/bash

SCRIPT=`realpath $0`
SCRIPTPATH=`dirname $SCRIPT`
pushd "${SCRIPTPATH}"
git submodule update --remote --recursive
popd
pushd "${SCRIPTPATH}/Marlin/Marlin"
make -f Makefile.calc
cp -f "calc" "${SCRIPTPATH}/../octoprint_PrintTimeGenius/marlin-calc"
cp -f "analyze.py" "${SCRIPTPATH}/../octoprint_PrintTimeGenius/analyze_marlin.py"
popd
