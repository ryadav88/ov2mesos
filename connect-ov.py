from hpOneView.oneview_client import OneViewClient
from hpOneView.exceptions import HPOneViewException

import json
import sys
import re
import logging
import os

ov_client = OneViewClient.from_environment_variables()
server_hw = ov_client.server_hardware.get_all()
# Iterate through each server and validate info in ES
for server in server_hw:
    # Update each ES record with data from Server H/W and keep track
    print("Name : %s Serial#: %s Model %s" %(server['name'],server['serialNumber'],server['shortModel']))
