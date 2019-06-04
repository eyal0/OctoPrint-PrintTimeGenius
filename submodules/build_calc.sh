#!/bin/bash

SCRIPT=`realpath $0`
SCRIPTPATH=`dirname $SCRIPT`
pushd "${SCRIPTPATH}"
git submodule update --remote --recursive
popd
pushd "${SCRIPTPATH}/Marlin/Marlin"
scons -i -j 10 || true
cp -f out/*/marlin-calc.* "${SCRIPTPATH}/../octoprint_PrintTimeGenius/analyzers"
popd
