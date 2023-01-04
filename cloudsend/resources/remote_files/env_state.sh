#!/usr/bin/bash

if (( $# < 1 )); then
    echo "$0 ENV_NAME"
    exit 0
else
    env_name="$1"; shift
fi

if [[ "$env_name" == "None" ]]; then
    thestate="unknown(no job hash provided)"
    #exit
fi

env_path="$HOME/run/$env_name"
thestate=""
errors=""
thelog=""

if [ -d $env_path ] && [[ $env_name != "None" ]]; then
    cd $env_path 

    # this is running (by UID)
    # https://stackoverflow.com/questions/3601515/how-to-check-if-a-variable-is-set-in-bash
    # ${thestate+x} evaluates empty var 'thestate'
    if [ -f "state" ]; then
        if [[ $(< state) =~ ^bootstraping.*$ ]] && ! [[ $(ps aux | grep "bootstrap.sh" | grep "$env_name" | grep -v 'grep' | grep -v 'env_state.sh') ]]; then
            # it says its running but we didnt find the UID, the PID nor the command name >> this has been aborted
            thestate="environment failed while bootstraping"
            #exit
        else
            # just display this state
            thestate=$(< state)
            thestate="$thestate"
            #tail state
            #exit
        fi
    elif [[ $(ps aux | grep "$uid" | grep -v 'grep' | grep -v 'state.sh') ]] ; then
        thestate="environment not created [1]"
        #exit
    fi
else
    thestate = "environment not created [2]"
fi

if [ -f "errors" ]; then
    errors=$(<errors)
    errors="$errors"
else
    errors="null"
fi

printf "{\"name\":\"$env_name\",\"state\":\"$thestate\",\"errors\":$errors}"