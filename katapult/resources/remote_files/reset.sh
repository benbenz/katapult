#!/usr/bin/bash

# for pid in `ps -ef | grep 'run.sh' | awk '{print $2}'` ; do
#     microrun_pid=$(pgrep -P $pid)
#     if ! [ -z ${microrun_pid+x} ] ; then
#         script_pid=$(pgrep -P $microrun_pid)
#         if ! [ -z ${script_pid+x} ] ; then
#             kill $script_pid
#         fi
#         kill $microrun_pid
#     fi
# done

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
