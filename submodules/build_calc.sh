#!/bin/bash

SCRIPT=`realpath $0`
SCRIPTPATH=`dirname $SCRIPT`
pushd "${SCRIPTPATH}"
git submodule update --remote --recursive
popd
pushd "${SCRIPTPATH}/Marlin/Marlin"
scons -j 10
cp -f */marlin-calc.* "${SCRIPTPATH}/../octoprint_PrintTimeGenius/analyzers"
popd
