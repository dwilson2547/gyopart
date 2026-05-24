#!/bin/bash

mkdir -p .ssh
cp /etc/ssh/* .ssh/
git -c core.sshCommand='ssh -o StrictHostKeyChecking=no' clone git@gitlab.com:dwilson2547/parts-direct-dbms.git
pip3 install -r parts-direct-dbms/src/requirements.txt
python3 parts-direct-dbms/src/app.py