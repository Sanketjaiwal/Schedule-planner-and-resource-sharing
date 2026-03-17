from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
import mysql.connector
from config import Config
import os
from datetime import datetime, timedelta, time, date
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)
app.config.from_object(Config)

# Database connection
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            database=app.config['MYSQL_DB']
        )
        return conn
    except mysql.connector.Error as e:
        print(f"Database connection error: {e}")
        return None

# Helper function to convert timedelta to time
def timedelta_to_time(td):
    """Convert timedelta to time object"""
    if isinstance(td, timedelta):
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return time(hour=hours, minute=minutes)
    return td

# Helper function to process timetable entries
def process_timetable_entries(entries):
    """Process timetable entries to ensure time objects are properly formatted"""
    processed_entries = []
    for entry in entries:
        # Create a copy of the entry
        processed_entry = dict(entry)
        
        # Convert start_time and end_time if they are timedelta objects
        if 'start_time' in processed_entry:
            processed_entry['start_time'] = timedelta_to_time(processed_entry['start_time'])
        if 'end_time' in processed_entry:
            processed_entry['end_time'] = timedelta_to_time(processed_entry['end_time'])
            
        processed_entries.append(processed_entry)
    return processed_entries

# Helper function to process reserved times
def process_reserved_times(reserved_times):
    """Process reserved time entries to ensure time objects are properly formatted"""
    processed_reserved = []
    for reserved in reserved_times:
        processed_reserved_item = dict(reserved)
        
        # Convert start_time and end_time if they are timedelta objects
        if 'start_time' in processed_reserved_item:
            processed_reserved_item['start_time'] = timedelta_to_time(processed_reserved_item['start_time'])
        if 'end_time' in processed_reserved_item:
            processed_reserved_item['end_time'] = timedelta_to_time(processed_reserved_item['end_time'])
            
        # Parse JSON days
        if processed_reserved_item.get('days'):
            try:
                processed_reserved_item['days_list'] = json.loads(processed_reserved_item['days'])
            except json.JSONDecodeError:
                processed_reserved_item['days_list'] = []
        else:
            processed_reserved_item['days_list'] = []
            
        processed_reserved.append(processed_reserved_item)
    return processed_reserved

# Helper function to get week dates
def get_week_dates(target_date=None):
    """Get all dates for the current week starting from Monday"""
    if target_date is None:
        target_date = datetime.now()
    
    # Find Monday of the current week
    start_date = target_date - timedelta(days=target_date.weekday())
    
    week_dates = {}
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    for i, day in enumerate(days):
        week_dates[day] = start_date + timedelta(days=i)
    
    return week_dates

# Create upload folder
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Theme detection function
def get_user_theme():
    if 'user_id' in session:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT theme FROM users WHERE id = %s", (session['user_id'],))
                user = cursor.fetchone()
                if user and user['theme']:
                    return user['theme']
            except mysql.connector.Error:
                pass
            finally:
                cursor.close()
                conn.close()
    
    # Default theme or system detection
    return session.get('theme', 'light')

# Apply theme context to all templates
@app.context_processor
def inject_theme():
    theme = get_user_theme()
    
    # Handle auto theme detection
    if theme == 'auto':
        # You can implement system theme detection here
        # For now, we'll default to light mode
        theme_class = 'theme-auto'
    else:
        theme_class = f'theme-{theme}'
    
    return {
        'current_theme': theme,
        'theme_class': theme_class
    }
    
# Template filter to safely format time
@app.template_filter('safe_strftime')
def safe_strftime(value, format='%H:%M'):
    """Safely format time objects, handling both time and timedelta objects"""
    if not value:
        return ""
    
    # If it's a time object, use strftime
    if hasattr(value, 'strftime'):
        return value.strftime(format)
    
    # If it's a timedelta object, convert to time first
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        time_obj = time(hour=hours, minute=minutes)
        return time_obj.strftime(format)
    
    # If it's already a string or other type, return as is
    return str(value)

# Routes
@app.route('/')
def index():
    return redirect(url_for('home'))

