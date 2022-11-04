#!/usr/bin/bash

if (( $# < 4 )); then
    echo "$0 ENV_NAME UID PID RUN_HASH OUT_FILE"
    exit 0
else
    env_name="$1"; shift
    uid=$1; shift
    pid=$1; shift
    run_hash="$1"; shift
    out_file="$1"; shift
fi

cd "$HOME/run/$env_name/$run_hash"

# this is running (by PID)
if ! [[ pid -eq 0 ]]; then
    if ps -p $pid | tail +2; then
        echo "running"
        exit
    fi
fi
# this is running (by name / command line)
if ps aux | grep "$env_name/$run_hash" | grep -v 'grep'; then
    echo "running"
    exit
fi
# check if we have a command state file
if [ -f state ]; then
    # it says its running but we didnt find the PID, it's like aborted
    if [[ $(< state) == "running" ]]; then
        echo "aborted"
        exit
    fi
    # if state is done but we dont have the out file, this is probably aborted?
    if [[ $(< state) == "done" ]]; then
        if ! [ -f $out_file ]; then
            echo "aborted_q" # "aborted?" _q for question
            exit
        fi
    fi
    # just display this state
    more state
    exit
fi
# check what is the environment state file
if [ -f ../state ]; then
    if [[ $(< ../state) == "bootstraping" ]]; then
        echo "idle"
        exit
    elif [[ $(< ../state) == "bootstraped" ]]; then
        # the environment is bootstraped but we cdont have state file nor the process in memory ...
        if [ -f $out_file ]; then
            echo "done"
            exit
        else
            echo "aborted"
            exit
        fi
    fi
fi

echo "unknown"