#!/usr/bin/bash

if (( $# < 4 )); then
    echo "$0 ENV_NAME JOB_HASH UID PID OUTPUT_FILES"
    exit 0
else
    env_name="$1"; shift
    job_hash="$1"; shift
    uid="$1"; shift
    pid=$1; shift
    pid_child=$1; shift
    output_files="$1"; shift
fi

while [ $job_hash ]
do

    if [[ "$job_hash" == "None" ]]; then
        thestate="unknown(no job hash provided)"
        #exit
    fi

    run_path="$HOME/run/$env_name/$job_hash/$uid"

    if [ -d $run_path ]; then
        cd $run_path 

        # this is running (by UID)
        # https://stackoverflow.com/questions/3601515/how-to-check-if-a-variable-is-set-in-bash
        # ${thestate+x} evaluates empty var 'thestate'
        if [ -z ${thestate+x} ] && [[ $uid != "None" ]]; then
            if [ -f "state" ]; then
                # split string of output_files
                all_output_files=1
                OUT_FILES_ARR=(${output_files//|/ })
                for output_file in "${OUT_FILES_ARR[@]}"
                do
                    if ! [ -f "$output_file" ] ; then
                        all_output_files=0
                    fi
                done
                if [[ $(< state) =~ ^running.*$ ]] && ! [[ $(ps aux | grep "$uid" | grep -v 'grep' | grep -v 'state.sh') ]]; then
                    # check if this is a memory issue:
                    # dmesg command; 
                    # or at the logfiles /var/log/kern.log, /var/log/messages, or /var/log/syslog.
                    
                    if [[ "$pid_child" != "None" ]] && [[ $(sudo dmesg | grep "pid=$pid_child" | grep "oom-kill") ]]; then
                        thestate="aborted(script exited abnormally [OOM Memory Kill])"
                    else
                        # it says its running but we didnt find the UID, the PID nor the command name >> this has been aborted
                        thestate="aborted(script exited abnormally)"
                    fi
                # if state is done but we dont have the out file, this is probably aborted
                # anyhow we cant do anything because we dont have an output file
                elif [[ $(< state) =~ ^done.*$ ]] && [[ $all_output_files == 0 ]]; then
                    thestate="aborted(script terminated abnormally [missing output file])" 
                else
                    # just display this state
                    thestate=$(< state)
                    thestate="$thestate"
                    #tail state
                    #exit
                fi
            elif [[ $(ps aux | grep "$uid" | grep -v 'grep' | grep -v 'state.sh') ]] ; then
                thestate="running(running normally [1])"
                #exit
            fi
        fi
    fi

    # this is running (by PID)
    if [ -z ${thestate+x} ] && [[ $pid != "None" ]] && ! [[ $pid -eq 0 ]]; then
        if [[ $(ps -p $pid | tail +2) ]] ; then
            thestate="running(running normally [2])"
            #exit
        fi
        if [[ $(ps --ppid $pid | tail +2) ]]; then #usually this is the one that will hit positive (when using PID)
            thestate="running(running normally [3])"
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
        thestate="unknown(no process info)"
        #exit
    fi

    if [ $pid == "None" ] && [ -f "$run_path/pid" ] ; then
        info_process=$(< "$run_path/pid")
        arrIN=(${info_process//,/ })
        pid=${arrIN[1]} 
    fi

    # the problem here is we may not be able to catch the PID on time ....
    # hence we wont have this info to retrieve errors
    # >> read in the pid file of the process, we have added the child pid now (appended by microrun.sh)

    #micro_pid=$(ps -ef | grep 'microrun.sh' | grep "$uid" | grep -v 'grep' | awk '{print $2}')
    #child_pid_out=$(pgrep -P $micro_pid) # this should give the script/command PID
    if [ $pid_child == "None" ] && [ -f "$run_path/pid" ] ; then
        info_process=$(< "$run_path/pid")
        arrIN=(${info_process//,/ })
        pid_child=${arrIN[2]} 
    fi

    echo "$uid,$pid,$thestate,$pid_child"

    # gets the next set of input parameters (hash,uid,pid,outfile)
    env_name="$1"; shift
    job_hash="$1"; shift
    uid="$1"; shift
    pid=$1; shift
    pid_child=$1; shift
    output_files="$1"; shift

    unset thestate

done