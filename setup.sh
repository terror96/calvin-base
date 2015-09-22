#!/bin/sh

# Get the IP address
IP=`ifconfig eth0 | grep inet | grep -v inet6 | awk '{print $2}' | cut -d ':' -f2`


# Launch Calvin services in a screen session
NL=`echo '\015'`
screen -d -m -S Calvin -t CSRUNTIME
screen -S Calvin -p CSRUNTIME -X stuff "csruntime --host ${IP} --controlport 5001 --port 5000 --keep-alive ${NL}"
screen -S Calvin -X screen -t CSWEB
screen -S Calvin -p CSWEB -X stuff "csweb -a ${IP} ${NL}"

# Run top
top -d 60
