#!/bin/bash

pythonSetup() {

    rowLimiter
    echo "Installation of Python and packages"

    echo "> Checking gcc install"
    gcc --version &>/dev/null
    if (( $? != 0 ))
        then
            echo "> Installing gcc"
            checkReturn sudo yum install gcc
        else
            echo "> gcc installed."
    fi

    echo "> Installing development libaries and packages"
    checkReturn sudo yum -y groupinstall "Development Tools"
    checkReturn sudo yum -y install openssl-devel bzip2-devel libffi-devel
    checkReturn sudo yum -y install wget

    echo "> Verifying the installed python version"
    local python_old_path=$(which python)
    local current_ver=$(python -V 2>&1)
    local required_ver="3.8.2
    "
    if [ "$(printf '%s\n' "$required_ver" "$current_ver" | sort -V | head -n1)" = "$required_ver" ]; then
        echo "> Compatible Python version installed ($current_ver > $required_ver)."
    else
        echo "> Installing compatible python version. Current install does not match requirements ($current_ver < $required_ver)"
        checkReturn mkdir -p /tmp/python392
        checkReturn cd /tmp/python392/
        checkReturn wget https://www.python.org/ftp/python/3.9.2/Python-3.9.2.tgz

        checkReturn cd /tmp/python392/
        checkReturn tar -xvf Python-3.9.2.tgz
        checkReturn cd /tmp/python392/Python-3.9.2
        checkReturn ./configure --enable-optimizations --prefix=/usr

        checkReturn sudo make altinstall

        current_ver=$(python -V 2>&1)
        if [ "$(printf '%s\n' "$required_ver" "$current_ver" | sort -V | head -n1)" = "$required_ver" ]; then
            echo "> Python install sucessfull."
        else
            echo "> Python install unsucessfull. Aborting"
            abortInstallScript
        fi

        echo "> Configuring alternative switch between old and new python version"
    fi

    echo "> Checking pip version"
    checkReturn  python3 -m pip install --upgrade pip

    echo "> Installing required packages"
    checkReturn pip install -r $mainPath/../python/requirements.txt

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