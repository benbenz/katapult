#!/usr/bin/bash

if [[ $(ps -ef | awk '/[b]ootstrap/{print $2}') ]] ; then
    ps -ef | awk '/[b]ootstrap/{print $2}' | xargs kill 
fi

if [[ $(ps -ef | awk '/[b]atch_run/{print $2}') ]] ; then
    ps -ef | awk '/[b]atch_run/{print $2}' | xargs kill 
fi

if [[ $(ps -ef | awk '/[r]un.sh/{print $2}') ]] ; then
    ps -ef | awk '/[r]un.sh/{print $2}' | xargs kill 
fi

if [[ $(ps -ef | awk '/[m]icrorun.sh/{print $2}') ]] ; then
    ps -ef | awk '/[m]icrorun.sh/{print $2}' | xargs kill 
fi

rm -rf $HOME/run

rm -rf $HOME/micromamba
