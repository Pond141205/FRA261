from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
import os, pytz
from werkzeug.security import generate_password_hash, check_password_hash

# ------------------ Flask App & SQLite Setup ------------------
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # ต้องมีเพื่อใช้ flash

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'Database', 'Server_db.sqlite3')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 30},
    'pool_timeout': 30
}

db = SQLAlchemy(app)

# Enable WAL mode for SQLite
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

with app.app_context():
    engine = db.engine
    event.listen(engine, "connect", set_sqlite_pragma)

# ------------------ Models ------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")  # "admin" or "user"
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

# ------------------ Initialize DB ------------------
if not os.path.exists('Database'):
    os.makedirs('Database')

with app.app_context():
    db.create_all()

# ------------------ Merge Logic ------------------
merged_batches = set()

def try_merge(batch_id, total_chunks, device_id):
    if batch_id in merged_batches:
        return None
    chunks = SiloData.query.filter_by(batch_id=batch_id).order_by(SiloData.chunk_id).all()
    current_chunk_count = len(chunks)
    if total_chunks is None or total_chunks == 0:
        print(f"[{device_id}] total_chunks not set in payload!")
        return None
    if current_chunk_count != total_chunks:
        print(f"[{device_id}] Waiting for all chunks: {current_chunk_count}/{total_chunks}")
        return None
    batch_timestamp = chunks[0].timestamp
    all_points_text = "".join([c.point_cloud for c in chunks])
    total_points = len(all_points_text.splitlines())
    print(f"[{device_id}] [Batch_id: {batch_id}] Merge complete: ~{total_points} points")
    merged_record = MergedData(
        timestamp=batch_timestamp,
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
    except Exception as e:
        db.session.rollback()
        print(f"Error saving MergedData for batch {batch_id}: {e}")
        return None

# ------------------ Routes ------------------

# Login Page (HTML)
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            # Login success -> redirect ตาม role
            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("user_dashboard"))
        else:
            error = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
    return render_template("login.html", error=error)

# Dashboard routes
@app.route("/admin/dashboard")
def admin_dashboard():
    return "นี่คือหน้า Dashboard ของ Admin"

@app.route("/user/dashboard")
def user_dashboard():
    return "นี่คือหน้า Dashboard ของ User"

# Admin manage users (API)
@app.route("/admin/users", methods=["GET"])
def list_users():
    users = User.query.all()
    return jsonify([{"id": u.id, "username": u.username, "role": u.role} for u in users])

@app.route("/admin/users/<int:user_id>", methods=["PUT"])
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

# Admin manage SiloMeta
@app.route("/admin/silo/<int:silo_id>", methods=["PUT"])
def edit_silo(silo_id):
    data = request.get_json()
    silo = SiloMeta.query.get_or_404(silo_id)
    if "plant_type" in data:
        silo.plant_type = data["plant_type"]
    if "province" in data:
        silo.province = data["province"]
    if "site_code" in data:
        silo.site_code = data["site_code"]
    if "silo_no" in data:
        silo.silo_no = data["silo_no"]
    db.session.commit()
    return jsonify({"status": "ok", "msg": "Silo updated"})

@app.route("/admin/silo", methods=["POST"])
def add_silo():
    data = request.get_json()
    new_silo = SiloMeta(
        device_id = data["device_id"],
        plant_type = data.get("plant_type", ""),
        province = data.get("province", ""),
        site_code = data.get("site_code", ""),
        silo_no = data.get("silo_no", "")
    )
    db.session.add(new_silo)
    db.session.commit()
    return jsonify({"status":"ok","msg":"New silo added"})

# Upload chunk
@app.route("/upload_chunk", methods=["POST"])
def upload_chunk():
    device_id = "UNKNOWN_DEVICE"
    batch_id = None
    total_chunks = None
    try:
        device_id = request.headers.get("X-Device-ID")
        total_chunks_str = request.headers.get("X-Total-Chunks")
        chunk_id_str = request.headers.get("X-Chunk-ID")
        batch_id = request.headers.get("X-Batch-ID")
        if not device_id:
            return jsonify({"status":"error","msg":"Missing X-Device-ID header"}), 400
        if not total_chunks_str or not chunk_id_str:
            return jsonify({"status":"error","msg":"Missing chunk headers"}), 400
        point_data = request.data.decode('utf-8', errors='ignore')
        if not point_data:
            return jsonify({"status":"error","msg":"Empty payload"}), 400
        total_chunks = int(total_chunks_str)
        chunk_id = int(chunk_id_str)
        silo = SiloMeta.query.filter_by(device_id=device_id).first()
        if not silo:
            return jsonify({"status":"error","msg":"Unknown device_id"}), 400
        thailand_tz = pytz.timezone('Asia/Bangkok')
        current_time_thailand = datetime.now(timezone.utc).astimezone(thailand_tz)
        record = SiloData(
            device_id = silo.device_id,
            batch_id = batch_id,
            timestamp = current_time_thailand,
            total_chunks = total_chunks,
            chunk_id = chunk_id,
            point_cloud = point_data
        )
        try:
            db.session.add(record)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            print(f"Chunk {chunk_id}/{total_chunks} from {device_id} ALREADY EXISTS. Checking for merge.")
        except Exception as e:
            db.session.rollback()
            raise e
        print(f"Received chunk {chunk_id}/{total_chunks} from {device_id} (Batch: {batch_id})")
        merge_success = try_merge(batch_id, total_chunks, device_id)
        if merge_success:
            return jsonify({"status":"ok","msg":f"Chunk {chunk_id} saved. Batch MERGED successfully."})
        else:
            return jsonify({"status":"ok","msg":f"Chunk {chunk_id} saved. Waiting for more chunks."})
    except Exception as e:
        print(f"Exception for device {device_id}:", e)
        if "database is locked" in str(e):
            return jsonify({"status":"error","msg":"Database is temporarily busy. Please retry shortly."}), 503
        return jsonify({"status":"error","msg":str(e)}), 500

    
# -------------------------------
# Run Server
#cmd run
#cd "C:\Users\POND\OneDrive\Documents\AllProject\FRA262 studio\Phase 2\code\server"
#venv\Scripts\activate
#ngrok http 5000
# -------------------------------

# ------------------ Run Server ------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
