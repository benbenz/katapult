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

while [ $job_hash ]
do

    if [[ "$job_hash" == "None" ]]; then
        thestate="unknown(0)"
        #exit
    fi

    run_path="$HOME/run/$env_name/$job_hash/$uid"

    if [ -d $run_path ]; then
        cd $run_path 

        # this is running (by UID)
        if [ -z ${thestate+x} ] && [[ $uid != "None" ]]; then
            if [ -f "state" ]; then
                if [[ $(< state) == "running" ]] && ! [[ $(ps aux | grep "$uid" | grep -v 'grep' | grep -v 'state.sh') ]]; then
                    # it says its running but we didnt find the UID, the PID nor the command name >> this has been aborted
                    thestate="aborted(1)"
                    #exit
                # if state is done but we dont have the out file, this is probably aborted
                # anyhow we cant do anything because we dont have an output file
                elif [[ $(< state) == "done" ]] && ! [ -f "$out_file" ] ; then
                    thestate="aborted(2)" 
                    #exit
                else
                    # just display this state
                    thestate=$(< state)
                    thestate="$thestate(0)"
                    #tail state
                    #exit
                fi
            elif [[ $(ps aux | grep "$uid" | grep -v 'grep' | grep -v 'state.sh') ]] ; then
                thestate="running(1)"
                #exit
            fi
        fi
    fi

    # this is running (by PID)
    if [ -z ${thestate+x} ] && [[ $pid != "None" ]] && ! [[ $pid -eq 0 ]]; then
        if [[ $(ps -p $pid | tail +2) ]] ; then
            thestate="running(2)"
            #exit
        fi
        if [[ $(ps --ppid $pid | tail +2) ]]; then #usually this is the one that will hit positive (when using PID)
            thestate="running(3)"
            #exit
        fi
    fi

    # check if we have a command state file
    # THIS IS TOO GLOBAL ...
    #if [ -z ${thestate+x} ] && [[ "$job_hash" != "None" ]]; then
    #    if [[ $(ps aux | grep "$env_name/$job_hash" | grep -v 'grep') ]]; then
    #        echo "running(4)"
    #        exit
    #    fi
    #fi

    # check what is the environment state file

# THIS IS NOT ROBUST because we may have an new instance bootstraping and we may be checking the UID of a process from an older instance ...
# this could return WAIT which is not okay
# it should return ABORTED or UNKNOWN at least
    # if [ -z ${thestate+x} ] && [ -d "$HOME/run/$env_name" ]; then
    #     cd "$HOME/run/$env_name"
    #     if [ -z ${thestate+x} ] && [ -f state ]; then
    #         if [[ $(< state) == "bootstraping" ]]; then
    #             thestate="wait(1)"
    #             #exit
    #         elif [[ $(< state) == "bootstraped" ]]; then
    #             # the environment is bootstraped but we dont have state file nor the process in memory ...
    #             # lets consider it aborted
    #             thestate="aborted(3)"
    #             #exit
    #         fi
    #     fi
    # fi

    if [ -z ${thestate+x} ] ; then
        thestate="unknown(1)"
        #exit
    fi

    if [ $pid == "None" ] && [ -f "$run_path/pid" ] ; then
        info_process=$(< "$run_path/pid")
        arrIN=(${info_process//,/ })
        pid=${arrIN[1]} 
    fi

    echo "$uid,$pid,$thestate"

    # gets the next set of input parameters (hash,uid,pid,outfile)
    env_name="$1"; shift
    job_hash="$1"; shift
    uid="$1"; shift
    pid=$1; shift
    out_file="$1"; shift

    unset thestate

done