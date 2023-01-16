#!/usr/bin/bash

auto_init="$1"

if [[ $(ps aux | grep "katapult.maestroserver" | grep -v 'grep') ]] ; then
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
    cd $HOME/katapult
    source $HOME/katapult/.venv/maestro/bin/activate
    $HOME/katapult/.venv/maestro/bin/python3 -u -m katapult.maestroserver $auto_init
fi