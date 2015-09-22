#!/bin/sh
#
# Attach to a running Docker instance and create a TTY
#

if [ $# -lt 1 ]; then
    echo "Usage: ${0} <container id>"
    exit 1
fi

docker exec -ti ${1} script -q -c "/bin/bash" /dev/null
