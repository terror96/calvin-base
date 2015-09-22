############################################################
# Dockerfile to build Calvin images
# Based on Ubuntu:14.04
#
# VERSION 1.0
############################################################

FROM ubuntu:14.04
MAINTAINER Tero Kauppinen, tero.kauppinen@ericsson.com

# Update the repository sources list
RUN apt-get -o Acquire::ForceIPv4=true update

################## BEGIN INSTALLATION ######################

# Install packages
RUN apt-get -o Acquire::ForceIPv4=true install -y python wget python-dev screen

# Copy files
COPY . /var/tmp/calvin
RUN mv /var/tmp/calvin/setup.sh /usr/local/bin/

# Install Calvin
RUN wget https://bootstrap.pypa.io/get-pip.py -O /root/get-pip.py && python /root/get-pip.py
RUN cd /var/tmp/calvin && python setup.py install

# Ports to expose
EXPOSE 8000
EXPOSE 5001
EXPOSE 5000

# Entrypoint
ENTRYPOINT /usr/local/bin/setup.sh