@app.route('/home')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        course = request.form['course']
        
        conn = get_db_connection()
        if conn is None:
            flash('Database connection error!', 'error')
            return render_template('register.html')
            
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO users (name, email, password, course, theme) VALUES (%s, %s, %s, %s, 'light')",
                (name, email, password, course)
            )
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Email already exists!', 'error')
        except mysql.connector.Error as e:
            flash(f'Registration error: {e}', 'error')
        finally:
            cursor.close()
            conn.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        if conn is None:
            flash('Database connection error!', 'error')
            return render_template('login.html')
            
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
            user = cursor.fetchone()
            
            if user:
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['user_course'] = user['course']
                session['user_email'] = user['email']
                session['theme'] = user.get('theme', 'light')
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid email or password!', 'error')
        except mysql.connector.Error as e:
            flash(f'Login error: {e}', 'error')
        finally:
            cursor.close()
            conn.close()
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('login'))
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get user data for profile
        cursor.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
        user_data = cursor.fetchone()
        
        # Get recent tasks
        cursor.execute("SELECT * FROM tasks WHERE user_id = %s ORDER BY due_date LIMIT 10", (session['user_id'],))
        recent_tasks = cursor.fetchall()
        
        # Get today's timetable
        today = datetime.now().strftime('%A')
        cursor.execute(
            "SELECT * FROM timetable WHERE user_id = %s AND day = %s ORDER BY start_time",
            (session['user_id'], today)
        )
        today_schedule = cursor.fetchall()
        today_schedule = process_timetable_entries(today_schedule)
        
        # Get upcoming tasks
        next_week = datetime.now() + timedelta(days=7)
        cursor.execute(
            "SELECT * FROM tasks WHERE user_id = %s AND due_date BETWEEN %s AND %s AND completed = FALSE ORDER BY due_date LIMIT 5",
            (session['user_id'], datetime.now(), next_week)
        )
        upcoming_tasks = cursor.fetchall()
        
        # Get weekly tasks count
        cursor.execute(
            "SELECT COUNT(*) as count FROM tasks WHERE user_id = %s AND due_date BETWEEN %s AND %s",
            (session['user_id'], datetime.now(), datetime.now() + timedelta(days=7))
        )
        weekly_tasks_result = cursor.fetchone()
        weekly_tasks_count = weekly_tasks_result['count'] if weekly_tasks_result else 0
        
        # Get user's uploaded resources for dashboard (last 6)
        cursor.execute(
            """SELECT * FROM resources 
               WHERE user_id = %s 
               ORDER BY uploaded_at DESC 
               LIMIT 6""",
            (session['user_id'],)
        )
        user_resources = cursor.fetchall()
        
    except mysql.connector.Error as e:
        flash(f'Dashboard error: {e}', 'error')
        recent_tasks = []
        today_schedule = []
        upcoming_tasks = []
        weekly_tasks_count = 0
        user_data = {}
        user_resources = []
    finally:
        cursor.close()
        conn.close()
    
    return render_template('dashboard.html', 
                         recent_tasks=recent_tasks,
                         today_schedule=today_schedule,
                         upcoming_tasks=upcoming_tasks,
                         weekly_tasks_count=weekly_tasks_count,
                         user_data=user_data,
                         user_resources=user_resources,
                         now=datetime.now())

@app.route('/timetable')
def timetable():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('dashboard'))
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get current week dates
        current_date = datetime.now()
        week_dates = get_week_dates(current_date)
        
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        timetable_data = {}
        
        for day in days:
            # Get schedules for this day (both repeating and specific date schedules)
            cursor.execute("""
                SELECT * FROM timetable 
                WHERE user_id = %s AND day = %s 
                AND (
                    repeat_type != 'none' 
                    OR (repeat_type = 'none' AND schedule_date = %s)
                    OR (repeat_type = 'none' AND schedule_date IS NULL)
                )
                ORDER BY start_time
            """, (session['user_id'], day, week_dates[day].date()))
            entries = cursor.fetchall()
            timetable_data[day] = process_timetable_entries(entries)
        
        # Get reserved time slots
        cursor.execute(
            "SELECT * FROM reserved_time WHERE user_id = %s ORDER BY created_at DESC",
            (session['user_id'],)
        )
        reserved_times = cursor.fetchall()
        reserved_times = process_reserved_times(reserved_times)
        
    except mysql.connector.Error as e:
        flash(f'Timetable error: {e}', 'error')
        timetable_data = {}
        days = []
        reserved_times = []
        week_dates = get_week_dates()
    finally:
        cursor.close()
        conn.close()
    
    return render_template('timetable.html', 
                         timetable_data=timetable_data, 
                         days=days,
                         reserved_times=reserved_times,
                         week_dates=week_dates)

