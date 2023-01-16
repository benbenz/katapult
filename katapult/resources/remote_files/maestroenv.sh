#!/usr/bin/bash

if ! [ -d "$HOME/katapult/.venv/maestro" ]; then
    echo "virtual environment not found"
    mkdir -p $HOME/katapult/.venv
    cd katapult/.venv
    virtualenv "maestro"
    cd $HOME/katapult
    source ".venv/maestro/bin/activate"
    .venv/maestro/bin/pip install -r requirements.txt
else
    echo "virtual environment exists"
    # we activate in run.sh now
    source "$HOME/katapult/.venv/maestro/bin/activate"
fi