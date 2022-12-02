waittime=0
while ! [[ $(ps -ef | awk '/[m]aestroserver/{print $2}') ]] || ! [[ $(lsof -i TCP | grep 'localhost:5000' | grep LISTEN) ]]
do
    echo "Waiting on maestro server"
    sleep 5 # sleep 15 seconds
    ((waittime=waittime+5))
    if [ $waittime -gt 3600 ]; then
        echo "Waited too long for maestro\nexiting"
        exit 99
    fi
done