@app.route('/add_timetable_entry', methods=['POST'])
def add_timetable_entry():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    day = request.form['day']
    start_time = request.form['start_time']
    end_time = request.form['end_time']
    activity_type = request.form['activity_type']
    description = request.form['description']
    subject = request.form.get('subject', '')
    repeat_type = request.form.get('repeat_type', 'none')
    repeat_days = request.form.getlist('repeat_days')
    schedule_date = request.form.get('schedule_date', '')
    
    # Validate time inputs
    if not start_time or not end_time:
        flash('Please provide both start and end times!', 'error')
        return redirect(url_for('timetable'))
    
    if start_time >= end_time:
        flash('End time must be after start time!', 'error')
        return redirect(url_for('timetable'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('timetable'))
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        days_to_add = []
        specific_date = None
        
        # Determine which days to add the schedule to
        if repeat_type == 'none':
            days_to_add = [day]
            # Use the specific date if provided, otherwise use current date
            if schedule_date:
                specific_date = schedule_date
            else:
                # Get the date for the selected day in current week
                week_dates = get_week_dates()
                specific_date = week_dates[day].date()
        elif repeat_type == 'daily':
            # Add for all 7 days
            days_to_add = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        elif repeat_type == 'weekly':
            # Add only for the selected day every week
            days_to_add = [day]
        elif repeat_type == 'specific_days' and repeat_days:
            # Add for specific selected days
            days_to_add = repeat_days
        else:
            days_to_add = [day]
        
        added_entries = 0
        conflicts = []
        
        for target_day in days_to_add:
            # Check for overlapping entries
            cursor.execute("""
                SELECT * FROM timetable 
                WHERE user_id = %s AND day = %s 
                AND (
                    (start_time <= %s AND end_time > %s) OR
                    (start_time < %s AND end_time >= %s) OR
                    (start_time >= %s AND end_time <= %s)
                )
                AND (
                    repeat_type != 'none' 
                    OR (repeat_type = 'none' AND schedule_date = %s)
                    OR (repeat_type = 'none' AND schedule_date IS NULL)
                )
            """, (session['user_id'], target_day, start_time, start_time, end_time, end_time, start_time, end_time, specific_date))
            day_conflicts = cursor.fetchall()
            
            if day_conflicts:
                conflicts.append(target_day)
                continue
            
            # Check for reserved time conflicts
            cursor.execute(
                """SELECT * FROM reserved_time 
                   WHERE user_id = %s AND JSON_CONTAINS(days, %s)
                   AND (
                       (start_time <= %s AND end_time > %s) OR
                       (start_time < %s AND end_time >= %s) OR
                       (start_time >= %s AND end_time <= %s)
                   )""",
                (session['user_id'], json.dumps(target_day), start_time, start_time, end_time, end_time, start_time, end_time)
            )
            reserved_conflicts = cursor.fetchall()
            
            if reserved_conflicts:
                conflicts.append(f"{target_day} (reserved)")
                continue
            
            # Add new entry
            cursor.execute(
                "INSERT INTO timetable (user_id, day, start_time, end_time, activity_type, description, subject, repeat_type, repeat_days, schedule_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (session['user_id'], target_day, start_time, end_time, activity_type, description, subject, repeat_type, json.dumps(repeat_days) if repeat_days else None, specific_date)
            )
            added_entries += 1
        
        conn.commit()
        
        if added_entries > 0:
            if len(days_to_add) == 1:
                flash('Timetable entry added successfully!', 'success')
            else:
                flash(f'Timetable entries added successfully for {added_entries} days!', 'success')
            
            if conflicts:
                flash(f'Could not add entries for: {", ".join(conflicts)} due to conflicts.', 'warning')
        else:
            flash('Could not add any timetable entries due to conflicts!', 'error')
            
    except mysql.connector.Error as e:
        flash(f'Error adding timetable entry: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('timetable'))

@app.route('/delete_timetable_entry/<int:entry_id>')
def delete_timetable_entry(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('timetable'))
        
    cursor = conn.cursor()
    
    try:
        # First check if the entry belongs to the user
        cursor.execute("SELECT * FROM timetable WHERE id = %s AND user_id = %s", (entry_id, session['user_id']))
        entry = cursor.fetchone()
        
        if not entry:
            flash('Timetable entry not found or you do not have permission to delete it!', 'error')
            return redirect(url_for('timetable'))
            
        cursor.execute("DELETE FROM timetable WHERE id = %s AND user_id = %s", (entry_id, session['user_id']))
        conn.commit()
        flash('Timetable entry deleted successfully!', 'success')
    except mysql.connector.Error as e:
        flash(f'Error deleting timetable entry: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('timetable'))

@app.route('/edit_timetable_entry', methods=['POST'])
def edit_timetable_entry():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    entry_id = request.form.get('entry_id')
    day = request.form.get('day')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    activity_type = request.form.get('activity_type')
    description = request.form.get('description')
    subject = request.form.get('subject', '')
    
    if not all([entry_id, day, start_time, end_time, activity_type, description]):
        return jsonify({'success': False, 'error': 'All fields are required'}), 400
    
    if start_time >= end_time:
        return jsonify({'success': False, 'error': 'End time must be after start time'}), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'error': 'Database connection error'}), 500
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if the entry belongs to the user
        cursor.execute("SELECT * FROM timetable WHERE id = %s AND user_id = %s", (entry_id, session['user_id']))
        entry = cursor.fetchone()
        
        if not entry:
            return jsonify({'success': False, 'error': 'Timetable entry not found'}), 404
        
        # Update the entry
        cursor.execute("""
            UPDATE timetable 
            SET day = %s, start_time = %s, end_time = %s, activity_type = %s, description = %s, subject = %s
            WHERE id = %s AND user_id = %s
        """, (day, start_time, end_time, activity_type, description, subject, entry_id, session['user_id']))
        
        conn.commit()
        return jsonify({'success': True, 'message': 'Timetable entry updated successfully'})
        
    except mysql.connector.Error as e:
        return jsonify({'success': False, 'error': f'Error updating timetable entry: {e}'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get_timetable_entry/<int:entry_id>')
def get_timetable_entry(entry_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection error'}), 500
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM timetable WHERE id = %s AND user_id = %s", (entry_id, session['user_id']))
        entry = cursor.fetchone()
        
        if entry:
            # Process time objects for JSON serialization
            if entry['start_time']:
                if isinstance(entry['start_time'], time):
                    entry['start_time'] = entry['start_time'].strftime('%H:%M')
            if entry['end_time']:
                if isinstance(entry['end_time'], time):
                    entry['end_time'] = entry['end_time'].strftime('%H:%M')
            
            return jsonify(entry)
        else:
            return jsonify({'error': 'Timetable entry not found'}), 404
    except mysql.connector.Error as e:
        return jsonify({'error': f'Database error: {e}'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/add_reserved_time', methods=['POST'])
def add_reserved_time():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    title = request.form.get('title', '')
    start_time = request.form['start_time']
    end_time = request.form['end_time']
    days = request.form.getlist('days')
    
    if not days:
        flash('Please select at least one day!', 'error')
        return redirect(url_for('timetable'))
    
    if start_time >= end_time:
        flash('End time must be after start time!', 'error')
        return redirect(url_for('timetable'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('timetable'))
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check for conflicts with existing reserved time
        for day in days:
            cursor.execute(
                """SELECT * FROM reserved_time 
                   WHERE user_id = %s AND JSON_CONTAINS(days, %s)
                   AND (
                       (start_time <= %s AND end_time > %s) OR
                       (start_time < %s AND end_time >= %s) OR
                       (start_time >= %s AND end_time <= %s)
                   )""",
                (session['user_id'], json.dumps(day), start_time, start_time, end_time, end_time, start_time, end_time)
            )
            conflicts = cursor.fetchall()
            
            if conflicts:
                flash(f'This reserved time conflicts with existing reserved time on {day}!', 'error')
                return redirect(url_for('timetable'))
        
        # Check for conflicts with user schedules
        for day in days:
            cursor.execute(
                """SELECT * FROM timetable 
                   WHERE user_id = %s AND day = %s
                   AND (
                       (start_time <= %s AND end_time > %s) OR
                       (start_time < %s AND end_time >= %s) OR
                       (start_time >= %s AND end_time <= %s)
                   )""",
                (session['user_id'], day, start_time, start_time, end_time, end_time, start_time, end_time)
            )
            schedule_conflicts = cursor.fetchall()
            
            if schedule_conflicts:
                flash(f'This reserved time conflicts with your schedule on {day}!', 'error')
                return redirect(url_for('timetable'))
        
        # Add reserved time
        cursor.execute(
            "INSERT INTO reserved_time (user_id, title, start_time, end_time, days) VALUES (%s, %s, %s, %s, %s)",
            (session['user_id'], title, start_time, end_time, json.dumps(days))
        )
        conn.commit()
        flash('Reserved time added successfully!', 'success')
    except mysql.connector.Error as e:
        flash(f'Error adding reserved time: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('timetable'))

@app.route('/delete_reserved_time/<int:reserved_id>')
def delete_reserved_time(reserved_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('timetable'))
        
    cursor = conn.cursor()
    
    try:
        # First check if the reserved time belongs to the user
        cursor.execute("SELECT * FROM reserved_time WHERE id = %s AND user_id = %s", (reserved_id, session['user_id']))
        reserved = cursor.fetchone()
        
        if not reserved:
            flash('Reserved time not found or you do not have permission to delete it!', 'error')
            return redirect(url_for('timetable'))
            
        cursor.execute("DELETE FROM reserved_time WHERE id = %s AND user_id = %s", (reserved_id, session['user_id']))
        conn.commit()
        flash('Reserved time deleted successfully!', 'success')
    except mysql.connector.Error as e:
        flash(f'Error deleting reserved time: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('timetable'))

# In your app.py, update the get_timetable_data route and helper functions:
@app.route('/get_timetable_data')
def get_timetable_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection error'}), 500
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get current week dates
        current_date = datetime.now()
        week_dates = get_week_dates(current_date)
        
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        timetable_data = {}
        
        for day in days:
            # Get current date for this day in the week
            current_day_date = week_dates[day].date()
            
            cursor.execute("""
                SELECT * FROM timetable 
                WHERE user_id = %s AND day = %s 
                AND (
                    repeat_type != 'none' 
                    OR (repeat_type = 'none' AND schedule_date = %s)
                    OR (repeat_type = 'none' AND schedule_date IS NULL)
                )
                ORDER BY start_time
            """, (session['user_id'], day, current_day_date))
            entries = cursor.fetchall()
            
            # Process entries to ensure proper formatting
            processed_entries = []
            for entry in entries:
                processed_entry = dict(entry)
                
                # Convert start_time and end_time if they are timedelta objects
                if 'start_time' in processed_entry:
                    if isinstance(processed_entry['start_time'], timedelta):
                        processed_entry['start_time'] = timedelta_to_time(processed_entry['start_time'])
                    if hasattr(processed_entry['start_time'], 'strftime'):
                        processed_entry['start_time'] = processed_entry['start_time'].strftime('%H:%M')
                    else:
                        processed_entry['start_time'] = str(processed_entry['start_time'])
                
                if 'end_time' in processed_entry:
                    if isinstance(processed_entry['end_time'], timedelta):
                        processed_entry['end_time'] = timedelta_to_time(processed_entry['end_time'])
                    if hasattr(processed_entry['end_time'], 'strftime'):
                        processed_entry['end_time'] = processed_entry['end_time'].strftime('%H:%M')
                    else:
                        processed_entry['end_time'] = str(processed_entry['end_time'])
                
                # Ensure schedule_date is properly formatted
                if processed_entry.get('schedule_date'):
                    if hasattr(processed_entry['schedule_date'], 'isoformat'):
                        processed_entry['schedule_date'] = processed_entry['schedule_date'].isoformat()
                    else:
                        processed_entry['schedule_date'] = str(processed_entry['schedule_date'])
                
                processed_entries.append(processed_entry)
            
            timetable_data[day] = processed_entries
        
        # Get reserved times
        cursor.execute(
            "SELECT * FROM reserved_time WHERE user_id = %s",
            (session['user_id'],)
        )
        reserved_times = cursor.fetchall()
        
        # Process reserved times
        processed_reserved = []
        for reserved in reserved_times:
            processed_reserved_item = dict(reserved)
            
            # Convert times
            if 'start_time' in processed_reserved_item:
                if isinstance(processed_reserved_item['start_time'], timedelta):
                    processed_reserved_item['start_time'] = timedelta_to_time(processed_reserved_item['start_time'])
                if hasattr(processed_reserved_item['start_time'], 'strftime'):
                    processed_reserved_item['start_time'] = processed_reserved_item['start_time'].strftime('%H:%M')
                else:
                    processed_reserved_item['start_time'] = str(processed_reserved_item['start_time'])
            
            if 'end_time' in processed_reserved_item:
                if isinstance(processed_reserved_item['end_time'], timedelta):
                    processed_reserved_item['end_time'] = timedelta_to_time(processed_reserved_item['end_time'])
                if hasattr(processed_reserved_item['end_time'], 'strftime'):
                    processed_reserved_item['end_time'] = processed_reserved_item['end_time'].strftime('%H:%M')
                else:
                    processed_reserved_item['end_time'] = str(processed_reserved_item['end_time'])
            
            # Parse JSON days
            if processed_reserved_item.get('days'):
                try:
                    processed_reserved_item['days_list'] = json.loads(processed_reserved_item['days'])
                except json.JSONDecodeError:
                    processed_reserved_item['days_list'] = []
            else:
                processed_reserved_item['days_list'] = []
                
            processed_reserved.append(processed_reserved_item)
        
        return jsonify({
            'timetable': timetable_data,
            'reserved_times': processed_reserved,
            'week_dates': {day: date.strftime('%Y-%m-%d') for day, date in week_dates.items()}
        })
    except Exception as e:
        print(f"Error in get_timetable_data: {e}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()
# ... (Keep all the other existing routes: tasks, resources, profile, etc. They remain unchanged)

@app.route('/tasks')
def tasks():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('dashboard'))
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM tasks WHERE user_id = %s ORDER BY due_date", (session['user_id'],))
        user_tasks = cursor.fetchall()
    except mysql.connector.Error as e:
        flash(f'Tasks error: {e}', 'error')
        user_tasks = []
    finally:
        cursor.close()
        conn.close()
    
    return render_template('tasks.html', tasks=user_tasks, now=datetime.now())

@app.route('/add_task', methods=['POST'])
def add_task():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    task_name = request.form['task_name']
    description = request.form['description']
    due_date = request.form['due_date']
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('tasks'))
        
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO tasks (user_id, task_name, description, due_date) VALUES (%s, %s, %s, %s)",
            (session['user_id'], task_name, description, due_date)
        )
        conn.commit()
        flash('Task added successfully!', 'success')
    except mysql.connector.Error as e:
        flash(f'Error adding task: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('tasks'))

@app.route('/delete_task/<int:task_id>')
def delete_task(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('tasks'))
        
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM tasks WHERE id = %s AND user_id = %s", (task_id, session['user_id']))
        conn.commit()
        flash('Task deleted successfully!', 'success')
    except mysql.connector.Error as e:
        flash(f'Error deleting task: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('tasks'))

@app.route('/complete_task/<int:task_id>')
def complete_task(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('tasks'))
        
    cursor = conn.cursor()
    
    try:
        # Toggle completion status
        cursor.execute("UPDATE tasks SET completed = NOT completed WHERE id = %s AND user_id = %s", (task_id, session['user_id']))
        conn.commit()
        flash('Task status updated!', 'success')
    except mysql.connector.Error as e:
        flash(f'Error updating task: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('tasks'))

@app.route('/resources')
def resources():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('dashboard'))
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get all courses for dropdown
        cursor.execute("SELECT DISTINCT course FROM users ORDER BY course")
        courses = [row['course'] for row in cursor.fetchall()]
        
        # Get resources for current user's course
        cursor.execute(
            """SELECT r.*, u.name as uploader_name 
               FROM resources r 
               JOIN users u ON r.user_id = u.id 
               WHERE r.course_related = %s 
               ORDER BY r.uploaded_at DESC""",
            (session['user_course'],)
        )
        resources = cursor.fetchall()
        
        # Get user's uploaded resources for dashboard
        cursor.execute(
            """SELECT * FROM resources 
               WHERE user_id = %s 
               ORDER BY uploaded_at DESC 
               LIMIT 6""",
            (session['user_id'],)
        )
        user_resources = cursor.fetchall()
        
    except mysql.connector.Error as e:
        flash(f'Resources error: {e}', 'error')
        courses = []
        resources = []
        user_resources = []
    finally:
        cursor.close()
        conn.close()
    
    return render_template('resources.html', 
                         resources=resources, 
                         courses=courses,
                         user_resources=user_resources)

@app.route('/upload_resource', methods=['POST'])
def upload_resource():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'file' not in request.files:
        flash('No file selected!', 'error')
        return redirect(url_for('resources'))
    
    file = request.files['file']
    resource_name = request.form['resource_name']
    resource_type = request.form['resource_type']
    description = request.form['description']
    course_related = request.form['course_related']
    
    if file.filename == '':
        flash('No file selected!', 'error')
        return redirect(url_for('resources'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            # Save file
            file.save(file_path)
            
            # Get file size
            file_size = get_file_size(file_path)
            
            conn = get_db_connection()
            if conn is None:
                flash('Database connection error!', 'error')
                return redirect(url_for('resources'))
                
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO resources 
                   (user_id, resource_name, file_name, resource_type, file_path, file_size, description, course_related) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (session['user_id'], resource_name, filename, resource_type, file_path, file_size, description, course_related)
            )
            conn.commit()
            
            cursor.close()
            conn.close()
            
            flash('Resource uploaded successfully!', 'success')
        except Exception as e:
            flash(f'Error uploading file: {e}', 'error')
    else:
        flash('Invalid file type! Allowed types: pdf, doc, docx, txt, jpg, jpeg, png', 'error')
    
    return redirect(url_for('resources'))

def get_file_size(file_path):
    """Get human readable file size"""
    size = os.path.getsize(file_path)
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size/1024:.1f} KB"
    else:
        return f"{size/(1024*1024):.1f} MB"

@app.route('/view_resource/<int:resource_id>')
def view_resource(resource_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        return "Database connection error", 500
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute(
            """SELECT r.*, u.name as uploader_name 
               FROM resources r 
               JOIN users u ON r.user_id = u.id 
               WHERE r.id = %s""",
            (resource_id,)
        )
        resource = cursor.fetchone()
        
        if resource:
            # Check if file exists
            if os.path.exists(resource['file_path']):
                # For PDFs and images, send the file
                if resource['file_name'].lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                    return send_file(resource['file_path'])
                else:
                    # For other files, force download
                    return send_file(resource['file_path'], as_attachment=False)
            else:
                return "File not found", 404
        else:
            return "Resource not found", 404
    except mysql.connector.Error as e:
        return f"Database error: {e}", 500
    finally:
        cursor.close()
        conn.close()

@app.route('/delete_resource/<int:resource_id>')
def delete_resource(resource_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('resources'))
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if resource belongs to user
        cursor.execute("SELECT * FROM resources WHERE id = %s AND user_id = %s", (resource_id, session['user_id']))
        resource = cursor.fetchone()
        
        if resource:
            # Delete file from filesystem
            if os.path.exists(resource['file_path']):
                os.remove(resource['file_path'])
            
            # Delete from database
            cursor.execute("DELETE FROM resources WHERE id = %s", (resource_id,))
            conn.commit()
            flash('Resource deleted successfully!', 'success')
        else:
            flash('Resource not found or you dont have permission to delete!', 'error')
    except mysql.connector.Error as e:
        flash(f'Error deleting resource: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('resources'))

@app.route('/download_resource/<int:resource_id>')
def download_resource(resource_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('resources'))
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
        resource = cursor.fetchone()
        
        if resource and os.path.exists(resource['file_path']):
            return send_file(resource['file_path'], as_attachment=True, download_name=resource['file_name'])
        else:
            flash('Resource not found!', 'error')
    except mysql.connector.Error as e:
        flash(f'Error downloading resource: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('resources'))

@app.route('/get_resource_info/<int:resource_id>')
def get_resource_info(resource_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection error'}), 500
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute(
            """SELECT r.*, u.name as uploader_name 
               FROM resources r 
               JOIN users u ON r.user_id = u.id 
               WHERE r.id = %s""",
            (resource_id,)
        )
        resource = cursor.fetchone()
        
        if resource:
            return jsonify({
                'id': resource['id'],
                'resource_name': resource['resource_name'],
                'file_name': resource['file_name'],
                'resource_type': resource['resource_type'],
                'file_size': resource['file_size'],
                'description': resource['description'],
                'course_related': resource['course_related'],
                'uploader_name': resource['uploader_name'],
                'uploaded_at': resource['uploaded_at'].strftime('%Y-%m-%d %H:%M:%S') if resource['uploaded_at'] else '',
                'can_delete': resource['user_id'] == session['user_id']
            })
        else:
            return jsonify({'error': 'Resource not found'}), 404
    except mysql.connector.Error as e:
        return jsonify({'error': f'Database error: {e}'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/update_profile', methods=['GET', 'POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('dashboard'))
        
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form['name']
            course = request.form['course']
            school_name = request.form.get('school_name', '')
            university = request.form.get('university', '')
            state = request.form.get('state', '')
            district = request.form.get('district', '')
            address = request.form.get('address', '')
            phone_number = request.form.get('phone_number', '')
            semester = request.form.get('semester', '')
            academic_year = request.form.get('academic_year', '')
            roll_number = request.form.get('roll_number', '')
            
            # Update user profile
            cursor.execute(
                """UPDATE users SET 
                    name = %s, course = %s, school_name = %s, university = %s,
                    state = %s, district = %s, address = %s, phone_number = %s,
                    semester = %s, academic_year = %s, roll_number = %s
                WHERE id = %s""",
                (name, course, school_name, university, state, district, address,
                 phone_number, semester, academic_year, roll_number, session['user_id'])
            )
            conn.commit()
            
            # Update session data
            session['user_name'] = name
            session['user_course'] = course
            
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('dashboard'))
            
        except mysql.connector.Error as e:
            flash(f'Error updating profile: {e}', 'error')
    
    # Get current user data for both GET and POST (in case of errors)
    try:
        cursor.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
        user_data = cursor.fetchone()
    except mysql.connector.Error as e:
        flash(f'Error loading profile data: {e}', 'error')
        user_data = {}
    finally:
        cursor.close()
        conn.close()
    
    return render_template('update_profile.html', user_data=user_data)

@app.route('/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    
    if new_password != confirm_password:
        flash('New passwords do not match!', 'error')
        return redirect(url_for('update_profile'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('update_profile'))
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify current password
        cursor.execute("SELECT password FROM users WHERE id = %s", (session['user_id'],))
        user = cursor.fetchone()
        
        if user and user['password'] == current_password:
            # Update password
            cursor.execute(
                "UPDATE users SET password = %s WHERE id = %s",
                (new_password, session['user_id'])
            )
            conn.commit()
            flash('Password changed successfully!', 'success')
        else:
            flash('Current password is incorrect!', 'error')
    except mysql.connector.Error as e:
        flash(f'Error changing password: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('update_profile'))

@app.route('/change_theme', methods=['POST'])
def change_theme():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    theme = request.form['theme']
    
    conn = get_db_connection()
    if conn is None:
        flash('Database connection error!', 'error')
        return redirect(url_for('update_profile'))
        
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "UPDATE users SET theme = %s WHERE id = %s",
            (theme, session['user_id'])
        )
        conn.commit()
        session['theme'] = theme
        flash('Theme updated successfully!', 'success')
    except mysql.connector.Error as e:
        flash(f'Error updating theme: {e}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('update_profile'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)