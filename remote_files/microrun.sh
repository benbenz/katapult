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

echo 'running' > $run_path/$uid-state

{ $thecommand >run.log && echo "done" > $run_path/$uid-state && cp "$out_file" "$uid-$out_file" 2>/dev/null; }