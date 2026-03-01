# app.py — ULTIMATE AI TRIP PLANNER 2025 (Final Integrated Version)
from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta
from urllib.parse import quote
from dotenv import load_dotenv
import httpx, os, secrets, random, string, re, html

# Import the database and models from your models.py file
from models import db, User, Trip

# === CONFIGURATION ===
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trips.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(16))

# Initialize the database with the app
db.init_app(app)

# Use Groq API Key - replace with your actual key or use environment variable
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ==========================================================
# HELPER FUNCTIONS (For History Page Images)
# ==========================================================
@app.context_processor
def utility_processor():
    def get_trip_image(place):
        return f"https://source.unsplash.com/800x600/?{quote(place)},travel,landmark"

    def get_trip_title(place):
        return f"Trip to {place}"

    def get_trip_description(place):
        return f"An amazing journey exploring the beauty of {place}."

    return dict(get_trip_image=get_trip_image,
                get_trip_title=get_trip_title,
                get_trip_description=get_trip_description)

# ==========================================================
# ITINERARY / RESTAURANTS FORMATTERS
# ==========================================================
def _strip_html_tags(text: str) -> str:
    return re.sub(r'<[^>]*?>', '', text or '')

def format_restaurants_html(raw_rest: str) -> str:
    """
    Accept either newline-separated list or already HTML and return an HTML <ul>.
    """
    if not raw_rest:
        return ""
    raw = raw_rest.strip()
    # If it already contains <ul> or <li> return as-is (safer to allow)
    if re.search(r'<\/?ul>|<\/?li>', raw, flags=re.I):
        return raw
    # Split on newlines or dashes
    items = [x.strip("-* \t") for x in re.split(r'[\r\n]+', raw) if x.strip()]
    if not items:
        return html.escape(raw)
    lis = "".join(f"<li>{html.escape(i)}</li>" for i in items)
    return f"<ul>{lis}</ul>"

def format_itinerary_html(raw: str) -> str:
    """
    Convert AI/plain text into structured .day-card HTML for CSS to work.
    If already contains .day-card markup, return as-is.
    """
    if not raw:
        return ""
    # If already contains day-card markup, return as-is
    if "class=\"day-card\"" in raw or "class='day-card'" in raw:
        return raw

    text = raw.strip()

    # If the AI returned full HTML (contains <div> tags), try to extract blocks
    if "<div" in text and "day" in text.lower():
        # Minimal sanitization: return as-is
        return text

    # Parse lines and try to find "Day X" markers
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    days = []
    current_items = []
    day_title = None

    day_marker_re = re.compile(r'(?i)^(day[\s\-:]*\d+|day\s+\w+|day\s*\d+)', re.I)

    for line in lines:
        # If line starts with "Day", "Day 1", "Day One", treat as new day
        if day_marker_re.match(line):
            # push previous
            if day_title or current_items:
                days.append((day_title or f"Day {len(days)+1}", list(current_items)))
            current_items = []
            # Extract a friendly title, e.g. "Day 1 — Arrival & City Tour"
            day_title = re.sub(r'^(?i)day[\s\-:]*', 'Day ', line, flags=re.I).strip()
            continue

        # Lines that look like bullet items or include times
        if re.match(r'^[\-\*•]\s*', line) or re.search(r'\d{1,2}:\d{2}', line) or "am" in line.lower() or "pm" in line.lower():
            # normalize bullet
            item = re.sub(r'^[\-\*•]\s*', '', line).strip()
            current_items.append(item)
        else:
            # If not time/bullet, treat as descriptive list item
            current_items.append(line)

    # push last
    if day_title or current_items:
        days.append((day_title or f"Day {len(days)+1}", list(current_items)))

    # If no days parsed, try to chunk evenly based on requested days if mentioned like "Create a 3-day itinerary"
    if not days:
        # simple fallback: put everything into Day 1
        days = [("Day 1", [html.escape(line) for line in lines])]

    # Build HTML
    html_parts = []
    for idx, (title, items) in enumerate(days, start=1):
        # ensure title like "Day X" exists
        if not title:
            title = f"Day {idx}"
        # Escape each item but keep simple formatting (allow commas)
        li_html = "".join(f"<li>{html.escape(it)}</li>" for it in items)
        html_parts.append(
            f"""
            <div class="day-card">
                <h4>{html.escape(title)}</h4>
                <ul>
                    {li_html}
                </ul>
            </div>
            """
        )

    return "\n".join(html_parts)


