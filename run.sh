#!/bin/sh
#
# Launch a Calvin instance
#

echo == Launching Calvin ==
docker run -p 8000/tcp -p 5000/tcp -p 5001/tcp -dti calvin:latest
