#!/usr/bin/bash

if ! [ -d "$HOME/cloudsend/.venv/maestro" ]; then
    echo "virtual environment not found"
    mkdir -p $HOME/cloudsend/.venv
    cd cloudsend/.venv
    virtualenv "maestro"
    cd $HOME/cloudsend
    source ".venv/maestro/bin/activate"
    .venv/maestro/bin/pip install -r requirements.txt
else
    echo "virtual environment exists"
    # we activate in run.sh now
    source "$HOME/cloudsend/.venv/maestro/bin/activate"
fi