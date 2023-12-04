from flask import Flask, render_template, request, redirect, url_for, flash, session
from hashlib import sha256
import hashlib
from flask_sqlalchemy import SQLAlchemy
import random
import string
from flask_socketio import SocketIO, emit, join_room
from difflib import SequenceMatcher
import sqlite3 as sql
from random import randint
import eventlet
import time
import pandas as pd
from flask_migrate import Migrate
import colorlog

# Configure colorlog
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(levelname)s:%(name)s:%(message)s'))

logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel(colorlog.DEBUG)

db = SQLAlchemy()
app = Flask(__name__)
socketio = SocketIO(app)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///project.db"
app.config["SECRET_KEY"] = "vT1$n&8iD4gY7oR2cVbN9LmK3jX6zQ5wM0hA8sE4fB7pZ2xW6uJ1"
db.init_app(app)
migrate = Migrate(app, db)


# Import the association table
users_rooms = db.Table('users_rooms',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('room_id', db.Integer, db.ForeignKey('room.id'))
)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    code = db.Column(db.String(10), unique=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    creator = db.relationship("User", backref=db.backref("created_rooms", lazy=True))
    connected_users = db.relationship('User', secondary=users_rooms, backref=db.backref('connected_rooms', lazy=True))

    def get_connected_users(self):
        return [user.username for user in self.connected_users]



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    password = db.Column(db.String(120))
    readiness = db.Column(db.String(10), default='Not Ready')
    code = db.Column(db.String(10), nullable=True)
    light_status = db.Column(db.String(10), default='off')
    active_message = db.Column(db.String(200), default='off')

    def __init__(self, username, password, code):
        self.username = username
        self.password = password
        self.code = code
    
    rooms = db.relationship('Room', secondary=users_rooms, back_populates='connected_users', overlaps='connected_rooms')


    def __repr__(self):
        return "<User %r>" % self.username

with app.app_context():
    db.create_all()


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user = User.query.get(user_id)

    if not user:
        return redirect(url_for("login"))

    created_rooms = user.created_rooms if user.created_rooms else []
    rooms = Room.query.all()
    return render_template(
        "home.html", username=user.username, created_rooms=created_rooms, rooms=rooms
    )


@app.route("/users/create", methods=["GET", "POST"])
def user_create():
    if request.method == "POST":
        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]
            code = generate_random_code()

            existing_user = User.query.filter(
                db.or_(User.username == username)
            ).first()

            if existing_user:
                if existing_user.username == username:
                    flash("Username already exists.")
                return redirect(url_for("auth"))
            else:
                # Create a new user
                hashed_password = hashlib.sha256(password.encode()).hexdigest()
                new_user = User(
                    username=username, password=hashed_password, code=code
                )
                db.session.add(new_user)
                db.session.commit()
                flash("User successfully registered!")
                return redirect(url_for("login"))

    return render_template("user/create.html")


@app.route("/user/<int:id>")
def user_detail(id):
    user = User.query.get(id)
    return render_template("user/detail.html", user=user)


