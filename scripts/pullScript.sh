#!/bin/bash

path=$(dirname "$(readlink -f "$0")")
cd $path

git fetch
git reset --hard origin/install_script
chmod +x "./installer.sh"
chmod +x "./pullScript.sh"
