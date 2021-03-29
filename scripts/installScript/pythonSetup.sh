#!/bin/bash

pythonSetup() {

    rowLimiter
    echo "Installation of Python and packages"

    echo "> Verifying the installed python version"
    python_old_path=$(which python)
    python_old_version=$(python -V 2>&1)


    echo "Finished Python installation Setup"

}

# Start if not used as source
if [ "${1}" != "--source-only" ]; then
    if (( $# != 1 )); then
        >&2 echo "Illegal number of parameters for the pythonSetup file"
        abortInstallScript
    fi

    # prelude
    local mainPath="$1"
    source "$mainPath" "--source-only"

    pythonSetup "${@}" # all arguments passed
fi