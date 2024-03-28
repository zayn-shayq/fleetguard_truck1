from flask import Flask, render_template, jsonify, request
import requests
import subprocess

app = Flask(__name__)

# Global variable to keep track of the fleetguard.py process
process = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/shipment')
def get_shipment():
    response = requests.get('https://fleetguard.azurewebsites.net/api/driver/shipment/upcoming/6605a7187d1cac50c0409fe7')
    data = response.json()
    return jsonify(data)

@app.route('/start_shipment', methods=['POST'])
def start_shipment():
    global process
    if process is None:
        process = subprocess.Popen(['python', 'fleetguard.py'])
        return jsonify({"status": "started"})
    else:
        process.terminate()
        process = None
        return jsonify({"status": "stopped"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