# ==========================================================
# GROQ API ITINERARY GENERATOR
# ==========================================================
def generate_ai_itinerary(place, days, adults, children, start_date=None):
    """
    Returns tuple: (description_str, itinerary_html, restaurants_html)
    Always returns HTML-safe itinerary/restaurants (formatters applied).
    Uses Groq API instead of OpenAI.
    """
    if not GROQ_API_KEY:
        # Fallback
        desc = f"A short curated {days}-day trip to {place}."
        itin = "<div class='day-card'><h4>Day 1 – Welcome</h4><ul><li>09:00 AM – Arrival & Relax</li><li>02:00 PM – Local Walk</li></ul></div>"
        rest = "- Local Cuisine\n- Street Food"
        return desc, format_itinerary_html(itin), format_restaurants_html(rest)

    prompt = f"""
You are a professional travel planner. Generate a {days}-day trip for {place}, India.
Adults: {adults}, Children: {children}.
Return plain HTML fragments only (no surrounding <html> or <body> tags).
Format:

DESCRIPTION:
A one-line catchy description.

ITINERARY:
<div class="day-card">
  <h4>Day 1 – Title</h4>
  <ul>
    <li>09:00 AM – Activity description</li>
    <li>01:00 PM – Lunch suggestion</li>
  </ul>
</div>

Repeat similar blocks for each day.

RESTAURANTS:
- Restaurant 1
- Restaurant 2
- Restaurant 3

Do not include any extraneous commentary.
"""

    try:
        # Use Groq API endpoint instead of OpenAI
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",  # Groq model
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "temperature": 0.7,
            },
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            raise ValueError("Empty response from AI")

        # Extract DESCRIPTION, ITINERARY, RESTAURANTS parts robustly
        desc = ""
        itin_raw = ""
        rest_raw = ""

        # Normalize markers
        content_norm = content.replace("\r\n", "\n")
        # Attempt splits
        if "DESCRIPTION:" in content_norm.upper():
            try:
                desc = re.split(r'DESCRIPTION[:\n]', content_norm, flags=re.I)[1].split("ITINERARY:")[0].strip()
            except Exception:
                desc = ""
        if "ITINERARY:" in content_norm.upper():
            try:
                itin_section = re.split(r'ITINERARY[:\n]', content_norm, flags=re.I)[1]
                # If RESTAURANTS exists, stop before it
                if re.search(r'RESTAURANTS[:\n]', itin_section, flags=re.I):
                    itin_raw = re.split(r'RESTAURANTS[:\n]', itin_section, flags=re.I)[0].strip()
                else:
                    # whole remaining block could be itinerary if restaurants absent
                    itin_raw = itin_section.strip()
            except Exception:
                itin_raw = ""
        if "RESTAURANTS:" in content_norm.upper():
            try:
                rest_raw = re.split(r'RESTAURANTS[:\n]', content_norm, flags=re.I)[1].strip()
            except Exception:
                rest_raw = ""

        # If we couldn't parse desc, fallback to first line
        if not desc:
            # take first non-empty line as description
            for line in content_norm.splitlines():
                if line.strip():
                    desc = line.strip()
                    break

        # Format results into HTML (ensures .day-card wrapping)
        itin_html = format_itinerary_html(itin_raw or content_norm)
        restaurants_html = format_restaurants_html(rest_raw)

        return desc or f"A {days}-day trip to {place}.", itin_html, restaurants_html

    except Exception as e:
        print("GROQ AI ERROR:", e)
        # graceful fallback
        desc = f"A {days}-day trip to {place}."
        itin = "<div class='day-card'><h4>Day 1 – Welcome</h4><ul><li>09:00 AM – Arrival</li><li>02:00 PM – Hotel Check-in</li><li>06:00 PM – Local Market</li></ul></div>"
        rest = "- Local Cuisine\n- Street Food"
        return desc, format_itinerary_html(itin), format_restaurants_html(rest)

