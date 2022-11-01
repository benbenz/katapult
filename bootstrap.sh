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


if ! [ -x "$(command -v $HOME/miniconda/bin/conda)" ]; then
  echo "installing conda ..."
  # get conda
  wget https://repo.anaconda.com/miniconda/Miniconda3-py38_4.12.0-Linux-x86_64.sh
  # install in silent mode
  bash Miniconda3-py38_4.12.0-Linux-x86_64.sh -f -b -p $HOME/miniconda
  source $HOME/miniconda/bin/activate >/dev/null
  $HOME/miniconda/bin/conda init >/dev/null
  source /home/ubuntu/.bashrc
else
  echo "conda has been found"
  # somehow we cant activate the bashrc ... >> init conda everytime ...
  source $HOME/miniconda/bin/activate >/dev/null
  $HOME/miniconda/bin/conda init >/dev/null
fi

#echo "$env_name"
if ! [ -x "$($HOME/miniconda/bin/conda info --envs | grep $env_name)" ];then
  echo "environment not found"
  $HOME/miniconda/bin/conda create -y -n $env_name 
  echo "environment created"
fi