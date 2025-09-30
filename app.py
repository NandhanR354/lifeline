# app.py
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_pymongo import PyMongo
from bson import ObjectId
from datetime import datetime
import json
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24)

# MongoDB configuration
app.config["MONGO_URI"] = "mongodb://localhost:27017/patient_system"
mongo = PyMongo(app)

# Helper to convert ObjectId to string in JSON responses
class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)

app.json_encoder = JSONEncoder

# Routes
@app.route('/')
def index():
    if 'patient_id' not in session:
        return redirect(url_for('login'))
    
    patient = mongo.db.patients.find_one({"_id": ObjectId(session['patient_id'])})
    return render_template('index.html', patient=patient)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        patient = mongo.db.patients.find_one({"username": username})
        if patient and check_password_hash(patient['password'], password):
            session['patient_id'] = str(patient['_id'])
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid credentials")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('patient_id', None)
    return redirect(url_for('login'))

# Module 1: Patient Communication System
@app.route('/chat')
def chat():
    if 'patient_id' not in session:
        return redirect(url_for('login'))
    
    patient = mongo.db.patients.find_one({"_id": ObjectId(session['patient_id'])})
    conversations = mongo.db.conversations.find({
        "participants": session['patient_id']
    })
    
    return render_template('chat.html', patient=patient, conversations=list(conversations))

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    if 'patient_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    conversations = mongo.db.conversations.find({
        "participants": session['patient_id']
    })
    
    result = []
    for conv in conversations:
        # Get last message
        last_message = mongo.db.messages.find_one(
            {"conversation_id": str(conv['_id'])},
            sort=[("timestamp", -1)]
        )
        
        # Get participant names
        participants = []
        for p_id in conv['participants']:
            if p_id != session['patient_id']:
                user = mongo.db.patients.find_one({"_id": ObjectId(p_id)})
                if user:
                    participants.append(user['name'])
        
        result.append({
            "id": str(conv['_id']),
            "title": ", ".join(participants),
            "last_message": last_message['message'] if last_message else "No messages yet",
            "timestamp": last_message['timestamp'] if last_message else conv['created_at']
        })
    
    return jsonify(result)

@app.route('/api/conversations/<conversation_id>/messages', methods=['GET'])
def get_messages(conversation_id):
    if 'patient_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    messages = mongo.db.messages.find({
        "conversation_id": conversation_id
    }).sort("timestamp", 1)
    
    result = []
    for msg in messages:
        sender = mongo.db.patients.find_one({"_id": ObjectId(msg['sender_id'])})
        result.append({
            "id": str(msg['_id']),
            "sender": sender['name'] if sender else "Unknown",
            "message": msg['message'],
            "timestamp": msg['timestamp'],
            "is_own": msg['sender_id'] == session['patient_id']
        })
    
    return jsonify(result)

@app.route('/api/messages', methods=['POST'])
def send_message():
    if 'patient_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.json
    conversation_id = data.get('conversation_id')
    message = data.get('message')
    
    if not conversation_id or not message:
        return jsonify({"error": "Missing required fields"}), 400
    
    # Create message
    new_message = {
        "conversation_id": conversation_id,
        "sender_id": session['patient_id'],
        "message": message,
        "timestamp": datetime.utcnow()
    }
    
    mongo.db.messages.insert_one(new_message)
    
    return jsonify({"status": "success", "message": "Message sent"})

@app.route('/api/help-request', methods=['POST'])
def submit_help_request():
    if 'patient_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.json
    priority = data.get('priority')
    category = data.get('category')
    description = data.get('description')
    
    if not priority or not category or not description:
        return jsonify({"error": "Missing required fields"}), 400
    
    # Create help request
    new_request = {
        "patient_id": session['patient_id'],
        "priority": priority,
        "category": category,
        "description": description,
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    
    mongo.db.help_requests.insert_one(new_request)
    
    return jsonify({"status": "success", "message": "Help request submitted"})

# Module 2: Mental Health Monitoring
@app.route('/mood-checkin')
def mood_checkin():
    if 'patient_id' not in session:
        return redirect(url_for('login'))
    
    patient = mongo.db.patients.find_one({"_id": ObjectId(session['patient_id'])})
    return render_template('mood_checkin.html', patient=patient)

@app.route('/api/mood', methods=['POST'])
def submit_mood():
    if 'patient_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.json
    mood = data.get('mood')
    notes = data.get('notes', '')
    
    if not mood:
        return jsonify({"error": "Mood is required"}), 400
    
    # Create mood check-in
    new_mood = {
        "patient_id": session['patient_id'],
        "mood": mood,
        "notes": notes,
        "timestamp": datetime.utcnow()
    }
    
    mongo.db.mood_checkins.insert_one(new_mood)
    
    return jsonify({"status": "success", "message": "Mood recorded"})

@app.route('/api/mood/history', methods=['GET'])
def get_mood_history():
    if 'patient_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    mood_data = mongo.db.mood_checkins.find({
        "patient_id": session['patient_id']
    }).sort("timestamp", -1).limit(30)  # Last 30 entries
    
    result = []
    for mood in mood_data:
        result.append({
            "id": str(mood['_id']),
            "mood": mood['mood'],
            "notes": mood['notes'],
            "timestamp": mood['timestamp']
        })
    
    return jsonify(result)

# Module 3: Treatment and Recovery Tracker
@app.route('/treatment-tracker')
def treatment_tracker():
    if 'patient_id' not in session:
        return redirect(url_for('login'))
    
    patient = mongo.db.patients.find_one({"_id": ObjectId(session['patient_id'])})
    return render_template('treatment_tracker.html', patient=patient)

@app.route('/api/treatment-schedule', methods=['GET'])
def get_treatment_schedule():
    if 'patient_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    # Get today's date for filtering
    today = datetime.now().date()
    
    # In a real app, this would come from the database
    # For demo purposes, we'll create a sample schedule
    schedule = {
        "patient_id": session['patient_id'],
        "tasks": [
            {
                "id": "1",
                "title": "Morning Medication",
                "time": "08:00 AM",
                "type": "Medication",
                "status": "completed",
                "description": "Take prescribed antibiotics with food"
            },
            {
                "id": "2",
                "title": "Physical Therapy",
                "time": "10:00 AM",
                "type": "Therapy",
                "status": "upcoming",
                "description": "Session with therapist Sarah"
            },
            {
                "id": "3",
                "title": "Doctor's Consultation",
                "time": "02:00 PM",
                "type": "Appointment",
                "status": "pending",
                "description": "Follow-up with Dr. Johnson"
            },
            {
                "id": "4",
                "title": "Rehabilitation Exercises",
                "time": "04:30 PM",
                "type": "Exercise",
                "status": "pending",
                "description": "Complete daily mobility exercises"
            }
        ]
    }
    
    return jsonify(schedule)

@app.route('/api/treatment/update-status', methods=['POST'])
def update_treatment_status():
    if 'patient_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.json
    task_id = data.get('task_id')
    status = data.get('status')
    
    # In a real app, this would update the database
    # For demo, we'll just return success
    
    return jsonify({"status": "success", "message": "Task status updated"})

if __name__ == "__main__":
    # Create a default patient user if not exists
    with app.app_context():
        existing = mongo.db.patients.find_one({"username": "patient01"})
        if not existing:
            mongo.db.patients.insert_one({
                "username": "patient01",
                "password": generate_password_hash("password123"),
                "name": "Patient 01",
                "created_at": datetime.utcnow()
            })
            print("✅ Default patient created: patient01 / password123")
        else:
            print("ℹ️ Default patient already exists")

    app.run(debug=True)