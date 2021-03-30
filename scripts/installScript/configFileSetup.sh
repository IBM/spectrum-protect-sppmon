#!/bin/bash

configFileSetup() {

    rowLimiter
    echo "Creating and configuring the config files"

    if ! (confirm "Do you want to add a server config now?"); then
        echo "Continuing with the next Step. Finished config file setup"
        return 0
    else
        local nextServer=true
    fi

    local config_dir="$(dirname ${1})"
    config_dir=$(realpath ${config_dir}/../config_files)

    echo "> All configurations files are written into dir ${config_dir}"

    while ${nextServer}; do
        echo "> Adding a new config file"
        echo "> Gathering server informations"

        local serverName

        local serverNameSet=false
        while ! $serverNameSet ; do
            promptLimitedText "readable name of the SPP server (no spaces)?" serverName
            local current_config="${config_dir}/${servername}.conf"
            if [[ -e ${current_config} ]]; then
                if ! (confirm "Do you want to overwrite existing file ${current_config}?") ; then
                    echo "Please re-enter a different server name"
                else
                    echo "> Overwriting old config file"
                fi
            fi
        done
        echo "{" > ${current_config}
        echo "> Created new config file ${current_config}"

        local srv_address
        promptLimitedText "SPP server address" srv_address
        local srv_port
        promptLimitedText "SPP server port" srv_address "443"

        local spp_username
        promptLimitedText "SPP REST-API User (equal to login via website)" spp_username
        local spp_password
        promptLimitedText "SPP REST-API password (equal to login via website)" spp_password

    done






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