from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, desc, ForeignKey
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone, timedelta
import os, pytz
from werkzeug.security import generate_password_hash, check_password_hash

# ------------------ Flask App & SQLite Setup ------------------
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# สร้างโฟลเดอร์ Database ถ้ายังไม่มี
if not os.path.exists(os.path.join(basedir, 'Database')):
    os.makedirs(os.path.join(basedir, 'Database'))

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'Database', 'Server_db.sqlite3')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 30},
    'pool_timeout': 30
}

db = SQLAlchemy(app)

# ------------------ Models ------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)
    deleted_at = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def soft_delete(self):
        self.is_active = False
        self.deleted_at = datetime.now(timezone.utc)
        self.username = f"deleted_{self.id}_{self.username}"

class UserBranchAccess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    province = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('User', backref=db.backref('branch_access', lazy=True, cascade='all, delete-orphan'))

    __table_args__ = (db.UniqueConstraint('user_id', 'province', name='_user_province_uc'),)

class SiloMeta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True, nullable=False)
    plant_type = db.Column(db.String(50))
    province = db.Column(db.String(50))
    site_code = db.Column(db.String(20))
    silo_no = db.Column(db.String(10))
    capacity = db.Column(db.Float, default=1000.0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    volume_data = db.relationship('VolumeData', backref='silo', lazy=True, cascade='all, delete-orphan')
    silo_data = db.relationship('SiloData', backref='silo', lazy=True, cascade='all, delete-orphan')
    merged_data = db.relationship('MergedData', backref='silo', lazy=True, cascade='all, delete-orphan')

class VolumeData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), db.ForeignKey('silo_meta.device_id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    volume = db.Column(db.Float)
    volume_percentage = db.Column(db.Float)

class SiloData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), db.ForeignKey('silo_meta.device_id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    batch_id = db.Column(db.String(100))
    total_chunks = db.Column(db.Integer)
    chunk_id = db.Column(db.Integer)
    point_cloud = db.Column(db.Text)
    
    __table_args__ = (db.UniqueConstraint('batch_id', 'chunk_id', name='_batch_chunk_uc'),)

class MergedData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), db.ForeignKey('silo_meta.device_id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    batch_id = db.Column(db.String(100))
    total_points = db.Column(db.Integer)
    merged_points = db.Column(db.Text)
    mesh_processed = db.Column(db.Boolean, default=False, nullable=False)

# ------------------ Initialize DB ------------------
def init_db():
    with app.app_context():
        @event.listens_for(db.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        
        db.create_all()
        print("Database initialized successfully!")

init_db()

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
        device_id=device_id,
        timestamp=batch_timestamp,
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

@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        # ✅ แก้ไข: ตรวจสอบเฉพาะ user ที่ active
        user = User.query.filter_by(username=username, is_active=True).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("user_dashboard"))
        else:
            error = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/admin/dashboard")
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template("admin_dashboard.html")

@app.route("/user/dashboard")
def user_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("user_dashboard.html")

# API สำหรับดึงข้อมูลตามสิทธิ์ผู้ใช้
@app.route("/api/user_branches")
def get_user_branches():
    if 'user_id' not in session:
        return jsonify([])
    
    user_id = session['user_id']
    user = User.query.filter_by(id=user_id, is_active=True).first()
    
    if user.role == 'admin':
        branches = db.session.query(SiloMeta.province).distinct().all()
        return jsonify([branch[0] for branch in branches])
    else:
        user_branches = UserBranchAccess.query.filter_by(user_id=user_id).all()
        return jsonify([branch.province for branch in user_branches])

@app.route("/api/volume_data")
def get_volume_data():
    try:
        if 'user_id' not in session:
            return jsonify({"error": "Unauthorized"}), 401
            
        user_id = session['user_id']
        user = User.query.get(user_id)
        
        subquery = db.session.query(
            VolumeData.device_id,
            db.func.max(VolumeData.timestamp).label('max_timestamp')
        ).group_by(VolumeData.device_id).subquery()

        query = db.session.query(VolumeData).join(
            subquery,
            (VolumeData.device_id == subquery.c.device_id) & 
            (VolumeData.timestamp == subquery.c.max_timestamp)
        ).join(SiloMeta, VolumeData.device_id == SiloMeta.device_id)
        
        if user.role == 'user':
            user_branches = UserBranchAccess.query.filter_by(user_id=user_id).all()
            if not user_branches:
                return jsonify([])
            allowed_provinces = [branch.province for branch in user_branches]
            query = query.filter(SiloMeta.province.in_(allowed_provinces))

        latest_volumes = query.all()

        result = []
        for volume in latest_volumes:
            silo = volume.silo
            percentage = (volume.volume / silo.capacity * 100) if silo.capacity else 0
            
            result.append({
                "device_id": volume.device_id,
                "volume": volume.volume,
                "volume_percentage": round(percentage, 1),
                "timestamp": volume.timestamp.isoformat(),
                "plant_type": silo.plant_type,
                "province": silo.province,
                "site_code": silo.site_code,
                "silo_no": silo.silo_no,
                "capacity": silo.capacity
            })

        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/volume_history/<device_id>")
def get_volume_history(device_id):
    try:
        if 'user_id' not in session:
            return jsonify({"error": "Unauthorized"}), 401
            
        user_id = session['user_id']
        user = User.query.get(user_id)
        
        if user.role == 'user':
            silo = SiloMeta.query.filter_by(device_id=device_id).first()
            if not silo:
                return jsonify({"error": "Device not found"}), 404
                
            user_branches = UserBranchAccess.query.filter_by(user_id=user_id).all()
            allowed_provinces = [branch.province for branch in user_branches]
            if silo.province not in allowed_provinces:
                return jsonify({"error": "Access denied"}), 403

        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        
        volumes = VolumeData.query.filter(
            VolumeData.device_id == device_id,
            VolumeData.timestamp >= seven_days_ago
        ).order_by(VolumeData.timestamp).all()

        result = [{
            "timestamp": vol.timestamp.isoformat(),
            "volume": vol.volume,
            "volume_percentage": vol.volume_percentage
        } for vol in volumes]

        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/silos")
def get_silos():
    try:
        if 'user_id' not in session:
            return jsonify({"error": "Unauthorized"}), 401
            
        user_id = session['user_id']
        user = User.query.get(user_id)
        
        query = SiloMeta.query
        
        if user.role == 'user':
            user_branches = UserBranchAccess.query.filter_by(user_id=user_id).all()
            if not user_branches:
                return jsonify([])
            allowed_provinces = [branch.province for branch in user_branches]
            query = query.filter(SiloMeta.province.in_(allowed_provinces))

        silos = query.all()
        result = [{
            "id": silo.id,
            "device_id": silo.device_id,
            "plant_type": silo.plant_type,
            "province": silo.province,
            "site_code": silo.site_code,
            "silo_no": silo.silo_no,
            "capacity": silo.capacity,
            "created_at": silo.created_at.isoformat()
        } for silo in silos]
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API สำหรับจัดการสิทธิ์สาขา
@app.route("/api/admin/user_branches/<int:user_id>", methods=["GET"])
def get_user_branches_admin(user_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        user_branches = UserBranchAccess.query.filter_by(user_id=user_id).all()
        user = User.query.get(user_id)
        
        result = {
            "user_id": user_id,
            "username": user.username if user else "Unknown",
            "provinces": [branch.province for branch in user_branches],
            "branch_count": len(user_branches)
        }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in get_user_branches_admin: {str(e)}")
        return jsonify({"error": f"Failed to retrieve user branches: {str(e)}"}), 500

@app.route("/api/admin/user_branches/<int:user_id>", methods=["POST"])
def update_user_branches(user_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        provinces = data.get('provinces', [])
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
            
        if user.role != 'user':
            return jsonify({"error": "Can only assign branches to users with 'user' role"}), 400
    
        try:
            deleted_count = UserBranchAccess.query.filter_by(user_id=user_id).delete()
            print(f"Deleted {deleted_count} old branch access records for user {user.username}")
            
            for province in provinces:
                user_branch = UserBranchAccess(
                    user_id=user_id,
                    province=province
                )
                db.session.add(user_branch)
                
            db.session.commit()
            
            print(f"Updated user {user.username} with access to {len(provinces)} branches: {', '.join(provinces)}")
            return jsonify({
                "status": "success", 
                "message": f"Updated user branches successfully",
                "branch_count": len(provinces)
            })
            
        except Exception as e:
            db.session.rollback()
            raise e
            
    except Exception as e:
        db.session.rollback()
        print(f"Error in update_user_branches: {str(e)}")
        return jsonify({"error": f"Failed to update user branches: {str(e)}"}), 500

# API สำหรับดึงข้อมูลสาขาทั้งหมด
@app.route("/api/admin/all_branches", methods=["GET"])
def get_all_branches():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        branches = db.session.query(SiloMeta.province).distinct().all()
        provinces = [branch[0] for branch in branches if branch[0]]
        
        branch_stats = []
        for province in provinces:
            silo_count = SiloMeta.query.filter_by(province=province).count()
            branch_stats.append({
                "province": province,
                "silo_count": silo_count
            })
        
        return jsonify(branch_stats)
        
    except Exception as e:
        print(f"Error in get_all_branches: {str(e)}")
        return jsonify({"error": f"Failed to retrieve branches: {str(e)}"}), 500

# API สำหรับตรวจสอบข้อมูลผู้ใช้ปัจจุบัน
@app.route("/api/current_user", methods=["GET"])
def get_current_user():
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    try:
        user_id = session['user_id']
        user = User.query.filter_by(id=user_id, is_active=True).first()
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        user_data = {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "allowed_branches": [],
            "silo_count": 0
        }
        
        if user.role == 'admin':
            user_data["allowed_branches"] = ["ทั้งหมด"]
            user_data["silo_count"] = SiloMeta.query.count()
        else:
            user_branches = UserBranchAccess.query.filter_by(user_id=user_id).all()
            user_data["allowed_branches"] = [branch.province for branch in user_branches]
            
            if user_branches:
                allowed_provinces = [branch.province for branch in user_branches]
                user_data["silo_count"] = SiloMeta.query.filter(SiloMeta.province.in_(allowed_provinces)).count()
        
        return jsonify(user_data)
        
    except Exception as e:
        print(f"Error in get_current_user: {str(e)}")
        return jsonify({"error": f"Failed to retrieve user data: {str(e)}"}), 500

# Admin management APIs
@app.route("/api/admin/users", methods=["GET"])
def list_users():
    """ดึงข้อมูลผู้ใช้ทั้งหมด (Admin only)"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        # ✅ นี้ถูกต้องแล้ว - ดึงเฉพาะ user ที่ active
        users = User.query.filter_by(is_active=True).all()
        result = []
        for u in users:
            user_data = {
                "id": u.id, 
                "username": u.username, 
                "role": u.role,
                "created_at": u.created_at.isoformat(),
                "is_current_user": u.id == session.get('user_id')
            }
            
            if u.role == 'user':
                user_branches = UserBranchAccess.query.filter_by(user_id=u.id).all()
                user_data["allowed_branches"] = [branch.province for branch in user_branches]
                user_data["branch_count"] = len(user_branches)
            else:
                user_data["allowed_branches"] = ["ทั้งหมด"]
                user_data["branch_count"] = "ทั้งหมด"
                
            result.append(user_data)
        
        print(f"Admin {session.get('username')} retrieved {len(result)} active users")
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in list_users: {str(e)}")
        return jsonify({"error": f"Failed to retrieve users: {str(e)}"}), 500

@app.route("/api/admin/users", methods=["POST"])
def add_user():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        if not data.get('username') or not data.get('password'):
            return jsonify({"error": "Username and password are required"}), 400

        if len(data.get('password', '')) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400

        existing_user = User.query.filter_by(username=data['username']).first()
        if existing_user:
            return jsonify({"error": "Username already exists"}), 400

        new_user = User(
            username=data['username'],
            role=data.get('role', 'user')
        )
        new_user.set_password(data['password'])
        
        db.session.add(new_user)
        db.session.commit()
        
        if new_user.role == 'user' and data.get('branches'):
            for province in data['branches']:
                user_branch = UserBranchAccess(
                    user_id=new_user.id,
                    province=province
                )
                db.session.add(user_branch)
            db.session.commit()
            print(f"Created user {new_user.username} with access to {len(data['branches'])} branches")
        else:
            print(f"Created user {new_user.username} with role {new_user.role}")
            
        return jsonify({
            "status": "success", 
            "message": "User created successfully",
            "user_id": new_user.id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in add_user: {str(e)}")
        return jsonify({"error": f"Failed to create user: {str(e)}"}), 500

@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
def edit_user(user_id):
    """แก้ไขข้อมูลผู้ใช้ (Admin only)"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        # ✅ แก้ไข: ดึงเฉพาะ user ที่ active
        user = User.query.filter_by(id=user_id, is_active=True).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # เก็บข้อมูลก่อนแก้ไขสำหรับ logging
        old_username = user.username
        old_role = user.role
        
        # อัพเดทข้อมูลผู้ใช้
        if "username" in data and data["username"] != user.username:
            # ตรวจสอบว่า username ใหม่ไม่ซ้ำ
            existing = User.query.filter_by(username=data["username"], is_active=True).first()
            if existing and existing.id != user_id:
                return jsonify({"error": "Username already exists"}), 400
            user.username = data["username"]
            
        if "password" in data and data["password"]:
            if len(data["password"]) < 6:
                return jsonify({"error": "Password must be at least 6 characters"}), 400
            user.set_password(data["password"])
            
        if "role" in data:
            user.role = data["role"]
        
        db.session.commit()
        
        # อัพเดทสิทธิ์การเข้าถึงสาขาสำหรับ user
        if user.role == 'user' and 'branches' in data:
            # ลบสิทธิ์เก่า
            UserBranchAccess.query.filter_by(user_id=user_id).delete()
            # เพิ่มสิทธิ์ใหม่
            for province in data['branches']:
                user_branch = UserBranchAccess(
                    user_id=user_id,
                    province=province
                )
                db.session.add(user_branch)
            db.session.commit()
            print(f"Updated user {user.username} with access to {len(data['branches'])} branches")
        elif user.role == 'admin':
            # ถ้าเปลี่ยนเป็น admin ให้ลบสิทธิ์สาขาทั้งหมด
            UserBranchAccess.query.filter_by(user_id=user_id).delete()
            db.session.commit()
            print(f"Updated user {user.username} to admin role")
        
        print(f"Admin {session.get('username')} updated user {old_username} (ID: {user_id})")
        return jsonify({
            "status": "success", 
            "message": "User updated successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in edit_user: {str(e)}")
        return jsonify({"error": f"Failed to update user: {str(e)}"}), 500

@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    """ลบผู้ใช้ (Admin only) - ใช้ Soft Delete"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        if session.get('user_id') == user_id:
            return jsonify({"error": "Cannot delete your own account"}), 400
            
        user = User.query.filter_by(id=user_id, is_active=True).first()
        if not user:
            return jsonify({"error": "User not found or already deleted"}), 404
            
        username = user.username
        
        print(f"🔴 Attempting to soft-delete user: {username} (ID: {user_id})")
        print(f"🔴 Before - is_active: {user.is_active}, deleted_at: {user.deleted_at}")
        
        # ใช้ Soft Delete
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # ✅ ตรวจสอบหลัง commit
        user_after = User.query.filter_by(id=user_id).first()
        print(f"🟢 After - is_active: {user_after.is_active}, deleted_at: {user_after.deleted_at}")
        
        print(f"🟢 Successfully soft-deleted user: {username}")
        return jsonify({
            "status": "success", 
            "message": f"User {username} deleted successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting user {user_id}: {str(e)}")
        return jsonify({"error": f"Failed to delete user: {str(e)}"}), 500
    
# API สำหรับลบสาขา
@app.route("/api/admin/branches/<string:province>", methods=["DELETE"])
def delete_branch(province):
    """ลบสาขาและข้อมูลที่เกี่ยวข้อง (Admin only)"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        # ตรวจสอบว่ามีไซโลในสาขานี้หรือไม่
        silos_in_branch = SiloMeta.query.filter_by(province=province).all()
        
        if silos_in_branch:
            return jsonify({
                "error": f"ไม่สามารถลบสาขา {province} ได้ เนื่องจากมีไซโลอยู่ {len(silos_in_branch)} ไซโล"
            }), 400
        
        # ลบสิทธิ์การเข้าถึงสาขาจาก user_branch_access
        deleted_access_count = UserBranchAccess.query.filter_by(province=province).delete()
        
        db.session.commit()
        
        print(f"✅ ลบสาขา {province} สำเร็จ")
        print(f"✅ ลบสิทธิ์การเข้าถึง {deleted_access_count} รายการจาก user_branch_access")
        
        return jsonify({
            "status": "success", 
            "message": f"ลบสาขา {province} สำเร็จ",
            "deleted_access_count": deleted_access_count
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting branch {province}: {str(e)}")
        return jsonify({"error": f"Failed to delete branch: {str(e)}"}), 500

# API สำหรับตรวจสอบสาขาก่อนลบ
@app.route("/api/admin/branches/<string:province>/check")
def check_branch_deletion(province):
    """ตรวจสอบว่าสาขาสามารถลบได้หรือไม่"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        # นับจำนวนไซโลในสาขา
        silo_count = SiloMeta.query.filter_by(province=province).count()
        
        # นับจำนวนผู้ใช้ที่เข้าถึงสาขานี้
        user_access_count = UserBranchAccess.query.filter_by(province=province).count()
        
        return jsonify({
            "province": province,
            "can_delete": silo_count == 0,
            "silo_count": silo_count,
            "user_access_count": user_access_count,
            "message": f"สาขา {province} มี {silo_count} ไซโล และ {user_access_count} ผู้ใช้ที่เข้าถึง"
        })
        
    except Exception as e:
        print(f"Error checking branch {province}: {str(e)}")
        return jsonify({"error": f"Failed to check branch: {str(e)}"}), 500

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
            
        silo = SiloMeta.query.filter_by(device_id=device_id).first()
        if not silo:
            return jsonify({"status":"error","msg":"Unknown device_id"}), 400
            
        if not total_chunks_str or not chunk_id_str:
            return jsonify({"status":"error","msg":"Missing chunk headers"}), 400
            
        point_data = request.data.decode('utf-8', errors='ignore')
        if not point_data:
            return jsonify({"status":"error","msg":"Empty payload"}), 400
            
        total_chunks = int(total_chunks_str)
        chunk_id = int(chunk_id_str)
        
        thailand_tz = pytz.timezone('Asia/Bangkok')
        current_time_thailand = datetime.now(timezone.utc).astimezone(thailand_tz)
        
        record = SiloData(
            device_id = device_id,
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

# Debug routes
@app.route("/api/debug")
def debug_data():
    volume_count = VolumeData.query.count()
    silo_count = SiloData.query.count()
    merged_count = MergedData.query.count()
    silo_meta_count = SiloMeta.query.count()
    user_count = User.query.filter_by(is_active=True).count()
    user_branch_count = UserBranchAccess.query.count()
    
    return jsonify({
        "volume_data_count": volume_count,
        "silo_data_count": silo_count, 
        "merged_data_count": merged_count,
        "silo_meta_count": silo_meta_count,
        "user_count": user_count,
        "user_branch_count": user_branch_count,
        "all_silo_meta": [{"device_id": s.device_id, "plant_type": s.plant_type, "province": s.province} for s in SiloMeta.query.all()],
        "all_users": [{"username": u.username, "role": u.role} for u in User.query.filter_by(is_active=True).all()],
        "user_branches": [{"user": ua.user.username, "province": ua.province} for ua in UserBranchAccess.query.all()]
    })

@app.route("/api/debug/delete_user/<int:user_id>")
def debug_delete_user(user_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    user_branches = UserBranchAccess.query.filter_by(user_id=user_id).all()
    
    debug_info = {
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "is_active": user.is_active
        },
        "related_data": {
            "user_branch_access_count": len(user_branches),
            "user_branch_access": [{"id": b.id, "province": b.province} for b in user_branches]
        }
    }
    
    return jsonify(debug_info)

@app.route("/api/debug/users")
def debug_users():
    """Debug endpoint to check all users"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    all_users = User.query.all()
    active_users = User.query.filter_by(is_active=True).all()
    
    result = {
        "all_users_count": len(all_users),
        "active_users_count": len(active_users),
        "all_users": [{
            "id": u.id,
            "username": u.username, 
            "is_active": u.is_active,
            "deleted_at": u.deleted_at.isoformat() if u.deleted_at else None
        } for u in all_users],
        "active_users": [{
            "id": u.id,
            "username": u.username
        } for u in active_users]
    }
    
    return jsonify(result)

@app.route("/overview")
def overview_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template("overview_dashboard.html")

# API for overview data
@app.route("/api/overview_data")
def get_overview_data():
    try:
        if 'user_id' not in session or session.get('role') != 'admin':
            return jsonify({"error": "Unauthorized"}), 401
            
        print("📊 Fetching overview data from database...")
        
        # Get all silos with their latest volume data
        subquery = db.session.query(
            VolumeData.device_id,
            db.func.max(VolumeData.timestamp).label('max_timestamp')
        ).group_by(VolumeData.device_id).subquery()

        latest_volumes = db.session.query(VolumeData).join(
            subquery,
            (VolumeData.device_id == subquery.c.device_id) & 
            (VolumeData.timestamp == subquery.c.max_timestamp)
        ).join(SiloMeta, VolumeData.device_id == SiloMeta.device_id).all()

        print(f"📈 Found {len(latest_volumes)} silos with volume data")

        # Process data for overview
        branches_map = {}
        total_silos = 0
        total_capacity = 0
        total_used = 0
        total_low_capacity = 0

        for volume in latest_volumes:
            silo = volume.silo
            province = silo.province
            
            # Skip invalid provinces
            if not province or 'deleted' in province.lower():
                continue
                
            if province not in branches_map:
                branches_map[province] = {
                    'name': province,
                    'siloCount': 0,
                    'totalCapacity': 0,
                    'totalUsed': 0,
                    'lowCapacityCount': 0
                }

            silo_capacity = silo.capacity or 1000
            current_amount = volume.volume or 0
            percentage = (current_amount / silo_capacity) * 100 if silo_capacity > 0 else 0
            is_low_capacity = percentage < 35
            
            # Update branch stats
            branches_map[province]['siloCount'] += 1
            branches_map[province]['totalCapacity'] += silo_capacity
            branches_map[province]['totalUsed'] += current_amount
            
            if is_low_capacity:
                branches_map[province]['lowCapacityCount'] += 1
                total_low_capacity += 1
            
            # Update total stats
            total_silos += 1
            total_capacity += silo_capacity
            total_used += current_amount

        # Calculate percentages for each branch
        for branch in branches_map.values():
            if branch['totalCapacity'] > 0:
                branch['usagePercentage'] = round((branch['totalUsed'] / branch['totalCapacity']) * 100)
            else:
                branch['usagePercentage'] = 0

        # Calculate total usage percentage
        total_usage_percentage = round((total_used / total_capacity) * 100) if total_capacity > 0 else 0

        result = {
            "branches": branches_map,
            "summary": {
                "totalBranches": len(branches_map),
                "totalSilos": total_silos,
                "totalUsagePercentage": total_usage_percentage,
                "totalLowCapacity": total_low_capacity,
                "totalCapacity": total_capacity,
                "totalUsed": total_used
            }
        }

        print(f"✅ Overview data processed: {len(branches_map)} branches, {total_silos} silos")
        print(f"📊 Summary: {total_usage_percentage}% used, {total_low_capacity} low capacity silos")
        
        return jsonify(result)

    except Exception as e:
        print(f"❌ Error in get_overview_data: {str(e)}")
        # Return demo data as fallback
        return jsonify(get_demo_overview_data())

def get_demo_overview_data():
    """ข้อมูลตัวอย่างเมื่อไม่สามารถดึงข้อมูลจริงได้"""
    return {
        "branches": {
            'สระบุรี': { 
                'name': 'สระบุรี', 
                'siloCount': 3, 
                'totalCapacity': 3000, 
                'totalUsed': 1500, 
                'lowCapacityCount': 1, 
                'usagePercentage': 50 
            },
            'ราชบุรี': { 
                'name': 'ราชบุรี', 
                'siloCount': 2, 
                'totalCapacity': 2000, 
                'totalUsed': 1200, 
                'lowCapacityCount': 0, 
                'usagePercentage': 60 
            }
        },
        "summary": {
            "totalBranches": 2,
            "totalSilos": 5,
            "totalUsagePercentage": 54,
            "totalLowCapacity": 1,
            "totalCapacity": 5000,
            "totalUsed": 2700
        }
    }
    
# API สำหรับลบหลายสาขาพร้อมกัน
@app.route("/api/admin/branches", methods=["DELETE"])
def delete_multiple_branches():
    """ลบหลายสาขาพร้อมกัน (Admin only)"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        data = request.get_json()
        if not data or 'provinces' not in data:
            return jsonify({"error": "No provinces provided"}), 400
            
        provinces = data['provinces']
        results = {
            'successful': [],
            'failed': [],
            'total_deleted_access': 0
        }
        
        for province in provinces:
            try:
                # ตรวจสอบว่ามีไซโลในสาขาหรือไม่
                silo_count = SiloMeta.query.filter_by(province=province).count()
                
                if silo_count > 0:
                    results['failed'].append({
                        'province': province,
                        'reason': f'มี {silo_count} ไซโลอยู่'
                    })
                    continue
                
                # ลบสิทธิ์การเข้าถึง
                deleted_count = UserBranchAccess.query.filter_by(province=province).delete()
                results['total_deleted_access'] += deleted_count
                results['successful'].append({
                    'province': province,
                    'deleted_access_count': deleted_count
                })
                
            except Exception as e:
                results['failed'].append({
                    'province': province,
                    'reason': str(e)
                })
        
        db.session.commit()
        
        return jsonify({
            "status": "success",
            "message": f"ลบสาขาสำเร็จ {len(results['successful'])} สาขา, ล้มเหลว {len(results['failed'])} สาขา",
            "results": results
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting multiple branches: {str(e)}")
        return jsonify({"error": f"Failed to delete branches: {str(e)}"}), 500

# API สำหรับเพิ่มไซโล (แก้ไข endpoint)
@app.route("/api/admin/silos", methods=["POST"])
def add_silo():
    """เพิ่มไซโลใหม่ (Admin only)"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        # ตรวจสอบข้อมูลที่จำเป็น
        required_fields = ['device_id', 'plant_type', 'province', 'site_code', 'silo_no']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # ตรวจสอบว่า device_id ซ้ำหรือไม่
        existing_silo = SiloMeta.query.filter_by(device_id=data['device_id']).first()
        if existing_silo:
            return jsonify({"error": "Device ID นี้มีอยู่ในระบบแล้ว"}), 400
        
        # สร้างไซโลใหม่
        new_silo = SiloMeta(
            device_id=data['device_id'],
            plant_type=data['plant_type'],
            province=data['province'],
            site_code=data['site_code'],
            silo_no=data['silo_no'],
            capacity=data.get('capacity', 1000.0)
        )
        
        db.session.add(new_silo)
        db.session.commit()
        
        print(f"✅ เพิ่มไซโลใหม่สำเร็จ: {new_silo.device_id}")
        
        return jsonify({
            "status": "success", 
            "message": "เพิ่มไซโลสำเร็จ",
            "silo_id": new_silo.id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error adding silo: {str(e)}")
        return jsonify({"error": f"Failed to add silo: {str(e)}"}), 500

# API สำหรับลบไซโลโดยใช้ device_id (ใช้ endpoint นี้แทน)
@app.route("/api/admin/silos/by_device/<string:device_id>", methods=["DELETE"])
def delete_silo_by_device(device_id):
    """ลบไซโลโดยใช้ device_id (Admin only)"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        # ค้นหาไซโลจาก device_id
        silo = SiloMeta.query.filter_by(device_id=device_id).first()
        
        if not silo:
            return jsonify({"error": f"ไม่พบไซโลด้วย Device ID: {device_id}"}), 404
        
        silo_name = f"ไซโล {silo.silo_no} - {silo.site_code}"
        
        # ลบข้อมูลที่เกี่ยวข้องทั้งหมด
        volume_deleted = VolumeData.query.filter_by(device_id=device_id).delete()
        silo_data_deleted = SiloData.query.filter_by(device_id=device_id).delete()
        merged_data_deleted = MergedData.query.filter_by(device_id=device_id).delete()
        
        db.session.delete(silo)
        db.session.commit()
        
        print(f"✅ ลบไซโลสำเร็จ (by device_id): {silo_name}")
        
        return jsonify({
            "status": "success", 
            "message": f"ลบ {silo_name} สำเร็จ",
            "deleted_data": {
                "volume_data": volume_deleted,
                "silo_data": silo_data_deleted,
                "merged_data": merged_data_deleted
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting silo by device_id {device_id}: {str(e)}")
        return jsonify({"error": f"Failed to delete silo: {str(e)}"}), 500
    
# เพิ่ม endpoint นี้ใน Flask app
@app.route("/api/admin/branches", methods=["POST"])
def add_branch():
    """เพิ่มสาขาใหม่ (Admin only)"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        # สำหรับตอนนี้ สาขาถูกสร้างอัตโนมัติจากข้อมูลไซโล
        # endpoint นี้เป็น placeholder สำหรับอนาคต
        return jsonify({
            "status": "success", 
            "message": "การเพิ่มสาขาจะถูกจัดการผ่านการเพิ่มไซโล"
        })
        
    except Exception as e:
        print(f"Error in add_branch: {str(e)}")
        return jsonify({"error": f"Failed to process request: {str(e)}"}), 500

# เพิ่ม endpoint สำหรับดึงข้อมูลผู้ใช้ที่เข้าถึงสาขา
@app.route("/api/admin/branch_users/<string:province>")
def get_branch_users(province):
    """ดึงข้อมูลผู้ใช้ที่เข้าถึงสาขา (Admin only)"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        user_access_count = UserBranchAccess.query.filter_by(province=province).count()
        
        return jsonify({
            "province": province,
            "user_count": user_access_count
        })
        
    except Exception as e:
        print(f"Error in get_branch_users: {str(e)}")
        return jsonify({"error": f"Failed to retrieve branch users: {str(e)}"}), 500
    
@app.route("/api/debug/overview")
def debug_overview():
    """Debug endpoint เพื่อตรวจสอบข้อมูล overview"""
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        # ดึงข้อมูลทั้งหมดสำหรับ debugging
        silos = SiloMeta.query.all()
        volume_data = VolumeData.query.all()
        
        # นับข้อมูลล่าสุด
        subquery = db.session.query(
            VolumeData.device_id,
            db.func.max(VolumeData.timestamp).label('max_timestamp')
        ).group_by(VolumeData.device_id).subquery()

        latest_volumes = db.session.query(VolumeData).join(
            subquery,
            (VolumeData.device_id == subquery.c.device_id) & 
            (VolumeData.timestamp == subquery.c.max_timestamp)
        ).all()
        
        debug_info = {
            "total_silos": len(silos),
            "total_volume_records": len(volume_data),
            "latest_volume_records": len(latest_volumes),
            "silos_by_province": {},
            "sample_silos": []
        }
        
        # จัดกลุ่มข้อมูลตามจังหวัด
        for silo in silos:
            province = silo.province or 'Unknown'
            if province not in debug_info["silos_by_province"]:
                debug_info["silos_by_province"][province] = 0
            debug_info["silos_by_province"][province] += 1
            
            # เก็บตัวอย่างข้อมูล
            if len(debug_info["sample_silos"]) < 5:
                debug_info["sample_silos"].append({
                    "device_id": silo.device_id,
                    "province": silo.province,
                    "site_code": silo.site_code,
                    "silo_no": silo.silo_no,
                    "capacity": silo.capacity
                })
        
        # ข้อมูล volume ล่าสุด
        debug_info["sample_volumes"] = []
        for volume in latest_volumes[:5]:  # ตัวอย่าง 5 รายการแรก
            debug_info["sample_volumes"].append({
                "device_id": volume.device_id,
                "volume": volume.volume,
                "timestamp": volume.timestamp.isoformat()
            })
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ------------------ Run Server ------------------
if __name__ == "__main__":
    print("Starting Flask server...")
    print(f"Database location: {os.path.join(basedir, 'Database', 'Server_db.sqlite3')}")
    app.run(host="0.0.0.0", port=5000, debug=True)
