#!/usr/bin/bash

if ! [ -d "$HOME/cloudrun/.venv/maestro" ]; then
    echo "virtual environment not found"
    mkdir -p $HOME/cloudrun/.venv
    cd cloudrun/.venv
    virtualenv "maestro"
    cd $HOME/cloudrun
    source ".venv/maestro/bin/activate"
    .venv/maestro/bin/pip install -r requirements.txt
else
    echo "virtual environment exists"
    # we activate in run.sh now
    source "$HOME/cloudrun/.venv/maestro/bin/activate"
fi