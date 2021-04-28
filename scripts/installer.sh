#!/bin/bash

# aborting the script with a restart message
abortInstallScript() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters abortInstallScript"
    fi

    rowLimiter

    echo "Aborting the SPPMon install script."
    echo "You may continue the script from the last saved point by restarting it."
    echo "Last saved point is: $continue_point."

    rowLimiter

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
    set -a # now all variables are exported
    eval "$topic=\"${value}\""
    set +a # Not anymore

    echo "$topic=\"${value}\"" >> "$passwordFile"
}

readAuth() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters readAuth"
        abortInstallScript
    fi
    if [[ -r "$passwordFile" ]]; then
        set -a # now all variables are exported
        source "${passwordFile}"
        set +a # Not anymore
    fi
}

restoreState() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters restoreState"
        abortInstallScript
    fi

    if [[ -f "$saveFile" ]]; then # already executed

            rowLimiter

            continue_point=$(<"$saveFile")
            echo "Welcome to the SPPMon install guide. You last saved point was $continue_point."
            echo "WARNING: Restarting has unpredictable effects. No warranty for any functionality."
            echo ""
            if confirm "Do you want to continue without restarting? Abort by CTRL + C."
                then # no restart
                    echo "Continuing from last saved point"
                else # restart
                    echo "restarting install process"
                    continue_point='0_WELCOME'
                echo "$continue_point" > "$saveFile"
            fi
        else # First execution
            continue_point='0_WELCOME'
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
    # Sudo Check
    sudoCheck

    # Part zero: Welcome
    if [[ $continue_point == "WELCOME" ]]
        then
            source "${subScripts}/welcome.sh" "$mainPath"
            # Savepoint and explanation inside of `welcome`
    fi

    # Part 1: System Setup (incomplete?)
    if [[ $continue_point == "SYS_SETUP" ]]
        then
            source "${subScripts}/setupRequirements.sh" "$mainPath"
            saveState '4_PYTHON_SETUP' 'Python3 installation and packages'
    fi

    # Part 4: Python installation and packages
    if [[ $continue_point == "PYTHON_SETUP" ]]
        then
            source "${subScripts}/pythonSetup.sh" "$mainPath"

            saveState 'INFLUX_SETUP' 'InfluxDB installation and setup'
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
            saveState 'USER_MANGEMENT' 'User creation for SPP, vSnap and others'
    fi

    # Part 5: User management for SPP server and components
    if [[ $continue_point == "USER_MANGEMENT" ]]
        then
            source "${subScripts}/userManagement.sh" "$mainPath"
            saveState 'CONFIG_FILE' 'creation of the monitoring file for each SPP-Server'
    fi

    # Part 6: User management for SPP server and components
    if [[ $continue_point == "CONFIG_FILE" ]]
        then
            source "${subScripts}/configFileSetup.sh" "$mainPath"
            saveState 'CRONTAB' 'Crontab configuration for automatic execution'
    fi

    # Part 7: User management for SPP server and components
    if [[ $continue_point == "CRONTAB" ]]
        then
            source "${subScripts}/configFileSetup.sh" "$mainPath"
            saveState 'GRAFANA_DASHBOARDS' 'Creation and configuration of the grafana dashboards'
    fi

    # Part 8: Grafana dashboards
    if [[ $continue_point == "GRAFANA_DASHBOARDS" ]]
        then
            source "${subScripts}/configFileSetup.sh" "$mainPath"
            saveState 'FINISHED' 'Creation and configuration of the grafana dashboards' #TODO
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