@app.route("/users")
def auth():
    return render_template("signUp.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user:
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            if user.password == hashed_password:
                session["logged_in"] = True
                session["username"] = user.username
                session["user_id"] = user.id
                flash("Login successful!")
                return redirect(url_for("home"))
            else:
                flash("Incorrect password!")
        else:
            flash("Username not found!")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.")
    return redirect(url_for("login"))


def generate_random_code(length=6):
    characters = string.digits
    code = "".join(random.choice(characters) for _ in range(length))
    return code


@app.route("/room/<code>")
def room_detail(code):
    if "user_id" not in session:
        return redirect(url_for("login"))
    room = Room.query.filter_by(code=code).first()
    user_id = session["user_id"]
    user = User.query.get(user_id)
    if not room:
        flash("Room not found.")
        return redirect(url_for("home"))
    if user_id == room.creator_id:
        return render_template("room/creator_detail.html", room=room, username=user.username)
    else:
        return render_template("room/detail.html", room=room, username=user.username)


@app.route("/room/<code>/play")
def start_game(code):
    if "user_id" not in session:
        return redirect(url_for("login"))
    room = Room.query.filter_by(code=code).first()
    user_id = session["user_id"]
    if user_id != room.creator_id:
        flash("You are not the host")
        return redirect(url_for('room_detail', code=code))
    else:
        socketio.emit('game_starting', room=code)
        return render_template("/room/game.html", room_code=code, user_id=user_id, room=room)


@app.route("/room")
def room():
    return render_template("room/join.html")

@socketio.on('ready_check')
def handle_ready_check(data):
    room_code = data['room_code']
    emit('redirect_to_ready_check', {'url': url_for('ready_check_creator', code=room_code)}, room=request.sid)
    emit('redirect_to_ready_check', {'url': url_for('ready_check', code=room_code)}, room=room_code)


@app.route('/show/ready_check_creator/<code>')
def ready_check_creator(code):
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id = session["user_id"]
    room = Room.query.filter_by(creator_id=user_id).first()

    if not room:
        flash("Error: Room not found!")
        return redirect(url_for("home"))

    return render_template("show/ready_check_creator.html", room=room, user_id=user_id)


@app.route('/show/ready_check/<code>')
def ready_check(code):
    room = Room.query.filter_by(code=code).first()
    return render_template("show/ready_check.html", room=room)

@app.route('/show/active/<code>')
def active(code):
    room = Room.query.filter_by(code=code).first()
    user = User.query.get(session["user_id"])
    #set all users to have the light colour black
    user.light_status = "#000000"
    db.session.commit()
    return render_template("show/active.html", room=room, user_id=user.id, username=user.username)

@app.route('/show/active/<code>/host')
def active_host(code):
    room = Room.query.filter_by(code=code).first()
    user = User.query.get(session["user_id"])
    for user in room.connected_users:
        user.light_status = "#000000"
    return render_template("show/active_creator.html", room=room, username=user.username)

@socketio.on('user_ready_status')
def handle_user_ready_status(data):
    print("Received user_ready_status event with data:", data)
    room_code = data['room_code']
    user_status = data['status']
    user_id = session["user_id"]
    user = User.query.get(user_id)
    print(f"User {user_id} is {user_status} in room {room_code}")

    socketio.emit('update_ready_status', {'user_id': user_id, 'status': user_status}, room=room_code)

@socketio.on("join_room")
def handle_join_room(data):
    print("Received join_room event with data:", data)
    room_code = data["room_code"]
    user_id = session["user_id"]
    room_id = data['room_id']

    print(f"Received join_room event. room_code: {room_code}, user_id: {user_id}")

    room = Room.query.get(room_id)
    user = User.query.get(user_id)

    if room and user:
        if user not in room.connected_users:
            room.connected_users.append(user)
            db.session.commit()

        connected_users = [u.username for u in room.connected_users]
        print(f"Emitting connected_users_update event. users: {connected_users}")
        join_room(room_code)
        print(f"User {user_id} joined room {room_code}.")

        socketio.emit(
            "connected_users_update", {"users": connected_users}, room=room_code
        )
        print(f"Emitting connected_users_update for room {room_code} with users {connected_users}")


@app.route("/rooms/create", methods=["GET", "POST"])
def room_create():
    if request.method == "POST":
        name = request.form["name"]
        code = generate_random_code()

        new_room = Room(name=name, code=code, creator_id=session["user_id"])
        db.session.add(new_room)
        db.session.commit()

        user = User.query.get(session["user_id"])
        user.code = code
        db.session.commit()

        socketio.emit(
            "room_created", {"room_code": new_room.code, "room_name": new_room.name}
        )

        flash("Room created successfully!")
        return redirect(url_for("room_detail", code=new_room.code))

    user = User.query.get(session["user_id"])

    return render_template("room/create.html", username=user.username)


@app.route("/join", methods=["POST"])
def join_room_route():
    room_code = request.form.get("room_code")
    user_id = session.get("user_id")

    if not room_code or not user_id:
        flash("An error occurred. Please try again.")
        return redirect(url_for("home"))

    room = Room.query.get(room_code)
    user = User.query.get(user_id)

    if not room or not user:
        flash("An error occurred. Please try again.")
        return redirect(url_for("home"))

    if user not in room.connected_users:
        room.connected_users.append(user)
        db.session.commit()

        socketio.emit(
            "connected_users_update",
            {"users": room.get_connected_users()},
            room=room_code,
        )

    return redirect(url_for("room_detail", id=room_code))


@socketio.on("leave_room")
def handle_leave_room_event(data):
    room_code = data["room_code"]
    user_id = session["user_id"]
    room = Room.query.filter_by(code=room_code).first()
    user = User.query.get(user_id)

    if room and user and user in room.connected_users:
        #check if leaving user is host
        if user_id == room.creator_id:
            #if host, delete room
            db.session.delete(room)
            db.session.commit()
            print(f"User {user_id} deleted room {room_code}")
        else:
            #if not host, remove user from room
            room.connected_users.remove(user)
            db.session.commit()

            connected_users = [u.username for u in room.connected_users]
            print(f"Emitting connected_users_update for room {room_code} with users {connected_users}")
            socketio.emit("connected_users_update", {"users": connected_users}, room=room_code)
        
        emit("left_room", {}, room=request.sid)

@socketio.on("user_ready_status")
def handle_user_ready_status(data):
    user_id = session["user_id"]
    room_code = data["room_code"]
    status = data["status"]
    print("Received user_ready_status event with data:", data)

    user = User.query.get(user_id)
    room = Room.query.filter_by(code=room_code).first()

    if user and room:
        user.readiness = status
        db.session.commit()
        print(f"User {user_id} is {status} in room {room_code}")

        # Broadcasting the updated readiness status
        ready_users = [u.username for u in room.connected_users if u.readiness == "Ready"]
        not_ready_users = [u.username for u in room.connected_users if u.readiness == "Not Ready"]
        print(f"Emitting update_user_status event. ready_users: {ready_users}, not_ready_users: {not_ready_users}, in room: {room_code}")
        socketio.emit("update_user_status", {"ready_users": ready_users, "not_ready_users": not_ready_users}, room=room_code)

@socketio.on("start_show")
def handle_start_show(data):
    room_code = data["room_code"]
    user_id = session["user_id"]
    room = Room.query.filter_by(code=room_code).first()
    user = User.query.get(user_id)
    url = url_for('active', code=room_code)
    print("Received start_show event with data:", data, url)
    #sends url and the user id in redirect
    if room and user:
        print(f"User {user_id} is starting show in room {room_code}")
        emit("redirect_to_active", {"url": url, "user_id": user_id}, room=room_code)

@socketio.on("fetch_light_status")
def fetch_light_status(data):
    room_code = data["room_code"]
    user_id = session["user_id"]
    room = Room.query.filter_by(code=room_code).first()
    user = User.query.get(user_id)
    #return the data in the format: {"users": {"user_id": {"username": "username", "light_status": "#ffffff"}}}
    print("Received fetch_light_status event with data:", data)
    if room and user:
        print(f"User {user_id} is fetching light status in room {room_code}")
        users = {}
        for user in room.connected_users:
            users[user.id] = {"username": user.username, "light_status": user.light_status}
            print(f"User {user.id} has light status {user.light_status}")
        emit("light_status_fetched", {"users": users}, room=room_code)

@socketio.on("update_light_status")
def update_light_status(data):
    room_code = data["room_code"]
    user_id = session["user_id"]
    room = Room.query.filter_by(code=room_code).first()
    user = User.query.get(user_id)
    print("Received update_light_status event with data:", data)
    users = {}
    if room and user:
        print(f"User {user_id} is updating light status in room {room_code}")
        for user in room.connected_users:
            users[user.id] = {"username": user.username, "light_status": user.light_status}
            print(f"User {user.id} has light status {user.light_status}")
        print(f"Emitting light_status_updated event. users: {users}")
        emit("light_status_updated", {"users": users}, room=room_code)

@socketio.on("color_event")
def handle_color_event(data):
    room_code = data["room_code"]
    user_id = session["user_id"]
    room = Room.query.filter_by(code=room_code).first()
    user = User.query.get(user_id)
    print("Received color_event event with data:", data)
    if room and user:
        print(f"User {user_id} is changing light color in room {room_code}")
        for user in room.connected_users:
            if user.username == data["username"]:
                user.light_status = data["color"]
                db.session.commit()
                print(f"User {user.id} has light status {user.light_status}")
        for user in room.connected_users:
            users = {}
            users[user.id] = {"username": user.username, "light_status": user.light_status}
        print(f"Emitting light_status_updated event. users: {users}")
        emit("light_status_updated", {"users": users}, room=room_code)
        emit("host_reload", {}, room=room_code)

@socketio.on("message_event")
def handle_color_event(data):
    room_code = data["room_code"]
    user_id = session["user_id"]
    room = Room.query.filter_by(code=room_code).first()
    user = User.query.get(user_id)
    #info logged in terminal
    logger.debug("Received message_event event with data:", data)
    if room and user:
        print(f"User {user_id} is changing light color in room {room_code}")
        for user in room.connected_users:
            if user.username == data["username"]:
                user.active_message = data["message"]
                db.session.commit()
                print(f"User {user.id} has message {user.active_message}")
        for user in room.connected_users:
            users = {}
            users[user.id] = {"username": user.username, "active_message": user.active_message}
        print(f"Emitting message_status_updated event. users: {users}")
        emit("message_status_updated", {"users": users}, room=room_code)
        emit("host_reload", {}, room=room_code)

if __name__ == "__main__":
    eventlet.wsgi.server(eventlet.listen(("192.168.86.94", 5000)), app)
    socketio.run(app)