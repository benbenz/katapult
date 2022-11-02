#!/usr/bin/bash

if (( $# < 2 )); then
  echo "$0 ENV_NAME CMD"
  exit 0
else
  env_name="$1"; shift
  thecommand="$1"; shift
fi

FILE_CONDA="environment.yml"
FILE_PYPI="requirements.txt"

if [ -f "$FILE_CONDA" ]; then

    export MAMBA_ROOT_PREFIX=/home/ubuntu/micromamba
    export MAMBA_EXE=/home/ubuntu/.local/bin/micromamba
    eval "$($HOME/.local/bin/micromamba shell hook --shell=bash)"
    micromamba activate "$env_name"

fi 

if ([ -f "$FILE_PYPI" ] && ! [ -f "$FILE_CONDA" ]); then
    source ".$env_name/bin/activate"
fi

eval "$thecommand"

#$HOME/.local/bin/micromamba run -a stdout,stderr -n "$env_name" $thecommand
