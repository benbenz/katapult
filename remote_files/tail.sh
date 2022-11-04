#!/usr/bin/bash

if (( $# < 3 )); then
    echo "$0 ENV_NAME SCRIPT_HASH UID"
    exit 0
else
    env_name="$1"; shift
    script_hash="$1"; shift
    uid="$1"; shift
fi

run_path="$HOME/run/$env_name/$script_hash"

tail -f "$run_path/$uid-run.log"