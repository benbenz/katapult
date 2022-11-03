#!/usr/bin/bash

echo $$

if (( $# < 2 )); then
  echo "$0 ENV_NAME CMD"
  exit 0
else
  env_name="$1"; shift
  thecommand="$1"; shift
  input_file="$1"; shift
  output_file="$1"; shift
  run_hash="$1"; shift
fi

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

cd "$HOME/run/$env_name/$run_hash"
#eval "nohup $thecommand >/dev/null 2>&1 &"
#eval "$thecommand >/dev/null 2>&1 &"
#eval "$thecommand"
#exec $thecommand
exec nohup $thecommand >run.log 2>&1 
#cmd_pid=$!
#echo "__PID_RUN__($$)"
#echo "__PID_CMD__($cmd_pid)"

#$HOME/.local/bin/micromamba run -a stdout,stderr -n "$env_name" $thecommand

# stop the instance if no other scripts are running 
#if ! [ ps aux | grep "$HOME/run.sh" | grep -v 'grep' ]; then
#  aws ec2 stop-instances --instance-ids $(ec2metadata --instance-id) --region $(ec2metadata --availability-zone | sed 's/.$//')
#fi
