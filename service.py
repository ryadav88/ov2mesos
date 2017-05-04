#!flask/bin/python
# -*- coding: utf-8 -*-
###
# (C) Copyright (2012-2017) Hewlett Packard Enterprise Development LP
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
###
from flask import Flask, jsonify, abort, make_response, request
from hpOneView.oneview_client import OneViewClient
from hpOneView.exceptions import HPOneViewException
import os
import datetime
import json

app = Flask(__name__)
ov_client = None

# Keep a track of Server Profile Tasks
server_profile_tasks=[]

# Service running
@app.route('/', methods=['GET'])
def get_alive():
    return make_response(jsonify({'status': 'Alive', 'message' : 'ov2mesos - Alive and kicking'}))

# Error handler for Flask
@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'Error': 'URI Not found'}),404)

# Implement the REST API
@app.route('/ov2mesos/capacity', methods=['GET'])
def get_capacity():
    spt_name = os.environ['ONEVIEW_UNIVERSE_SPT']
    spt_obj = ov_client.server_profile_templates.get_by_name(spt_name)
    server_hw = ov_client.server_hardware.get_by('serverHardwareTypeUri', spt_obj['serverHardwareTypeUri'])
    server_list = []
    for server in server_hw:
        #check if server has a server_profile URI
        if server['serverProfileUri'] == None:
            record = {
                'name' : server['name'],
                'model': server['model']
            }
            server_list.append(record)
            # pre-empt capacity by shutting down servers.
            '''
            try:
                ov_client.server_hardware.update_power_state(dict(powerState="Off",powerControl="MomentaryPress"),server['uri'],timeout=1)
            except HPOneViewException as e:
                print (e.msg)
            '''

    return make_response(jsonify({'available_count': len(server_list),'available': server_list}))

@app.route('/ov2mesos/addnode', methods=['POST'])
def post_addnode():
    # expecting a json with the following format
    # { 'count' : int }
    if not request.json or not 'count' in request.json:
        abort(400)

    profile_count = int(request.json['count'])
    # create a SP from variables that are being passed in
    # Return the task ID or store the task ID
    spt_name = os.environ['ONEVIEW_UNIVERSE_SPT']
    osdp_name = os.environ['ONEVIEW_UNIVERSE_OSDP']

    for index in range(profile_count):
        # Format name of SP = SPT-DATE-TIME-microsecond
        now = datetime.datetime.now()
        sp_name = spt_name + '-' + now.strftime('%Y%m%d') + '-' + now.strftime('%H%M%S') + '-' + str(now.microsecond)

        spt_obj = ov_client.server_profile_templates.get_by_name(spt_name)

        resp = get_capacity()
        available_server_list = json.loads(resp.response[0])
        if available_server_list['available_count'] > 0:
            serverHwName = available_server_list['available'][0]['name']
            serverHW = ov_client.server_hardware.get_by('name',serverHwName)

            # Assign a server profile template to a server.
            server_profile = dict(name=sp_name,
                 serverProfileTemplateUri=spt_obj['uri'],
                 serverHardwareUri=serverHW[0]['uri'],
                 enclosureGroupUri=serverHW[0]['serverGroupUri'],
                 serverHardwareTypeUri=serverHW[0]['serverHardwareTypeUri'])

            # Power off the server if the server has not powered off
            configuration = {
                "powerState": "Off",
                "powerControl": "MomentaryPress"
            }
            server_hardware_id = serverHW[0]['uuid']
            server_power = ov_client.server_hardware.update_power_state(configuration, server_hardware_id)

            # Verify if Server_power is off before firing off a profile.
            task_uri = None
            try:
                task_uri = ov_client.server_profiles.create(server_profile,timeout=2)
            except HPOneViewException as e:
                print (e.msg)

            task_list = ov_client.tasks.get_all(filter=["associatedResource.resourceName='" + sp_name + "'",
                                                        "associatedResource.resourceCategory='server-profiles'"])

            # check for task to a server profile
            server_profile_tasks.append(task_list)
        else:
            return make_response(jsonify({'status': 'No capacity available', 'requested':profile_count}))

    return_list = []
    for server in server_profile_tasks:
        return_obj = dict(status=server[0]['taskStatus'],percentComplete=server[0]['percentComplete'],serverProfileUri=server[0]['associatedResource']['resourceUri'])
        return_list.append(return_obj)

    return make_response(jsonify({'status': return_list,'requested':len(return_list)}))

@app.route('/ov2mesos/status', methods=['GET'])
def get_profile_status():
    # create a SP from variables that are being passed in
    # Return the task ID or store the task ID
    length = len(server_profile_tasks)

    status_list = []

    if length >= 1:
        # process all tasks and return current status
        for server_profile in server_profile_tasks:
            task_status = ov_client.tasks.get(server_profile[0]['uri'])
            status_dict = dict(status = task_status['taskStatus'],percentComplete=task_status['percentComplete'],
                               serverProfileUri=task_status['associatedResource']['resourceUri'])
            status_list.append(status_dict)
            # remove completed tasks from list as its not relevant anymore
            if task_status['stateReason'] == 'Completed':
                server_profile_tasks.remove(server_profile)

    return make_response(jsonify({'Message':'Count:0 implies all tasks are complete','Count':len(server_profile_tasks),'Profile status':status_list}))


@app.route('/ov2mesos/removenode', methods=['POST'])
def post_removenode():
    # create a SP from variables that are being passed in
    # Return the task ID or store the task ID
    # Get current time
    now = datetime.datetime.now()
    if not request.json or not 'count' in request.json:
        abort(400)

    profile_count = int(request.json['count'])
    spt_name = os.environ['ONEVIEW_UNIVERSE_SPT']
    # get a list of matching profiles
    profile_list = ov_client.server_profiles.get_all(filter="'name' matches '" + spt_name + "%'")

    # create list of profile names to delete
    delete_list = []
    for profile in profile_list:
        delete_list.append(dict(name=profile['name'],uri=profile['uri'],hwuri=profile['serverHardwareUri']))
    sorted_delete = sorted(delete_list, key=lambda k: k['name'])

    deleted = []

    for index in range(profile_count):
        # iterate through the number of servers to remove
        print ("deleting profile : %s"%sorted_delete[index]['name'])
        try:
            ov_client.server_hardware.update_power_state(dict(powerState="Off", powerControl="MomentaryPress"),
                                                         sorted_delete[index]['hwuri'])
        except HPOneViewException as e:
            print(e.msg)
        try:
            ov_client.server_profiles.delete(sorted_delete[index]['uri'])
        except HPOneViewException as e:
            print(e.msg)
        deleted.append(sorted_delete[index]['name'])

    return make_response(jsonify({'status':'Deleting','Requested':profile_count,'profiles':deleted}))


if __name__ == '__main__':
    # Connect to OneView
    print ("ov2mesos service started")
    ov_client = OneViewClient.from_environment_variables()
    #ov_client = OneViewClient(config)
    app.run(debug=True)
