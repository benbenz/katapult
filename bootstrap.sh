#!/usr/bin/bash

#source /etc/profile
#source $HOME/.bashrc
#exit

if (( $# < 1 )); then
  echo "$0 ENV_NAME"
  exit 0
else
  env_name="$1"; shift
fi

FILE_CONDA="environment.yml"
FILE_PYPI="requirements.txt"

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

  if ! [ -x "$(command -v $HOME/.local/bin/micromamba)" ]; then
    echo "installing mamba ..."
    curl micro.mamba.pm/install.sh | bash
    export MAMBA_ROOT_PREFIX=/home/ubuntu/micromamba
    export MAMBA_EXE=/home/ubuntu/.local/bin/micromamba
    #eval "$($HOME/.local/bin/micromamba shell hook -s posix)"
    eval "$($HOME/.local/bin/micromamba shell hook --shell=bash)"
  else
    echo "mambda has been found"
    # somehow we cant activate the bashrc ... >> init conda everytime ...
    # source $HOME/miniconda/bin/activate >/dev/null
    #$HOME/miniconda/bin/conda init >/dev/null
    export MAMBA_ROOT_PREFIX=/home/ubuntu/micromamba
    export MAMBA_EXE=/home/ubuntu/.local/bin/micromamba
    #eval "$($HOME/.local/bin/micromamba shell hook -s posix)"
    eval "$($HOME/.local/bin/micromamba shell hook --shell=bash)"
    #source /home/ubuntu/.bashrc    
  fi  

  # 2. check if we need to create the environment

  #if ! [ -x "$($HOME/miniconda/bin/conda info --envs | grep $env_name)" ];then
  # if { $HOME/miniconda/bin/conda env list | grep $env_name; } >/dev/null 2>&1; then
  #   echo "environment not found"
  #   $HOME/miniconda/bin/conda create -y -n $env_name 
  #   echo "environment created"
  # fi
  #$HOME/miniconda/bin/activate $env_name >/dev/null
  micromamba activate $env_name
  if [ $? -eq 0 ]; then
    echo "conda environment exists"
  else
    echo "conda environment not found"
    # $HOME/miniconda/bin/conda create -y -n "$env_name"
    # use mambda instead
    micromamba create -y -f "$FILE_CONDA" -n "$env_name"

    echo "conda environment created"
  fi

  # 3. activate the environment
  

  #$HOME/miniconda/bin/activate $env_name >/dev/null
  # or using micromamba
  #$HOME/.local/bin/micromamba activate $env_name
  micromamba activate $env_name

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
    source ".$env_name/bin/activate"
  fi
  
fi # FILE_PYPI

python3 $HOME/run_remote.py
