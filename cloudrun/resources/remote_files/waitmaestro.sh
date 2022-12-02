if (( $# > 0  )); then
    with_log=$1
else
    with_log=0
fi

waittime=0
taillog=0
linecount_start=0
linecount_end=0
while ! [[ $(ps -ef | awk '/[m]aestroserver/{print $2}') ]] || ! [[ $(lsof -i TCP | grep 'localhost:5000' | grep LISTEN) ]]
do
    echo -e "\033[1m\033[5m... Waiting on maestro server ...\033[0m"
    if [ $with_log -eq 1 ]; then
        if [ $taillog -eq 0 ]; then
            cat $HOME/maestro.log
            linecount_start=$(wc -l < $HOME/maestro.log)
            ((taillog=taillog+1))
        else
            linecount_end=$(wc -l < $HOME/maestro.log)
            ((linecount=linecount_end-linecount_start))
            tail -n $linecount $HOME/maestro.log
            ((linecount_start=linecount_end))
        fi
    fi
    sleep 5 # sleep 15 seconds
    ((waittime=waittime+5))
    if [ $waittime -gt 3600 ]; then
        echo "Waited too long for maestro\nexiting"
        exit 99
    fi
done

if [ $with_log -eq 1 ]; then
    linecount_end=$(wc -l < $HOME/maestro.log)
    ((linecount=linecount_end-linecount_start))
    tail -n $linecount $HOME/maestro.log
    ((linecount_start=linecount_end))
fi
