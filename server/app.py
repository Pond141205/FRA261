from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
import os, pytz
from werkzeug.security import generate_password_hash, check_password_hash

# ===========================================================
#   Flask App Config + SQLite Setup
# ===========================================================

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # ต้องมีเพื่อใช้ session + flash

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'Database', 'Server_db.sqlite3')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 30},
    'pool_timeout': 30
}

db = SQLAlchemy(app)

# Enable WAL mode for SQLite (เพิ่มความเร็ว)
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

with app.app_context():
    engine = db.engine
    event.listen(engine, "connect", set_sqlite_pragma)

# ===========================================================
#   Database Models
# ===========================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")  # admin หรือ user
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class SiloData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    device_id = db.Column(db.String(50))
    batch_id = db.Column(db.String(100))
    total_chunks = db.Column(db.Integer)
    chunk_id = db.Column(db.Integer)
    point_cloud = db.Column(db.Text)
    __table_args__ = (db.UniqueConstraint('batch_id', 'chunk_id', name='_batch_chunk_uc'),)


class MergedData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    device_id = db.Column(db.String(50))
    batch_id = db.Column(db.String(100))
    total_points = db.Column(db.Integer)
    merged_points = db.Column(db.Text)
    mesh_processed = db.Column(db.Boolean, default=False, nullable=False)


class VolumeData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    device_id = db.Column(db.String(50))
    volume = db.Column(db.Float)


class SiloMeta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True)
    plant_type = db.Column(db.String(50))
    province = db.Column(db.String(50))
    site_code = db.Column(db.String(20))
    silo_no = db.Column(db.String(10))


# ===========================================================
#   Initialize Database Folder + Tables
# ===========================================================

if not os.path.exists('Database'):
    os.makedirs('Database')

with app.app_context():
    db.create_all()

# ===========================================================
#   Merge Function
# ===========================================================

merged_batches = set()

def try_merge(batch_id, total_chunks, device_id):
    if batch_id in merged_batches:
        return None

    chunks = SiloData.query.filter_by(batch_id=batch_id).order_by(SiloData.chunk_id).all()
    if len(chunks) != total_chunks:
        return None

    all_points_text = "".join([c.point_cloud for c in chunks])
    total_points = len(all_points_text.splitlines())
    merged_record = MergedData(
        timestamp=chunks[0].timestamp,
        device_id=device_id,
        batch_id=batch_id,
        total_points=total_points,
        merged_points=all_points_text
    )

    try:
        db.session.add(merged_record)
        db.session.commit()
        merged_batches.add(batch_id)
        return True
    except Exception:
        db.session.rollback()
        return None

# ===========================================================
#   Auth Decorators
# ===========================================================

def login_required(f):
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def admin_required(f):
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect("/login")
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def user_required(f):
    def wrapper(*args, **kwargs):
        if session.get("role") != "user":
            return redirect("/login")
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# ===========================================================
#   Routes: Login / Logout / Dashboard
# ===========================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("user_dashboard"))
        error = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html", username=session.get("username"))


@app.route("/user/dashboard")
@user_required
def user_dashboard():
    return render_template("user_dashboard.html", username=session.get("username"))

# ===========================================================
#   Admin API: Users + Silo
# ===========================================================

@app.route("/admin/users", methods=["GET"])
@admin_required
def list_users():
    users = User.query.all()
    return jsonify([{"id": u.id, "username": u.username, "role": u.role} for u in users])


@app.route("/admin/users/<int:user_id>", methods=["PUT"])
@admin_required
def edit_user(user_id):
    data = request.get_json()
    user = User.query.get_or_404(user_id)

    if "username" in data:
        user.username = data["username"]
    if "password" in data:
        user.set_password(data["password"])
    if "role" in data:
        user.role = data["role"]

    db.session.commit()
    return jsonify({"status": "ok", "msg": "User updated"})


@app.route("/admin/silo/<int:silo_id>", methods=["PUT"])
@admin_required
def edit_silo(silo_id):
    data = request.get_json()
    silo = SiloMeta.query.get_or_404(silo_id)

    for field in ["plant_type", "province", "site_code", "silo_no"]:
        if field in data:
            setattr(silo, field, data[field])

    db.session.commit()
    return jsonify({"status": "ok", "msg": "Silo updated"})


@app.route("/admin/silo", methods=["POST"])
@admin_required
def add_silo():
    data = request.get_json()
    new_silo = SiloMeta(
        device_id=data["device_id"],
        plant_type=data.get("plant_type", ""),
        province=data.get("province", ""),
        site_code=data.get("site_code", ""),
        silo_no=data.get("silo_no", "")
    )
    db.session.add(new_silo)
    db.session.commit()
    return jsonify({"status": "ok", "msg": "New silo added"})

# ===========================================================
#   Upload Chunk API
# ===========================================================

@app.route("/upload_chunk", methods=["POST"])
def upload_chunk():
    try:
        device_id = request.headers.get("X-Device-ID")
        total_chunks = request.headers.get("X-Total-Chunks")
        chunk_id = request.headers.get("X-Chunk-ID")
        batch_id = request.headers.get("X-Batch-ID")

        if not device_id or not total_chunks or not chunk_id:
            return jsonify({"status":"error","msg":"Missing headers"}), 400

        point_data = request.data.decode('utf-8', errors='ignore')
        if not point_data:
            return jsonify({"status":"error","msg":"Empty payload"}), 400

        silo = SiloMeta.query.filter_by(device_id=device_id).first()
        if not silo:
            return jsonify({"status":"error","msg":"Unknown device_id"}), 400

        record = SiloData(
            device_id=device_id,
            batch_id=batch_id,
            timestamp=datetime.now(timezone.utc).astimezone(pytz.timezone('Asia/Bangkok')),
            total_chunks=int(total_chunks),
            chunk_id=int(chunk_id),
            point_cloud=point_data
        )

        try:
            db.session.add(record)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()

        merge_success = try_merge(batch_id, int(total_chunks), device_id)
        if merge_success:
            return jsonify({"status":"ok","msg":"Batch merged"})

        return jsonify({"status":"ok","msg":"Chunk saved"})

    except Exception as e:
        return jsonify({"status":"error","msg":str(e)}), 500

    
# -------------------------------
# Run Server
#cmd run
#cd "C:\Users\POND\OneDrive\Documents\AllProject\FRA262 studio\Phase 2\code\server"
#venv\Scripts\activate
#ngrok http 5000
# https://unconserving-madelyn-glottogonic.ngrok-free.dev/login
# -------------------------------

# ------------------ Run Server ------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)