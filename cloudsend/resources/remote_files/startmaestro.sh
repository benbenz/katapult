#!/usr/bin/env bash

auto_init="$1"

if [[ $(ps aux | grep "cloudsend.maestroserver" | grep -v 'grep') ]] ; then
    echo "Maestro server already running"
else
    # make sure we kill all maestroserver processes
    #if [[ $(ps -ef | awk '/[s]tartmaestro.sh/{print $2}') ]] ; then
    #    ps -ef | awk '/[s]tartmaestro.sh/{print $2}' | xargs kill
    #fi
    if [[ $(ps -ef | awk '/[m]aestroserver/{print $2}') ]] ; then
        ps -ef | awk '/[m]aestroserver/{print $2}' | xargs kill 
    fi
    echo "Starting maestro server ..."
    cd $HOME/cloudsend
    source $HOME/cloudsend/.venv/maestro/bin/activate
    $HOME/cloudsend/.venv/maestro/bin/python3 -u -m cloudsend.maestroserver $auto_init
fi