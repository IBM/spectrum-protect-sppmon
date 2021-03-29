#!/bin/bash



# ########### MISC / FUNCTIONS #######################

checkReturn() {
    eval "${@}"
    if [[ "$?" -ne 0 ]]
        then
            echo "ERROR when executing command: \"$@\""
            abortInstallScript
    fi
}

sudoCheck() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters sudoCheck"
        abortInstallScript
    fi

    echo "Checking if sudo privileges are available."
    if [[ "$EUID" = 0 ]]; then
        echo "(1) already root"
    else
        sudo -k # make sure to ask for password on next sudo
        if sudo true; then
            echo "(2) correct password"
        else
            echo "(3) wrong password"
            abortInstallScript
        fi
    fi
}

# ########### PRINTING #######################

# print row of # signs to the console
rowLimiter() {
    if (( $# != 0 )); then
        >&2 echo "Illegal number of parameters rowLimiter"
        abortInstallScript
    fi

    printf '\n'
    printf '#%.0s' $(seq 1 $(tput cols)) && printf '\n'
    printf '\n'
}

# ############ USER PROMPTS ###################

# prompt for a confirm with message, returning true or false
confirm() { # param1:message
    if (( $# != 1 )); then
        >&2 echo "Illegal number of parameters confirm"
        abortInstallScript
    fi

    local message="$1"
    local confirmInput

    read -r -s -p"$1 (Yes/no) [Yes]" confirmInput
    echo ""
    case "$confirmInput" in
        [yY][eE][sS] | [yY] | "" )
            echo 'Yes'
            return 0
            ;;
        * )
            echo 'No'
            return 1
            ;;
    esac
}

promtText() {
    if (( $# != 2 && $# != 3 )); then
        >&2 echo "Illegal number of parameters promtText"
        abortInstallScript
    fi

    local message="$1" # param1:message
    local __resultVal=$2 # param2: result
    local defaultValue # OPTIONAL param3: default val

    local promtTextInput

    if [ -n ${3+x} ] # evaluates to nothing if not set, form: if [ -z {$var+x} ]; then unset; else set; fi
        then    # default set
            defaultValue="$3"
            message="$message [$defaultValue]"
        else # default not given
            defaultValue=""
    fi
    while true ; do
        read -r -p"$message: " promtTextInput
        echo ""
        promtTextInput="${promtTextInput:-$defaultValue}" # substitues if unset or null
        # form: ${parameter:-word}

        if confirm "Is \"$promtTextInput\" the correct input?"; then
                break
        fi

        eval $__resultVal="'$promtTextInput'"
    done
}


promptUserCred() {
    if (( $# != 2 && $# != 3 )); then
        >&2 echo "Illegal number of parameters promptUserCred"
        abortInstallScript
    fi

    local description="$1" # param1: description in text
    local __resultVal=$2 # param2: result
    # OPTIONAL param3: default val

    local prohibitedSymbols="\" '"
    local promptUserCredInput
    local symbCheck

    while [-z $promptUserCredInput ]; do
        if [ -n ${3+x} ]; then # evaluates to nothing if not set, form: if [ -z {$var+x} ]; then unset; else set; fi
            promtText "Please enter the desired $description" promptUserCredInput $3
        else # default not given
            promtText "Please enter the desired $description" promptUserCredInput
        fi

        if [ -z $promptUserCredInput ]; then
            echo "No empy value is allowed, please try again."
        else
            symbCheck=$(echo "$promptUserCredInput" | grep "[$prohibitedSymbols]" >/dev/null; echo $?)
            # 0 means match, which is bad. 1 = all good
            if [[ $symbCheck -ne 1 ]]; then
                echo "The $description must not contain any of the following symbols: $prohibitedSymbols"
                promptUserCredInput=""
            fi
        fi
    done

    eval $__resultVal="'$promptUserCredInput'"
}


# ######### STARTUP ##############

if [ "${1}" != "--source-only" ]; then
    if (( $# != 1 )); then
        >&2 echo "Illegal number of parameters for the helper file"
        abortInstallScript
    fi

    # prelude
    local mainPath="$1"
    source "$mainPath" "--source-only"

    # STARTFUNCTION "${@}" # all arguments passed
fi