# ==========================================================
# ROUTES
# ==========================================================
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    trips = Trip.query.filter_by(user_id=session['user_id']).order_by(Trip.date_created.desc()).all()
    return render_template('dashboard.html', trips=trips)


@app.route('/history')
def history():
    if 'user_id' not in session:
        flash('Please login to view history.', 'info')
        return redirect(url_for('login'))
    trips = Trip.query.filter_by(user_id=session['user_id']).order_by(Trip.date_created.desc()).all()
    return render_template('history.html', trips=trips)


@app.route('/famous_places')
def famous_places():
    return render_template('famous_places.html')


# --- AUTH ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password', 'danger')
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm = request.form['confirm_password']

        if password != confirm:
            flash('Passwords do not match!', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Email already taken!', 'danger')
        else:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('home'))


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('If an account exists, a reset link has been sent.', 'success')
            return redirect(url_for('login'))

        token = ''.join(random.choices(string.ascii_letters + string.digits, k=64))
        user.reset_token = token
        user.reset_token_expires = datetime.utcnow() + timedelta(minutes=30)
        db.session.commit()
        return redirect(url_for('reset_password', token=token))
    return render_template('forgot_password.html')


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or user.reset_token_expires < datetime.utcnow():
        flash('Invalid or expired link.', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form['password']
        confirm = request.form['confirm_password']
        if password != confirm:
            flash('Passwords do not match!', 'danger')
        else:
            user.set_password(password)
            user.reset_token = None
            user.reset_token_expires = None
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('login'))
    return render_template('reset_password.html')


# --- PLAN TRIP ---
@app.route('/plantrip', methods=['GET', 'POST'])
def plantrip():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    if request.method == 'POST':
        place = request.form['place'].strip()

        # === DYNAMIC INDIA CHECK ---
        if not is_place_in_india(place):
            flash("This service is restricted to Indian locations only.", "danger")
            return redirect(url_for('plantrip'))
        # ============================
        days = int(request.form.get('days', 7))
        adults = int(request.form.get('adults', 1))
        children = int(request.form.get('children', 0))
        start_date_str = request.form.get('travel_date')
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None

        desc, itin, rest = generate_ai_itinerary(place, days, adults, children, start_date)
        # Always format/clean before saving
        itin_html = format_itinerary_html(itin)
        rest_html = format_restaurants_html(rest)
       
       # --- NEW IMAGE LOGIC (Updated) ---
        # 1. Default fallback (online image)
        image_url = f"https://source.unsplash.com/1600x900/?{quote(place)},travel"

        # 2. Check for local image with various extensions (.jpeg, .png, .webp, .avif)
        base_name = place.lower().replace(' ', '_')
        for ext in ['.jpeg', '.jpg', '.png', '.webp', '.avif']:
            local_filename = f"{base_name}{ext}"
            local_file_path = os.path.join(app.root_path, 'static', 'images', local_filename)
            
            if os.path.exists(local_file_path):
                # If found, set the image URL to the local static path
                image_url = url_for('static', filename=f'images/{local_filename}')
                break
        # -----------------------------------


        trip = Trip(
            user_id=session['user_id'], place=place, days=days, adults=adults,
            children=children, start_date=start_date, description=desc,
            itinerary=itin_html, restaurants=rest_html, image_url=image_url
        )
        db.session.add(trip)
        db.session.commit()
        return redirect(url_for('view_itinerary', trip_id=trip.id))

    return render_template('plantrip.html', tomorrow=tomorrow)

