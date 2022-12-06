#!/usr/bin/env bash

if [[ $(ps aux | grep "cloudrun.maestroserver" | grep -v 'grep') ]] ; then
    echo "CloudRun server already running"
else
    # make sure we kill all maestroserver processes
    #if [[ $(ps -ef | awk '/[s]tartmaestro.sh/{print $2}') ]] ; then
    #    ps -ef | awk '/[s]tartmaestro.sh/{print $2}' | xargs kill
    #fi
    if [[ $(ps -ef | awk '/[m]aestroserver/{print $2}') ]] ; then
        ps -ef | awk '/[m]aestroserver/{print $2}' | xargs kill 
    fi
    echo "Starting CloudRun server ..."
    #cd $HOME/cloudrun
    #source ./.venv/maestro/bin/activate
    python3 -u -m cloudrun.maestroserver
fi