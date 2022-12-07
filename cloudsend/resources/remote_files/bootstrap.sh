#!/usr/bin/bash

#source /etc/profile
#source $HOME/.bashrc
#exit

if (( $# < 2 )); then
  echo "$0 ENV_NAME DEV"
  exit 0
else
  env_name="$1"; shift
  dev=$2; shift
fi

FILE_SH="$HOME/run/$env_name/env_command.sh"
FILE_CONDA="$HOME/run/$env_name/environment.yml"
FILE_PYPI="$HOME/run/$env_name/requirements.txt"
FILE_APTGET="$HOME/run/$env_name/aptget.sh"
FILE_JULIA="$HOME/run/$env_name/env_julia.jl"

echo "bootstraping" > "$HOME/run/$env_name/state"

rm -f "$HOME/run/$env_name/ready"

if [ -f "$FILE_SH" ]; then
  (cd "$HOME/run/$env_name/"; "$FILE_SH")
fi

if [ -f "$FILE_APTGET" ]; then
  $FILE_APTGET
fi

if [ -f "$FILE_CONDA" ]; then

  # 1. check if we need to install conda

  # if ! [ -x "$(command -v $HOME/miniconda/bin/conda)" ]; then
  #   echo "installing conda ..."
  #   # get conda
  #   wget https://repo.anaconda.com/miniconda/Miniconda3-py38_4.12.0-Linux-x86_64.sh
  #   # install in silent mode
  #   bash Miniconda3-py38_4.12.0-Linux-x86_64.sh -f -b -p $HOME/miniconda
  #   source $HOME/miniconda/bin/activate >/dev/null
  #   $HOME/miniconda/bin/conda init >/dev/null
  #   source /home/ubuntu/.bashrc

  # else
  #   echo "conda has been found"
  #   # somehow we cant activate the bashrc ... >> init conda everytime ...
  #   # source $HOME/miniconda/bin/activate >/dev/null
  #   #$HOME/miniconda/bin/conda init >/dev/null
  # fi

  export MAMBA_ROOT_PREFIX=/home/ubuntu/micromamba
  export MAMBA_EXE=/home/ubuntu/.local/bin/micromamba
  
  if ! [ -x "$(command -v $HOME/.local/bin/micromamba)" ]; then
    echo "installing mamba ..."
    curl micro.mamba.pm/install.sh | bash
    #eval "$($HOME/.local/bin/micromamba shell hook -s posix)"
    eval "$($HOME/.local/bin/micromamba shell hook --shell=bash )"
  else
    echo "mamba has been found"
    #eval "$($HOME/.local/bin/micromamba shell hook -s posix)"
    eval "$($HOME/.local/bin/micromamba shell hook --shell=bash )"
  fi  

  # 2. check if we need to create the environment

  #if ! [ -x "$($HOME/miniconda/bin/conda info --envs | grep $env_name)" ];then
  # if { $HOME/miniconda/bin/conda env list | grep $env_name; } >/dev/null 2>&1; then
  #   echo "environment not found"
  #   $HOME/miniconda/bin/conda create -y -n $env_name 
  #   echo "environment created"
  # fi
  #$HOME/miniconda/bin/activate $env_name >/dev/null
  if [[ "$dev" -eq 1 ]]; then
    echo "overwriting mamba environment"
    micromamba create -y -f "$FILE_CONDA" -n "$env_name"
    echo "mamba environment created"
  else
    micromamba activate $env_name
    if [[ $? -eq 0 ]]; then
      echo "mamba environment exists"
    else
      echo "mamba environment not found"
      # $HOME/miniconda/bin/conda create -y -n "$env_name"
      # use mambda instead
      micromamba create -y -f "$FILE_CONDA" -n "$env_name"

      echo "mamba environment created"
    fi
  fi

  # 3. activate the environment
  micromamba activate $env_name

  # we activate in run.sh now
  #$HOME/miniconda/bin/activate $env_name >/dev/null
  #micromamba activate $env_name

fi # FILE_CONDA

# we use virtualenv only if requirements.txt is here and NO conda env is used ...
# otherwise, conda will handle the PIP dependencies ...

if ([ -f "$FILE_PYPI" ] && ! [ -f "$FILE_CONDA" ]); then

  # 1. nothing to do: virtualenv is already installed

  # 2. check if we need to create the virtual environment, and activate
  if ! [ -d ".$env_name" ]; then
    echo "virtual environment not found"
    virtualenv ".$env_name"
    source ".$env_name/bin/activate"
    .$env_name/bin/pip install -r requirements.txt
  else
    echo "virtual environment exists"
    # we activate in run.sh now
    source ".$env_name/bin/activate"
  fi
  
fi # FILE_PYPI


if [ -f "$FILE_JULIA" ]; then
  julia $FILE_JULIA
  echo "Julia packages installed"
fi


echo "bootstraped" > "$HOME/run/$env_name/state"

echo "" > "$HOME/run/$env_name/ready"

#python3 $HOME/run_remote.py
