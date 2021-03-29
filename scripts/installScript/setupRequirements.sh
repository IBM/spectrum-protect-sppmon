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
    echo "> Logging System information"
    echo -e "-------------------------------System Information----------------------------"
    echo -e "Hostname:\t\t"`hostname`
    echo -e "uptime:\t\t\t"`uptime | awk '{print $3,$4}' | sed 's/,//'`
    echo -e "Manufacturer:\t\t"`cat /sys/class/dmi/id/chassis_vendor`
    echo -e "Product Name:\t\t"`cat /sys/class/dmi/id/product_name`
    echo -e "Version:\t\t"`cat /sys/class/dmi/id/product_version`
    echo -e "Serial Number:\t\t"`cat /sys/class/dmi/id/product_serial`
    echo -e "Machine Type:\t\t"`vserver=$(lscpu | grep Hypervisor | wc -l); if [ $vserver -gt 0 ]; then echo "VM"; else echo "Physical"; fi `
    echo -e "Operating System:\t"`hostnamectl | grep "Operating System" | cut -d ' ' -f5-`
    echo -e "Kernel:\t\t\t"`uname -r`
    echo -e "Architecture:\t\t"`arch`
    echo -e "Processor Name:\t\t"`awk -F':' '/^model name/ {print $2}' /proc/cpuinfo | uniq | sed -e 's/^[ \t]*//'`
    echo -e "Active User:\t\t"`w | cut -d ' ' -f1 | grep -v USER | xargs -n1`
    echo -e "System Main IP:\t\t"`hostname -I`
    echo -e "----------------------------------Disk--------------------------------------"
    df -Ph
    echo -e "-------------------------------Package Updates-------------------------------"
    yum updateinfo summary | grep 'Security|Bugfix|Enhancement'
    echo ""
    echo "> finished logging."
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