#!/bin/bash

setupRequirements() {
    # Part One: Setup and Requirements

    rowLimiter
    echo "Checking now system setup and requirements"
    echo ""
    echo "To make sure this script can run sucessfully, please make sure the system requirements are fullfied"
    echo "https://github.com/IBM/spectrum-protect-sppmon/wiki/System-requirements"

    echo ""
    echo "> Checking yum"
    if ! [ -x "$(command -v yum)" ]
        then
            echo "ERROR: yum is not available. Please make sure it is installed!"
            abortInstallScript
        else
            echo "> Yum installed."
    fi

}

# Start if not used as source
if [ "${1}" != "--source-only" ]; then
    if (( $# != 1 )); then
        >&2 echo "Illegal number of parameters for the SetupRequirements file"
        abortInstallScript
    fi
    # prelude
    local mainPath="$1"
    source "$mainPath" "--source-only"


    setupRequirements "${@}" # all arguments passed
fi