#!/usr/bin/env bash

if [[ $(ps aux | grep "cloudsend.maestroserver" | grep -v 'grep') ]] ; then
    echo "CloudSend server already running"
else
    # make sure we kill all maestroserver processes
    #if [[ $(ps -ef | awk '/[s]tartmaestro.sh/{print $2}') ]] ; then
    #    ps -ef | awk '/[s]tartmaestro.sh/{print $2}' | xargs kill
    #fi
    if [[ $(ps -ef | awk '/[m]aestroserver/{print $2}') ]] ; then
        ps -ef | awk '/[m]aestroserver/{print $2}' | xargs kill 
    fi
    echo "Starting CloudSend server ..."
    #cd $HOME/cloudsend
    #source ./.venv/maestro/bin/activate
    python3 -u -m cloudsend.maestroserver
fi