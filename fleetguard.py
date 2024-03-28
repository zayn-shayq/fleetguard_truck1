import cv2
import smbus
import time
import math
import serial
import pynmea2
from datetime import datetime
import os
from azure.storage.blob import BlobServiceClient
from pymongo import MongoClient
import re
from flask import Flask, render_template, jsonify, request
import requests
import subprocess


# Azure Blob Storage and MongoDB setup
CONNECTION_STRING = 'DefaultEndpointsProtocol=https;AccountName=crimescene;AccountKey=IRI+NPBsx1esOBfDeaKcrRsOHHlpgKuS2RwURVRFPVpv+NeUpuZEMuIV6sPkDh5KQ4gOSawY9hC4+AStbhinCA==;EndpointSuffix=core.windows.net'
CONTAINER_NAME = "post"
MONGO_CONNECTION_STRING = 'mongodb+srv://fyp:fyp@fyp.h8p1vij.mongodb.net/'
DATABASE_NAME = 'test'
COLLECTION_NAME = 'pidatas'

# Initialize Azure Blob Service Client
blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)

# Initialize MongoDB Client
mongo_client = MongoClient(MONGO_CONNECTION_STRING)
db = mongo_client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

# MPU6050 setup
bus = smbus.SMBus(1)  # Assuming using I2C bus 1
DEVICE_ADDRESS = 0x68  # MPU6050 device address

# Define timestamp variable
timestamp = None

def MPU_Init():
    bus.write_byte_data(DEVICE_ADDRESS, 0x6B, 1)  # Wake the MPU6050 up as it starts in sleep mode
    bus.write_byte_data(DEVICE_ADDRESS, 0x1B, 0)  # Set gyro full scale range
    bus.write_byte_data(DEVICE_ADDRESS, 0x1C, 0)  # Set accelerometer full scale range

def read_raw_data(addr):
    high = bus.read_byte_data(DEVICE_ADDRESS, addr)
    low = bus.read_byte_data(DEVICE_ADDRESS, addr+1)
    value = ((high << 8) | low)
    if value > 32768:
        value -= 65536
    return value

def read_sensor_data():
    MPU_Init()
    acc_x = read_raw_data(0x3B)
    acc_y = read_raw_data(0x3D)
    acc_z = read_raw_data(0x3F)
    temp = read_raw_data(0x41)
    actual_temp = (temp / 340.0) + 36.53  # Temperature in Celsius
    actual_temp = round(actual_temp, 2)  # Rounding off temperature
    Ax = acc_x / 16384.0
    Ay = acc_y / 16384.0
    Az = acc_z / 16384.0
    acceleration = math.sqrt(Ax**2 + Ay**2 + Az**2) * 9.81  # Acceleration in m/s^2
    print(actual_temp, acceleration)
    return actual_temp, acceleration

def get_gps_data():
    port = "/dev/ttyAMA0"
    try:
        ser = serial.Serial(port, baudrate=9600, timeout=0.5)
        time.sleep(2)
        for attempt in range(10):  # Try to read up to 10 lines to find a valid $GPRMC sentence
            newdata = ser.readline().decode('unicode_escape').strip()
            if newdata.startswith("$GPRMC"):
                newmsg = pynmea2.parse(newdata)
                if newmsg.latitude != 0.0 and newmsg.longitude != 0.0:
                    print(f"GPS Data: {newmsg.latitude}, {newmsg.longitude}")
                    return newmsg.latitude, newmsg.longitude
                else:
                    print("Waiting for valid GPS fix...")
            else:
                print(f"Received different GPS data: {newdata}")
    except Exception as e:
        print(f"Error reading GPS data: {e}")
    return None, None


def capture_and_resize_image():
    global timestamp  # Declare timestamp as global
    cam = cv2.VideoCapture(0)
    time.sleep(3)  # Warm-up time for the camera
    ret, frame = cam.read()
    cam.release()
    if ret:
        resized_image = cv2.resize(frame, (720, 480))  # Resize for consistency
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = f"{timestamp}.jpg"
        cv2.imwrite(image_path, resized_image)
        return image_path
    return None

def sanitize_blob_name(name):
    parts = name.split(".")
    sanitized_filename = re.sub(r'[^a-zA-Z0-9-_.]', '_', parts[0])
    sanitized_name = f"{sanitized_filename}.{parts[-1]}" if len(parts) > 1 else sanitized_filename
    return sanitized_name[:1024]

def upload_image_to_azure(file_path):
    blob_name = sanitize_blob_name(os.path.basename(file_path))
    blob_client = container_client.get_blob_client(blob_name)
    with open(file_path, "rb") as data:
        blob_client.upload_blob(data)
    os.remove(file_path)  # Remove the file once uploaded
    return blob_client.url


def get_shipmentID():
    try:
        response = requests.get('https://fleetguard.azurewebsites.net/api/driver/shipment/start/6605c894175a3ee13ed6f25a')
        data = response.json()
        print(data)
        shipmentID = data.get("shipmentID", "")
        print(shipmentID)
        return shipmentID
    except Exception as e:
        print(f"Failed to get shipmentID: {e}")
        return ""


while True:
    
    # Capture and process image
    image_file = capture_and_resize_image()
    image_url = f"{timestamp}.jpg"  # Use timestamp variable
    if image_file:
        image_url = upload_image_to_azure(image_file)
    

    # Read sensor data
    temperature, acceleration = read_sensor_data()
    
    # Get GPS data
    lat, lng = get_gps_data()

    
    shipmentID = get_shipmentID()
    #get_shipmentID()
    # Combine data
    combined_data = {
        "shipmentID": shipmentID,
        "timestamp": datetime.now(),
        "image_url": image_url,
        "temperature": temperature,
        "acceleration": acceleration,
        "latitude": lat,
        "longitude": lng
    }

    print(f"Data saved: {combined_data}")

    
    # Save data to MongoDB
    collection.insert_one(combined_data)

    time.sleep(5)  # Sleep for 5 seconds before the next read
