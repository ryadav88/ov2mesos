#!flask/bin/python
from flask import Flask, jsonify, abort, make_response
from hpOneView.oneview_client import OneViewClient

app = Flask(__name__)
ov_client = None

# Keep a track of Server Profile Tasks
server_profile_tasks=[]

# Service running
@app.route('/', methods=['GET'])
def get_alive():
    return jsonify({'status': 'Alive', 'message' : 'ov2mesos - Alive and kicking'})

# Error handler for Flask
@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'Error': 'URI Not found'}),404)

if __name__ == '__main__':
    app.run(debug=True)
