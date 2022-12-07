#!/usr/bin/env bash

if [[ $(ps -ef | awk '/[m]aestroserver/{print $2}') ]] ; then
    ps -ef | awk '/[m]aestroserver/{print $2}' | xargs kill 
fi

rm -rf $HOME/cloudsend