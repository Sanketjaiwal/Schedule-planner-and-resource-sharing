CREATE DATABASE IF NOT EXISTS schedule_planner;
USE schedule_planner;

-- Users table with extended fields
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    course VARCHAR(100) NOT NULL,
    school_name VARCHAR(255),
    university VARCHAR(255),
    state VARCHAR(100),
    district VARCHAR(100),
    address TEXT,
    phone_number VARCHAR(20),
    semester VARCHAR(50),
    academic_year VARCHAR(50),
    roll_number VARCHAR(50),
    theme VARCHAR(20) DEFAULT 'light',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Timetable table
CREATE TABLE timetable (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    day ENUM('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday') NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    activity_type ENUM('college', 'personal') NOT NULL,
    description VARCHAR(255) NOT NULL,
    subject VARCHAR(100),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Tasks table
CREATE TABLE tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    task_name VARCHAR(255) NOT NULL,
    description TEXT,
    due_date DATETIME NOT NULL,
    reminder_sent_1hour BOOLEAN DEFAULT FALSE,
    reminder_sent_1day BOOLEAN DEFAULT FALSE,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Reserved Time table
CREATE TABLE reserved_time (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    title VARCHAR(255),
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    days JSON NOT NULL, -- Stores array of days ['Monday', 'Tuesday', ...]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Resources table
CREATE TABLE resources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    course VARCHAR(100) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    description TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

