#!/bin/bash

configFileSetup() {

    rowLimiter
    echo "Creating and configuring the config files"

    local local_dir="$(dirname ${1})"
    echo "> local_dir: ${local_dir}"
    local config_dir=$(realpath ${local_dir}/../config_files)
    python3 "${local_dir}/createConfigFile.py" "${config_dir}"

    echo "Finished the config file setup"

}

# Start if not used as source
if [ "${1}" != "--source-only" ]; then
    if (( $# != 1 )); then
        >&2 echo "Illegal number of parameters for the configFileSetup file"
        abortInstallScript
    fi

    # prelude
    local mainPath="$1"
    source "$mainPath" "--source-only"

    configFileSetup "${@}" # all arguments passed
fi