def is_place_in_india(place):
    """
    Uses Groq API to dynamically determine if the place is in India.
    Returns True/False.
    """
    if not GROQ_API_KEY:
        return True  # Allow if no API key
    
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",  # Groq model
                "messages": [
                    {
                        "role": "system",
                        "content": "Return ONLY 'yes' or 'no'. No other text."
                    },
                    {
                        "role": "user",
                        "content": f"Is '{place}' a location inside India? Answer only yes or no."
                    }
                ],
                "max_tokens": 2,
                "temperature": 0.1,
            },
            timeout=20
        )
        data = response.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("No choices returned from Groq API")

        choice = choices[0]
        content = (
            choice.get("message", {}).get("content")
            or choice.get("delta", {}).get("content")
            or choice.get("text")
        )

        if not content:
            raise ValueError("No content returned from Groq API")

        answer = content.strip().lower()
        return answer == "yes"

    except Exception as e:
        print("Place validation error:", e)
        return True   # allow user if API fails

@app.route('/itinerary/<int:trip_id>')
def view_itinerary(trip_id):
    trip = Trip.query.get_or_404(trip_id)

    if trip.user_id != session.get('user_id'):
        return redirect(url_for('dashboard'))

    # Ensure formatted before render
    trip.itinerary = format_itinerary_html(trip.itinerary)
    trip.restaurants = format_restaurants_html(trip.restaurants)

    return render_template(
        'itinerary.html',
        trip=trip,
        cache_buster=int(datetime.now().timestamp())
    )



@app.route('/regenerate/<int:trip_id>', methods=['POST'])
def regenerate_itinerary(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.user_id != session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403

    desc, itin, rest = generate_ai_itinerary(trip.place, trip.days, trip.adults, trip.children, trip.start_date)
    trip.description = desc
    trip.itinerary = format_itinerary_html(itin)
    trip.restaurants = format_restaurants_html(rest)
    db.session.commit()
    return jsonify({"description": desc, "itinerary": trip.itinerary})


# --- CHATBOT ---
@app.route('/chatbot', methods=['POST'])
def chatbot_route():
    data = request.get_json(silent=True) or {}
    user_message = data.get('message', '').strip()

    if not user_message:
        return jsonify({'reply': "Hello! How can I help you plan your trip?"})

    if not GROQ_API_KEY:
        return jsonify({'reply': f"I received: '{html.escape(user_message)}'. (Please configure Groq API Key)"})

    try:
        print("GROQ API KEY FOUND:", bool(GROQ_API_KEY))
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",  # Groq model
                "messages": [
                    {"role": "system", "content": "You are a friendly travel assistant that helps plan trips."},
                    {"role": "user", "content": user_message}
                ],
                "max_tokens": 300,
                "temperature": 0.7,
            },
            timeout=30
        )
        response.raise_for_status()
        bot_reply = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return jsonify({'reply': bot_reply or "Sorry, I couldn't generate an answer."})
    except Exception as e:
        print("CHATBOT ERROR:", e)
        return jsonify({'reply': "Sorry, I'm having trouble connecting to the AI right now."})


# --- USER PROFILE ---
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if not user.check_password(current_password):
            flash('Incorrect current password!', 'danger')
        elif new_password != confirm_password:
            flash('New passwords do not match!', 'danger')
        else:
            user.set_password(new_password)
            db.session.commit()
            flash('Password updated successfully!', 'success')

    return render_template('profile.html', user=user)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Creates the database if it doesn't exist
    print("✅ APPLICATION STARTED: http://127.0.0.1:5000")
    print(f"✅ GROQ API: {'Configured' if GROQ_API_KEY else 'Not configured'}")
    app.run(debug=True)