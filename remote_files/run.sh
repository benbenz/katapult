#!/usr/bin/bash

#echo $$

if (( $# < 6 )); then
  echo "$0 ENV_NAME CMD IN_FILE OUT_FILE RUN_HASH PID_FILE"
  exit 0
else
  env_name="$1"; shift
  thecommand="$1"; shift
  input_file="$1"; shift
  output_file="$1"; shift
  run_hash="$1"; shift
  pid_file="$1"; shift
fi

run_path="$HOME/run/$env_name/$run_hash"

# TODO: check if existing PID and PID running ... and throw warning, exit or do something ?
#printf '%s\n' $$ > $pid_file

echo 'idle' > $run_path/state # used to check the state of a process
rm -f output_file

FILE_CONDA="$HOME/run/$env_name/environment.yml"
FILE_PYPI="$HOME/run/$env_name/requirements.txt"

if [ -f "$FILE_CONDA" ]; then

    export MAMBA_ROOT_PREFIX=/home/ubuntu/micromamba
    export MAMBA_EXE=/home/ubuntu/.local/bin/micromamba
    eval "$($HOME/.local/bin/micromamba shell hook --shell=bash)"
    micromamba activate "$env_name"

fi 

if ([ -f "$FILE_PYPI" ] && ! [ -f "$FILE_CONDA" ]); then
    source ".$env_name/bin/activate"
fi

# TODO: check if existing PID and PID running ... and throw warning, exit or do something ?
printf '%s\n' $$ > $pid_file

#exec nohup $HOME/run/$env_name/microrun.sh "$thecommand" "$run_path"
#exit

cd $run_path
echo 'running' > $run_path/state
#exec nohup $thecommand >run.log 2>&1  
#exec $thecommand >run.log
#$( exec $thecommand >run.log && echo 'done' > $run_path/state) & printf '%s\n' $(jobs -p) >  "${pid_file}2"
($thecommand >run.log && echo 'done' > $run_path/state) & printf '%s\n' $(jobs -p) >  "${pid_file}2"
#( exec $thecommand >run.log && echo 'done' > $run_path/state ) & printf '%s\n' $(jobs -p) >  "${pid_file}2"
#wait $!
#wait $(jobs -p)
#wait 
#echo 'done' > $run_path/state #& printf '%s\n' $! > "${pid_file}2") 

# stop the instance if no other scripts are running 
#if ! [ ps aux | grep "$HOME/run.sh" | grep -v 'grep' ]; then
#  aws ec2 stop-instances --instance-ids $(ec2metadata --instance-id) --region $(ec2metadata --availability-zone | sed 's/.$//')
#fi
