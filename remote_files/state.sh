#!/usr/bin/bash

if (( $# < 4 )); then
    echo "$0 ENV_NAME JOB_HASH UID PID OUT_FILE"
    exit 0
else
    env_name="$1"; shift
    job_hash="$1"; shift
    uid="$1"; shift
    pid=$1; shift
    out_file="$1"; shift
fi

if [[ "$job_hash" == "None" ]]; then
    echo 'unknown(0)'
    exit
fi

run_path="$HOME/run/$env_name/$job_hash/$uid"
cd $run_path 

# this is running (by UID)
if [[ $uid != "None" ]]; then
    if [[ $(ps aux | grep "$uid" | grep -v 'grep' | grep -v 'state.sh') ]] ; then
        echo "running(1)"
        exit
    fi
    if [ -f "state" ]; then
        # it says its running but we didnt find the UID, the PID nor the command name >> this has been aborted
        if [[ $(< state) == "running" ]]; then
            echo "aborted(1)"
            exit
        fi
        # if state is done but we dont have the out file, this is probably aborted
        # anyhow we cant do anything because we dont have an output file
        if [[ $(< state) == "done" ]]; then
            if ! [ -f "$out_file" ]; then
                echo "aborted(2)" 
                exit
            fi
            echo "done(1)"
            exit
        fi
        # just display this state
        tail state
        exit
    fi

fi

# this is running (by PID)
if [[ pid != "None" ]] && ! [[ pid -eq 0 ]]; then
    if [[ $(ps -p $pid | tail +2) ]] ; then
        echo "running(2)"
        exit
    fi
    if [[ $(ps -ppid $pid | tail +2) ]]; then #usually this is the one that will hit positive (when using PID)
        echo "running(3)"
        exit
    fi
fi

# check if we have a command state file
if [[ "$job_hash" != "None" ]]; then
    if [[ $(ps aux | grep "$env_name/$job_hash" | grep -v 'grep') ]]; then
        echo "running(4)"
        exit
    fi
fi

cd "$HOME/run/$env_name"
# check what is the environment state file
if [ -f state ]; then
    if [[ $(< state) == "bootstraping" ]]; then
        echo "idle(1)"
        exit
    elif [[ $(< state) == "bootstraped" ]]; then
        # the environment is bootstraped but we dont have state file nor the process in memory ...
        # lets consider it aborted
        echo "aborted(3)"
        exit
    fi
fi

echo "unknown"
exit