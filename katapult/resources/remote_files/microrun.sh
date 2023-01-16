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

echo 'running(running normally)' > $run_path/state

# { $thecommand >run.log && echo 'done(completed normally)' > $run_path/state 2>&1; } 2>>run.log

# this new code allows to capture the child pid (the script/command PID)
$thecommand 2>&1 >run.log & child_pid=$!
echo ",$child_pid" >> $pid_file
wait $child_pid
exit_status=$?
if [[ $exit_status == 0 ]]; then
  echo "done(completed normally)" > $run_path/state
else
  echo "aborted(exit status = $exit_status)" > $run_path/state
fi