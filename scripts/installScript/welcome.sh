#!/bin/bash

welcome() {
    # Welcome Message
    rowLimiter

    echo "Welcome to the Spectrum-Protect-Plus Monitoring install wizard!"
    echo "This script will guide you through the install process of SPPMon."
    echo ""
    echo "If you have any feature requests or want to report bugs, please refer to our github page."
    echo "https://github.com/IBM/spectrum-protect-sppmon"
    echo "If you require any assistance with installing, please refer to our wiki page or open an issue to allow us to improve this process."
    echo "https://github.com/IBM/spectrum-protect-sppmon/wiki"

    rowLimiter

    echo "IMPORTANT: You may stop at savepoint and continue later."
    echo "WARNING: Do not exit inbetween savepoints!"
    echo "Note: You may use the [default] case by just hitting enter in any following promts"
    if ! (confirm "Start install script?");
        then
            echo "Aborting install script. Nothing has been changed yet."
            exit -1
        else
            echo ""
            echo "Starting install script for sppmon."
            echo ""
            continue_point='1_SYS_SETUP'
            echo "$continue_point" > $saveFile
    fi
}

# Start if not used as source
if [ "${1}" != "--source-only" ]; then
    if (( $# != 1 )); then
        >&2 echo "Illegal number of parameters for the welcome file"
        abortInstallScript
    fi
    # prelude
    local mainPath="$1"
    source "$mainPath" "--source-only"

    welcome "${@}" # all arguments passed
fi