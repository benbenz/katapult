#!/usr/bin/bash

if (( $# < 2 )); then
  echo "$0 COMMAND RUN_PATH"
  exit 99
else
  thecommand="$1"; shift
  run_path="$1"; shift
fi

cd $run_path

echo 'running' > $run_path/state

if nohup $thecommand >run.log; then
    echo "done" > $run_path/state
else
    echo "aborted" > $run_path/state
fi