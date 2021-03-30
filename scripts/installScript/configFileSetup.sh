#!/bin/bash

configFileSetup() {

    rowLimiter
    echo "Creating and configuring the config files"

    local config_dir="$(dirname ${1})"
    config_dir=$(realpath ${config_dir}/../config_files)

    echo "> All configurations files are written into dir ${config_dir}"

    while true; do

        if ! (confirm "Do you want to add (another) new server config?"); then
            echo "Continuing with the next Step."
            break # stop outer loop
        fi

        echo "> Adding a new config file"
        local serverName=""

        while [[ -z ${serverName} ]] ; do
            promptLimitedText "Please enter the desired readable name of the SPP server (no spaces)?" serverName
            local current_config="${config_dir}/${serverName}.conf"
            if [[ -e ${current_config} ]]; then
                if ! (confirm "Do you want to overwrite existing file ${current_config}?") ; then
                    echo "Please re-enter a different server name"
                    serverName=""
                else
                    echo "> Overwriting old config file"
                fi
            fi
        done
        echo "{" > ${current_config}
        echo "> Created new config file ${current_config}"

        echo "> Gathering server informations"

        local srv_address
        promptLimitedText "Please enter the desired SPP server address" srv_address
        local srv_port
        promptLimitedText "Please enter the desired SPP server port" srv_port "443"

        local spp_username
        promptLimitedText "Please enter the desired SPP REST-API User (equal to login via website)" spp_username
        local spp_password
        promptLimitedText "Please enter the desired SPP REST-API password (equal to login via website)" spp_password

        local spp_retention=""
        while [[ -z ${spp_retention} ]]; do
            promptLimitedText "How long are the JobLogs saved within the Server? (Format: 48h, 60d, 2w)" spp_retention "60d"
            if ! [[ "${spp_retention}" =~ ^[0-9]+[hdw]$ ]]; then
                echo "The format is incorrect. Please try again."
                spp_retention=""
            fi
        done

        checkReturn tee -a ${current_config} &>/dev/null <<EOF
    "sppServer": {
                    "username":     "${spp_username}",
                    "password":     "${spp_password}",
                    "srv_address":  "${srv_address}",
                    "srv_port":     ${srv_port},
                    "jobLog_rentation": "${spp_retention}"
  },
EOF

    echo "> inserting influxDB informations"
    readAuth
    local requiredAuth=( "influxAdminName" "influxAdminPassword" "sslEnabled" "unsafeSsl" "influxAddress" "influxPort" )
    for auth in "${requiredAuth[@]}"; do
        if [[ -z $(eval "\$${auth}") ]]; then
            promptLimitedText "> Information for '${auth}' is missing. Please enter it." ${auth}
            saveAuth "$auth" $(eval "\$${auth}")
        fi
    done

    checkReturn tee -a ${current_config} &>/dev/null <<EOF
    "influxDB": {
                    "username":     "${influxAdminName}",
                    "password":     "${influxAdminPassword}",
                    "ssl":          ${sslEnabled},
                    "verify_ssl":   ${unsafeSsl},
                    "srv_port":     ${influxPort},
                    "srv_address":  "${influxAddress}",
                    "dbName":       "$spp_name"
  },
EOF




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