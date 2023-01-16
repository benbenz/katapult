#!/usr/bin/bash

if (( $# < 1 )); then
    echo "$0 UID"
    exit 0
fi

global_path="$HOME/run"

for uid in "$@"
do
    # mark the job as cancelled
    echo "$uid" >> $global_path/cancelled
done

for uid in "$@"
do
    # kill the processes
    # if [[ $(ps -ef | awk '/[m]icrorun.sh.*'"$uid"'/{print $2}' | xargs ps -o pid --no-heading --ppid) ]] ; then
    #    ps -ef | awk '/[m]icrorun.sh.*'"$uid"'/{print $2}' | xargs ps -o pid --no-heading --ppid | xargs kill 
    # fi
    # if [[ $(ps -ef | awk '/[m]icrorun.sh.*'"$uid"'/{print $2}') ]] ; then
    #    ps -ef | awk '/[m]icrorun.sh.*'"$uid"'/{print $2}' | xargs kill 
    # fi
    # if [[ $(ps -ef | awk '/[r]un.sh.*'"$uid"'/{print $2}' | xargs ps -o pid --no-heading --ppid) ]] ; then
    #     ps -ef | awk '/[r]un.sh.*'"$uid"'/{print $2}' | xargs ps -o pid --no-heading --ppid | xargs kill
    # fi
    if [[ $(ps -ef | awk '/[r]un.sh.*'"$uid"'/{print $2}') ]] ; then
        ps -ef | awk '/[r]un.sh.*'"$uid"'/{print $2}' | xargs pkill -P 
    fi

    # mark as aborted
    echo "aborted(9)" > $HOME/run/*/*/$uid/state

    # gets the next set of input parameters (uid)
    uid="$1"; shift

done