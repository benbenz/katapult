#!/usr/bin/bash

if (( $# < 5)); then
  echo "$0 COMMAND UID RUN_PATH PID_FILE OUT_FILE"
  exit 99
else
  thecommand="$1"; shift
  uid="$1"; shift
  run_path="$1"; shift
  pid_file="$1"; shift
  out_file="$1"; shift
fi

cd $run_path

echo 'running' > $run_path/state

# { $thecommand >$uid-run.log && echo "done" > $run_path/state && cp "$out_file" "$uid-$out_file" 2>/dev/null; }
{ $thecommand >run.log && echo "done" > $run_path/state 2>&1; } 2>>run.log
