#!/usr/bin/bash

if (( $# < 3 )); then
    echo "$0 ENV_NAME JOB_HASH UID"
    exit 0
else
    env_name="$1"; shift
    job_hash="$1"; shift
    uid="$1"; shift
fi

run_path="$HOME/run/$env_name/$job_hash"

tail -f "$run_path/$uid-run.log"