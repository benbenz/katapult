#!/usr/bin/bash

#echo $$

if (( $# < 6 )); then
  echo "$0 ENV_NAME CMD IN_FILE OUT_FILE JOB_HASH UID"
  exit 0
else
  env_name="$1"; shift
  thecommand="$1"; shift
  input_files="$1"; shift
  output_files="$1"; shift
  batch_uid="$1"; shift
  job_hash="$1"; shift
  uid="$1"; shift
fi

env_path="$HOME/run/$env_name"
run_path="$HOME/run/$env_name/$job_hash/$uid"
pid_file="$run_path/pid"
cmd_file="$run_path/cmd"

function check_cancelled () {
  # the job has been marked as cancelled by kill.sh
  if [[ $(grep -s "$uid" $HOME/run/cancelled) ]]; then
    echo "Job has been cancelled by kill command"
    echo 'aborted(cancelled by kill)' > $run_path/state # used to check the state of a process
    exit 1
  fi
}

check_cancelled


# TODO: check if existing PID and PID running ... and throw warning, exit or do something ?
# we print the mother PID in the PID file (it used to be the one from microrun)
printf '%s,%s' $uid $$ > $pid_file

printf '%s\n%s\n' "$thecommand" $input_files > $cmd_file

echo 'wait(waiting for environment)' > $run_path/state # used to check the state of a process

OUT_FILES_ARR=(${output_files//|/ })
for output_file in "${OUT_FILES_ARR[@]}"
do
  rm -f $output_file
done

waittime=0
while [[ $(< $env_path/state) != "bootstraped" ]] || ! [ -f $env_path/state ]
do
  check_cancelled
  if [[ $(< $env_path/state) == "failed" ]]; then
    echo "Environment bootstraping has FAILED"
    echo 'aborted(environment has failed)' > $run_path/state # used to check the state of a process
    exit 97
  fi
  if [[ $(ps aux | grep "bootstrap.sh" | grep "$env_name" | grep -v 'grep') ]]; then
    echo "Waiting on environment to be bootstraped"
    sleep 15 # sleep 15 seconds
    ((waittime=waittime+15))
    if [ $waittime -gt 3600 ]; then
      echo "Waited too long for bootstraped environment\nexiting"
      echo 'aborted(waited too long for environment)' > $run_path/state
      exit 99
    fi
  else
    echo "Bootstraping has stopped without success, exiting"
    echo 'aborted(bootstraping has failed)' > $run_path/state
    exit 98
  fi
done
echo "Environment is bootstraped"

while [[ $(ps aux | grep "batch_run" | grep -v "batch_run-$batch_uid" | grep -v 'grep') ]]
do
  echo "Waiting on previous batch to finish"
  echo 'wait(waiting on previous batch to finish)' > $run_path/state
  sleep 15
done

echo 'idle(about to start)' > $run_path/state # used to check the state of a process

FILE_CONDA="$HOME/run/$env_name/environment.yml"
FILE_PYPI="$HOME/run/$env_name/requirements.txt"

if [ -f "$FILE_CONDA" ]; then

    export MAMBA_ROOT_PREFIX=/home/ubuntu/micromamba
    export MAMBA_EXE=/home/ubuntu/.local/bin/micromamba
    eval "$($HOME/.local/bin/micromamba shell hook --shell=bash)"
    micromamba activate "$env_name"

fi 

if ([ -f "$FILE_PYPI" ] && ! [ -f "$FILE_CONDA" ]); then
    source "$HOME/run/.$env_name/bin/activate"
fi

#exec nohup $HOME/run/$env_name/microrun.sh "$thecommand" "$run_path"
#exit

check_cancelled

cd $run_path
echo 'running(normally)' > $run_path/state
#exec nohup $thecommand >run.log 2>&1  
#exec $thecommand >run.log
#$( exec $thecommand >run.log && echo 'done' > $run_path/state) & printf '%s\n' $(jobs -p) >  "${pid_file}2"
#($thecommand >run.log && echo 'done' > $run_path/state) & printf '%s\n' $(jobs -p) >  "${pid_file}2"
# { $thecommand >run.log & export pid=$! & echo $pid > "${pid_file}2" && wait $pid; } && echo 'done' > $run_path/state
# { $HOME/run/$env_name/microrun.sh "$thecommand" "$run_path" & echo $! > "${pid_file}2"; }

# { $HOME/run/$env_name/microrun.sh "$thecommand" "$uid" "$run_path" "$pid_file" "$output_files" & echo $! > "${pid_file}"; }


# { $HOME/run/microrun.sh "$thecommand" "$uid" "$run_path" "$pid_file" "$output_files"; }
# CHANGED FOR INLINE COMMAND:
#$thecommand 2>&1 >run.log & child_pid=$!
#$thecommand 2>error.log >run.log & child_pid=$!
bash -c "$thecommand" 2>error.log >run.log & child_pid=$!
echo ",$child_pid" >> $pid_file
wait $child_pid
exit_status=$?
if [[ $exit_status == 0 ]]; then
  echo "done(completed normally)" > $run_path/state
else
  echo "aborted(exit status = $exit_status)" > $run_path/state
fi

# pgrep -P PID >>> Get the subprocesses


# stop the instance if no other scripts are running 
#if ! [ ps aux | grep "$HOME/run.sh" | grep -v 'grep' ]; then
#  aws ec2 stop-instances --instance-ids $(ec2metadata --instance-id) --region $(ec2metadata --availability-zone | sed 's/.$//')
#fi
