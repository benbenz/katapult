#!/usr/bin/bash

if (( $# < 1 )); then
  echo "$0 PID_FILE"
  exit 0
else
  pid_file="$1"; shift
fi

waittime=0
while ! [ -f "$pid_file" ]
do
    sleep 15
    waittime = waittime + 15
    if [waittime>3600]; then
        echo "Waited too long for PID ... exiting"
        exit 99
    fi
done 

tail "$pid_file"