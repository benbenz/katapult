#!/usr/bin/env bash

if [[ $(ps aux | grep "cloudrun.maestroserver" | grep -v 'grep') ]] ; then
    echo "Maestro server already running"
else
    echo "Starting maestro server ..."
    cd $HOME/cloudrun
    source $HOME/cloudrun/.venv/maestro/bin/activate
    $HOME/cloudrun/.venv/maestro/bin/python3 -u -m cloudrun.maestroserver
fi