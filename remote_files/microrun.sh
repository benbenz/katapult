#!/usr/bin/bash

if (( $# < 3 )); then
  echo "$0 COMMAND RUN_PATH PID_FILE"
  exit 99
else
  thecommand="$1"; shift
  run_path="$1"; shift
  pid_file="$1"; shift
fi

cd $run_path

echo 'running' > $run_path/state

{ $thecommand >run.log && echo "done" > $run_path/state; }
# $thecommand >run.log && echo "done" > $run_path/state; 
# if nohup $thecommand >run.log; then
#     echo "done" > $run_path/state
# else
#     echo "aborted" > $run_path/state
# fi