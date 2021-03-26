#!/bin/bash

# aborting the script with a restart message
abortInstallScript() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters abortInstallScript"
    fi

    echo "Aborting the SPPMon install script."
    echo "You may continue the script from the last saved point by restarting it."
    echo "Last saved point is: $continue_point."

    # exit with error code
    exit -1
}

saveState() { # param1: new continue_point #param2: name of next step
    if (( $# != 2 )); then
        >&2 echo "Illegal number of parameters saveState"
        abortInstallScript
    fi
    # global on purpose
    continue_point="$1"
    echo "$continue_point" > "$saveFile"

    local next_step="$2"

    rowLimiter
    echo "## Safepoint: You may abort the script now ##"
    if ! (confirm "Continue with $next_step?");
        then
            abortInstallScript
        else
            echo "continuing with $next_step"
    fi
}

# get path of current script
getPath() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters getPath"
        abortInstallScript
    fi
    #DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
    #echo $DIR
    #local DIR=$(dirname "$(readlink -f "$0")")
    #echo $DIR

    echo $(dirname "$(readlink -f "$0")")
}

saveAuth() { # topic is the describer
    if (( $# != 2 )); then
        >&2 echo "Illegal number of parameters saveAuth"
        abortInstallScript
    fi
    local topic=$1 # param1: topic
    local value=$2 # param2: value

    # save into global variable
    eval "\"$topic\"=\"$value\""

    echo "\"$topic\"=\"$value\"" >> "$passwordFile"

    echo "$topic saved in password file and exported as variable"
}

readAuth() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters readAuth"
        abortInstallScript
    fi
    if [[ -f "$passwordFile" ]]
        then
            set -a # now all variables are exported
            source "$passwordFile"
            set +a # Not anymore
    fi
}

restoreState() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters restoreState"
        abortInstallScript
    fi

    if [[ -f "$saveFile" ]]
        then # already executed
            continue_point=$(<"$saveFile")
            echo "Welcome to the SPPMon install guide. You last saved point was $continue_point."
            echo "WARNING: Restarting has unpredictable effects. No warranty for any functionality."
            echo ""
            if confirm "Do you want to continue without restarting? Abort by CTRL + C."
                then # no restart
                    echo "Continuing from last saved point"
                else # restart
                    echo "restarting install process"
                    continue_point='WELCOME'
                echo "$continue_point" > "$saveFile"
            fi
        else # First execution
            continue_point='WELCOME'
            echo "$continue_point" > "$saveFile"
    fi
}

removeGeneratedFiles() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters removeGeneratedFiles"
        abortInstallScript
    fi

    if [[ -f "$saveFile" ]]
        then
            rm "$saveFile"
    fi

    if [[ -f "$passwordFile" ]]
        then
            rm "$passwordFile"
    fi
}

main(){

    if [[ "${1}" == "--debug" ]]
        then
            removeGeneratedFiles
    fi

    restoreState
    readAuth

    # Part zero: Welcome
    if [[ $continue_point == "WELCOME" ]]
        then
            source "${subScripts}/welcome.sh" "$mainPath"
            # Savepoint and explanation inside of `welcome`
    fi

    # Sudo Check
    sudoCheck

    # Part 1: System Setup (incomplete?)
    if [[ $continue_point == "SYS_SETUP" ]]
        then
            source "${subScripts}/setupRequirements.sh" "$mainPath"
            saveState 'INFLUX_SETUP' 'InfluxDB installation and setup' # next point
    fi

    # Part 2: InfluxDB installation and setup
    if [[ $continue_point == "INFLUX_SETUP" ]]
        then
            source "${subScripts}/influxSetup.sh" "$mainPath"
            saveState 'GRAFANA_SETUP' 'Grafana installation'
    fi

    # Part 3: Grafana installation
    if [[ $continue_point == "GRAFANA_SETUP" ]]
        then
            source "${subScripts}/grafanaSetup.sh" "$mainPath"
            saveState 'PYTHON_SETUP' 'Python3 installation and packages'
    fi

    # Part 4: Python installation and packages
    if [[ $continue_point == "PYTHON_SETUP" ]]
        then
            source "${subScripts}/pythonSetup.sh" "$mainPath"
            saveState 'USER_MANGEMENT' 'User creation for SPP, vSnap and others'
    fi

}

# Start main if not used as source
if [ "${1}" != "--source-only" ]; then

    # prelude
    path=$(getPath)
    subScripts="${path}/installScript"
    mainPath="${path}/installer.sh"
    saveFile="${subScripts}/.savefile.txt"
    passwordFile="${path}/.passwords.txt"

    # Sources
    source "$subScripts/helper.sh" "--source-only"

    # handling of signals
    trap " abortInstallScript " INT QUIT HUP

    main "${@}" # all arguments passed
fi
