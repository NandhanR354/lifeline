# app.py
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_pymongo import PyMongo
from bson import ObjectId
from datetime import datetime, timedelta
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

def init_db():
    """Initialize database with sample data"""
    try:
        # Create sample patient if doesn't exist
        if mongo.db.patients.count_documents({}) == 0:
            patient_id = mongo.db.patients.insert_one({
                "username": "patient01",
                "password": generate_password_hash("password123"),
                "name": "John Smith",
                "patient_id": "PT2024001",
                "email": "john.smith@example.com",
                "room": "301A",
                "admission_date": datetime.utcnow()
            }).inserted_id

            # Create sample conversations
            mongo.db.conversations.insert_one({
                "participants": [str(patient_id), "nurse_sarah"],
                "title": "Nurse Sarah",
                "created_at": datetime.utcnow()
            })

            mongo.db.conversations.insert_one({
                "participants": [str(patient_id), "dr_johnson"],
                "title": "Dr. Johnson", 
                "created_at": datetime.utcnow()
            })

            # Create sample messages
            mongo.db.messages.insert_many([
                {
                    "conversation_id": str(mongo.db.conversations.find_one({"title": "Nurse Sarah"})["_id"]),
                    "sender_id": "nurse_sarah",
                    "message": "Your therapy session has been rescheduled to 11 AM today.",
                    "timestamp": datetime.utcnow() - timedelta(hours=2)
                },
                {
                    "conversation_id": str(mongo.db.conversations.find_one({"title": "Nurse Sarah"})["_id"]),
                    "sender_id": str(patient_id),
                    "message": "Thank you for letting me know. I'll be ready.",
                    "timestamp": datetime.utcnow() - timedelta(hours=1)
                }
            ])

            # Create sample mood check-ins
            mongo.db.mood_checkins.insert_many([
                {
                    "patient_id": str(patient_id),
                    "mood": "Great",
                    "notes": "Feeling much better today after a good night's sleep",
                    "timestamp": datetime.utcnow() - timedelta(hours=3)
                },
                {
                    "patient_id": str(patient_id),
                    "mood": "Good", 
                    "notes": "Therapy session went well",
                    "timestamp": datetime.utcnow() - timedelta(days=1)
                }
            ])

            print("✓ Sample data created successfully!")
    except Exception as e:
        print(f"Database initialization error: {e}")

# Initialize database on startup
init_db()

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
    conversations = list(mongo.db.conversations.find({
        "participants": session['patient_id']
    }))
    
    return render_template('chat.html', patient=patient, conversations=conversations)

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
        
        # Get unread count
        unread_count = mongo.db.messages.count_documents({
            "conversation_id": str(conv['_id']),
            "sender_id": {"$ne": session['patient_id']},
            "read": False
        })
        
        result.append({
            "id": str(conv['_id']),
            "title": conv.get('title', 'Conversation'),
            "last_message": last_message['message'] if last_message else "No messages yet",
            "timestamp": last_message['timestamp'] if last_message else conv['created_at'],
            "unread_count": unread_count
        })
    
    return jsonify(result)

@app.route('/api/conversations/<conversation_id>/messages', methods=['GET'])
def get_messages(conversation_id):
    if 'patient_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    # Mark messages as read
    mongo.db.messages.update_many(
        {
            "conversation_id": conversation_id,
            "sender_id": {"$ne": session['patient_id']},
            "read": False
        },
        {"$set": {"read": True}}
    )
    
    messages = mongo.db.messages.find({
        "conversation_id": conversation_id
    }).sort("timestamp", 1)
    
    result = []
    for msg in messages:
        if msg['sender_id'] == session['patient_id']:
            sender_name = "You"
        else:
            # In a real app, you'd look up the sender's name
            sender_name = "Nurse" if "nurse" in msg['sender_id'] else "Doctor"
        
        result.append({
            "id": str(msg['_id']),
            "sender": sender_name,
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
        "timestamp": datetime.utcnow(),
        "read": False
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
    }).sort("timestamp", -1).limit(30)
    
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
    
    # Sample treatment schedule - in real app, this would come from database
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
        ],
        "weekly_schedule": [
            {
                "day": "Monday",
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "tasks": ["Medication", "Physical Therapy", "Doctor Consultation"]
            },
            {
                "day": "Tuesday", 
                "date": (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d"),
                "tasks": ["Medication", "Lab Tests", "Rehabilitation"]
            },
            {
                "day": "Wednesday",
                "date": (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%d"),
                "tasks": ["Medication", "Physical Therapy", "Counseling"]
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

@app.route('/health')
def health_check():
    try:
        mongo.db.command('ping')
        return jsonify({"status": "healthy", "database": "connected"})
    except:
        return jsonify({"status": "unhealthy", "database": "disconnected"})

if __name__ == "__main__":
    print("=" * 50)
    print("LIFEL1NE Patient Dashboard")
    print("=" * 50)
    print("Access at: http://localhost:5000")
    print("Default login: patient01 / password123")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)