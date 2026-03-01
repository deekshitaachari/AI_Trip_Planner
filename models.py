from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    trips = db.relationship('Trip', backref='user', lazy=True)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    place = db.Column(db.String(100), nullable=False)
    days = db.Column(db.Integer, nullable=False)
    adults = db.Column(db.Integer, default=1)
    children = db.Column(db.Integer, default=0)
    start_date = db.Column(db.Date, nullable=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Fields for AI Content
    description = db.Column(db.String(500), nullable=True)
    itinerary = db.Column(db.Text, nullable=True)
    restaurants = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)