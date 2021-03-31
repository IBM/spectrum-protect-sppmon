#!/bin/bash

restartInflux() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters restartInflux"
        abortInstallScript
    fi

    echo " restarting influxdb service"
    checkReturn sudo systemctl restart influxdb

    echo "> Waiting 15 seconds for startup"
    sleep 15

    checkReturn systemctl is-active influxdb
    echo " restarted"
}

verifyConnection() {
    if (( $# != 2 )); then
        >&2 echo "Illegal number of parameters verifyConnection"
        abortInstallScript
    fi
    userName=$1 # param1: user to be logged in
    password=$2 # param2: password to be used


    echo "> verifying connection to InfluxDB"
    local connectionTestString="influx -host localhost -username $userName -password $password"
    if sslEnabled ; then # globalVar
        connectionTestString="$connectionTestString -ssl"
        if unsafeSsl ; then # globalVar
            connectionTestString="$connectionTestString -unsafeSsl"
        fi
    fi

    local connectionResponse=$(connectionTestString)
show databases
quit

    local influxVerifyCode=$(echo $connectionResponse | grep .*ERR.* >/dev/null; echo $?)
    if [[ $influxVerifyCode -ne 1 ]]; then
        # 0 means match -> This is faulty. 1 means no match = good

        echo "ERROR: The connection could not be established: $connectionResponse"
        abortInstallScript
    fi
}

influxSetup() {

    rowLimiter
    echo "Setup and installation of InfluxDB"

    echo "> configuring yum repository"
    sudo tee  /etc/yum.repos.d/influxdb.repo<<EOF
[influxdb]
name = InfluxDB Repository
baseurl = https://repos.influxdata.com/rhel/7/x86_64/stable/
enabled = 1
gpgcheck = 1
gpgkey = https://repos.influxdata.com/influxdb.key
EOF

    echo "> Installing database"
    checkReturn sudo yum install influxdb

    echo "> Starting InfluxDB service"
    checkReturn sudo systemctl enable --now influxdb

    echo "> Waiting 15 seconds for startup"
    sleep 15

    echo "> Verify InfluxDB service"
    checkReturn sudo systemctl is-active influxdb

    local influxAddress="$(ip route get 1 | sed -n 's/^.*src \([0-9.]*\) .*$/\1/p')"
    local influxPort="8086"

    echo "> Firewall configuration"
    checkReturn sudo firewall-cmd --add-port=${influxPort}/tcp --permanent
    checkReturn sudo firewall-cmd --reload

    local config_path="/etc/influxdb/influxdb.conf"
    local config_backup_path="${config_path}.orig"
    if [[ -f "${config_backup_path}" ]]; then
        echo "> Probably restarting the install script."
        echo "> Restoring original config file from backup"
        checkReturn sudo cp "${config_backup_path}" "${config_path}"

    echo "> Backuping default configuration into ${config_backup_path}"
    checkReturn sudo cp -n "${config_path}" "${config_backup_path}"

    # Access rights
    checkReturn sudo chown influxdb:influxdb /etc/influxdb/influxdb.conf -R

    echo "> editing config file part 1"
    if confirm "Do you want to report usage data to usage.influxdata.com?"
        then
            checkReturn sudo sed -i '"s/\#*\s*reporting-disabled\s*=.*/ reporting-disabled = false/"' "${config_path}"
        else
            checkReturn sudo sed -i '"s/\#*\s*reporting-disabled\s*=.*/ reporting-disabled = true/"' "${config_path}"
    fi

    # sed -i 's/search_string/replace_string/' filename
    # sed -i -r '/header3/,/pattern/ s|pattern|replacement|' filename

    # [meta] dir
    checkReturn sudo sed -ri '"/\[meta\]/,/dir\s*=.+/ s|\#*\s*dir\s*=.+| dir = \"/influxDB/meta\"|"' "${config_path}"

    # [data] dir
    checkReturn sudo sed -ri '"/\[data\]/,/dir\s*=.+/ s|\#*\s*dir\s*=.+| dir = \"/influxDB/data\"|"' "${config_path}"
    # [data] wal-dir
    checkReturn sudo sed -ri '"/\[data\]/,/wal-dir\s*=.+/ s|\#*\s*wal-dir\s*=.+| wal-dir = \"/influxDB/wal\"|"' "${config_path}"

    # [http] enabled = true
    checkReturn sudo sed -ri '"/\[http\]/,/enabled\s*=.+/ s|\#*\s*enabled\s*=.+| enabled = true|"' "${config_path}"
    # [http] log-enabled = true
    checkReturn sudo sed -ri '"/\[http\]/,/log-enabled\s*=.+/ s|\#*\s*log-enabled\s*=.+| log-enabled = true|"' "${config_path}"

    # [http] flux-enabled = true
    checkReturn sudo sed -ri '"/\[http\]/,/flux-enabled\s*=.+/ s|\#*\s*flux-enabled\s*=.+| flux-enabled = true|"' "${config_path}"
    # [http] flux-log-enabled = true
    checkReturn sudo sed -ri '"/\[http\]/,/flux-log-enabled\s*=.+/ s|\#*\s*flux-log-enabled\s*=.+| flux-log-enabled = true|"' "${config_path}"

    # [http] bind-address TODO test " vs ' (port variable)
    checkReturn sudo sed -ri "\"/\[http\]/,/bind-address\s*=.+/ s|\#*\s*bind-address\s*=.+| bind-address = \\\":${influxPort}\\\"|\"" "${config_path}"

    # DISABLE to allow user creation
    # [http] auth-enabled = false
    checkReturn sudo sed -ri '"/\[http\]/,/auth-enabled\s*=.+/ s|\#*\s*auth-enabled\s*=.+| auth-enabled = false|"' "${config_path}"
    # [http] https-enabled = false
    checkReturn sudo sed -ri '"/\[http\]/,/https-enabled\s*=.+/ s|\#*\s*https-enabled\s*=.+| https-enabled = false|"' "${config_path}"

    # restart influxdb
    restartInflux

    # Create user
    local userCreateReturnCode=1 # start value
    while [[ $userCreateReturnCode -ne 0 ]]; do # repeat until break, when it works

        readAuth # read all existing auths

        # Sets default to either pre-saved value or influxadmin
        if [[ -z $influxAdminName ]]; then
            local influxAdminName="influxAdmin"
        fi
        promptLimitedText "Please enter the desired InfluxDB admin name" influxAdminName "$influxAdminName"

        # sets default to presaved value if empty
        if [[ -z $influxAdminName ]]; then
            local influxAdminPassword
        fi
        promptLimitedText "Please enter the desired InfluxDB admin password" influxAdminPassword "$influxAdminPassword"

        local userCreateResult
        userCreateResult=$(curl -XPOST "http://${influxAddress}:${influxPort}/query" --data-urlencode "q=CREATE USER $influxAdminName WITH PASSWORD '$influxAdminPassword' WITH ALL PRIVILEGES")
        userCreateReturnCode=$(echo $userCreateResult | grep .*error.* >/dev/null; echo $?) # {"results":[{"statement_id":0}]}" or {"error":"..."}
        # 0 means match -> This is faulty. 1 means no match = good
        if [[ $userCreateReturnCode -ne 1 ]]
            then
                echo "Creation failed, please try again"
                echo "Result from influxDB: $userCreateResult"
            else
                saveAuth "influxAdminName" "$influxAdminName"
                saveAuth "influxAdminPassword" "$influxAdminPassword"
                saveAuth "influxPort" "${influxPort}"
                saveAuth "influxAddress" "${influxAddress}"
        fi

    done

    echo " > editing influxdb config file part 2"
    # [http] auth-enabled = true
    checkReturn sudo sed -ri '"/\[http\]/,/auth-enabled\s*=.+/ s|\#*\s*auth-enabled\s*=.+| auth-enabled = true|"' "${config_path}"
    # [http] pprof-auth-enabled = true
    checkReturn sudo sed -ri '"/\[http\]/,/pprof-enabled\s*=.+/ s|\#*\s*pprof-enabled\s*=.+| pprof-enabled = true|"' "${config_path}"
    # [http] ping-auth-enabled = true
    checkReturn sudo sed -ri '"/\[http\]/,/ping-auth-enabled\s*=.+/ s|\#*\s*ping-auth-enabled\s*=.+| ping-auth-enabled = true|"' "${config_path}"

    # ################# START OF HTTPS ##########################

    # saved later into file
    local sslEnabled=false
    local unsafeSsl=false

    if confirm "Do you want to enable HTTPS-communication with the influxdb? This is highly recommended!"; then
        # [http] https-enabled = true
        checkReturn sudo sed -ri '"/\[http\]/,/https-enabled\s*=.+/ s|\#*\s*https-enabled\s*=.+| https-enabled = true|"' "${config_path}"

        sslEnabled=true

        local httpsKeyPath
        local httpsCertPath

        if confirm "Do you want to create a self-signed certificate? Answer no to use existing one"; then

            unsafeSsl=true

            httpsKeyPath="/etc/ssl/influxdb-selfsigned.key"
            httpsCertPath="/etc/ssl/influxdb-selfsigned.crt"

            local keyCreateCommand="sudo openssl req -x509 -nodes -newkey rsa:4096 -keyout \"$httpsKeyPath\" -out \"$httpsCertPath\""
            local certDuration

            while true; do # repeat until valid symbol
                promptText "How long should if be valid in days? Leave empty for no limit" certDuration
                if ! [[ $certDuration =~ '^[0-9]+$' ]] || [[ -z $certDuration ]]; then
                    echo "You may only enter numbers or leave blank."
                else
                    break
                fi
            done

            # append duration of cert
            if [[ -n $certDuration ]]; then
                keyCreateCommand="$keyCreateCommand -days $certDuration"
            fi

            # Actually create it
            while true; do # repeat until created
                eval $keyCreateCommand
                if [[ $? -ne 0 ]]; then
                    if ! confirm "cert creation failed. Do you want to try again?"; then
                        abortInstallScript
                    fi
                else
                    break
                fi
            done
        else # Provide own cert

            local selfsignedString=""

            if confirm "Is your cert self-signed and InfluxDB should use the unsafe ssl flag?"; then
                selfsignedString="-selfsigned"
                unsafeSsl=true
            fi

            # Key
            while [[ -z $httpsKeyPath ]]; do
                promptText "Please enter the path to the https cert key" httpsKeyPath "/etc/ssl/influxdb${selfsignedString}.key"
                if [[ -z $httpsKeyPath ]]; then
                    echo "The path of the key must not be empty"
                fi
            done
            # Cert
            while [[ -z $httpsCertPath ]]; do
                promptText "Please enter the path to the https cert key" httpsCertPath "/etc/ssl/influxdb${selfsignedString}.cert"
                if [[ -z $httpsCertPath ]]; then
                    echo "The path of the cert must not be empty"
                fi
            done

        fi

        # Edit config file again
        # [http] https-certificate
        checkReturn sudo sed -ri "/\[http\]/,/https-certificate\s*=.+/ s|\#*\s*https-certificate\s*=.+| https-certificate = \"$httpsCertPath\"|" "${config_path}"
        # [http] https-private-key
        checkReturn sudo sed -ri "/\[http\]/,/https-private-key\s*=.+/ s|\#*\s*https-private-key\s*=.+| https-private-key = \"$httpsKeyPath\"|" "${config_path}"

    fi

    ###################### END OF HTTPS ######################

    saveAuth "sslEnabled" "$sslEnabled"
    saveAuth "unsafeSsl" "$unsafeSsl"

    # restart influxdb
    echo "restart influxdb service"
    restartInflux

    # Checking connection
    verifyConnection $influxAdminName $influxAdminPassword


    # Create Grafana Reader
    readAuth # read existing authentification

    # this should always be grafana reader
    local influxGrafanaReaderName="GrafanaReader"

    # sets default to presaved value if it exists
    if [[ -z $influxGrafanaReaderPassword ]]; then
        local influxGrafanaReaderPassword=""
    fi

    echo "Creating InfluxDB '$influxGrafanaReaderName' user"

    promptLimitedText "Please enter the desired InfluxDB GrafanaReader user password" influxGrafanaReaderPassword "$influxGrafanaReaderPassword"

    verifyConnection "$influxGrafanaReaderName" "$influxGrafanaReaderPassword"

    saveAuth "influxGrafanaReaderName" "$influxGrafanaReaderName"
    saveAuth "influxGrafanaReaderPassword" "$influxGrafanaReaderPassword"

    echo "Finished InfluxDB Setup"

}


# Start if not used as source
if [ "${1}" != "--source-only" ]; then
    if (( $# != 1 )); then
        >&2 echo "Illegal number of parameters for the influxSetup file"
        abortInstallScript
    fi

    # prelude
    local mainPath="$1"
    source "$mainPath" "--source-only"

    influxSetup "${@}" # all arguments passed
fi