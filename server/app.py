from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, create_engine
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
import os, json,pytz, numpy as np

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
# 1. Use an SQLite URI that explicitly allows the use of connect_args
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'Database', 'Server_db.sqlite3')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 2. Set the connection arguments, including a timeout for locking
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    # Increase the timeout (default is 5 seconds) to give concurrent writes more time to complete
    'connect_args': {'timeout': 30},
    'pool_timeout': 30 # This is the pool's timeout, not SQLite's lock timeout
}
db = SQLAlchemy(app)

# 3. Function to enable WAL mode
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Event listener to set PRAGMA journal_mode=WAL on connection."""
    cursor = dbapi_connection.cursor()
    # Execute the PRAGMA to enable WAL mode
    cursor.execute("PRAGMA journal_mode=WAL")
    # You might also want to set busy_timeout if not using the connect_args above
    # cursor.execute("PRAGMA busy_timeout=30000") # 30 seconds
    cursor.close()

# 4. Register the event listener with the engine
with app.app_context():
    # Get the underlying SQLAlchemy engine object
    engine = db.engine
    # Listen for the 'connect' event and apply the pragma
    event.listen(engine, "connect", set_sqlite_pragma)


# --- Table 1: Raw chunk input (Rest of your models are unchanged) ---
class SiloData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    device_id = db.Column(db.String(50))
    batch_id = db.Column(db.String(100)) 
    total_chunks = db.Column(db.Integer)
    chunk_id = db.Column(db.Integer)
    point_cloud = db.Column(db.Text)

    __table_args__ = (db.UniqueConstraint('batch_id', 'chunk_id', name='_batch_chunk_uc'),) # Ensure unique chunk per batch

# --- Table 2: Merged point cloud ---
class MergedData(db.Model):
    # ... (Model definition remains the same) ...
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    device_id = db.Column(db.String(50))
    batch_id = db.Column(db.String(100))
    total_points = db.Column(db.Integer)
    merged_points = db.Column(db.Text)
    mesh_processed = db.Column(db.Boolean, default=False, nullable=False)

# --- Table 3: Volume results ---
class VolumeData(db.Model):
    # ... (Model definition remains the same) ...
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    device_id = db.Column(db.String(50))
    volume = db.Column(db.Float)

# --- Table 4: Silo meta ---
class SiloMeta(db.Model):
    # ... (Model definition remains the same) ...
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True)
    plant_type = db.Column(db.String(50))
    province = db.Column(db.String(50))
    site_code = db.Column(db.String(20))
    silo_no = db.Column(db.String(10))

# --- Init database ---
if not os.path.exists('Database'):
    os.makedirs('Database')
with app.app_context():
    db.create_all()
# -------------------------------
# Merge Logic 
# -------------------------------
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

    # --- MODIFIED Merge Logic ---
    batch_timestamp = chunks[0].timestamp 
    
    # Merge all text chunks by joining them
    all_points_text = ""
    for c in chunks:
        # c.point_cloud_json already contains the raw text
        all_points_text += c.point_cloud
        
    # Estimate total points by counting lines
    total_points = len(all_points_text.splitlines())
    
    print(f"[{device_id}] [Batch_id: {batch_id}] Merge complete: ~{total_points} points")

    # Save merged text
    merged_record = MergedData(
        timestamp=batch_timestamp,
        device_id=device_id,
        batch_id=batch_id,
        total_points=total_points, 
        merged_points=all_points_text # Save the combined text
    )
    
    try:
        db.session.add(merged_record)
        db.session.commit()
        merged_batches.add(batch_id) 
        # We return the text, but you can change this to return the np.array
        # if you parse it here. For now, just confirming merge.
        return True 
        
    except Exception as e:
        db.session.rollback()
        print(f"Error saving MergedData for batch {batch_id}: {e}")
        return None

# -------------------------------
# API Endpoints
# -------------------------------

@app.route("/api/merged_data")
def api_merged_data():
    rows = MergedData.query.order_by(MergedData.timestamp.desc()).all()
    result = []
    for r in rows:
        result.append({
            "id": r.id,
            "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "device_id": r.device_id,
            "batch_id": r.batch_id,
            "total_points": r.total_points,
            "mesh_processed": bool(r.mesh_processed)
        })
    return jsonify(result)

@app.route("/upload_chunk", methods=["POST"])
def upload_chunk():
    device_id = "UNKNOWN_DEVICE"
    batch_id = None
    total_chunks = None


    
    try:
        # 1. Get headers (these are all strings)
        device_id = request.headers.get("X-Device-ID")
        total_chunks_str = request.headers.get("X-Total-Chunks")
        chunk_id_str = request.headers.get("X-Chunk-ID")
        batch_id = request.headers.get("X-Batch-ID") 
        
        # print(f"\n--- New Request Headers ---")
        # print(f"X-Device-ID: {device_id}")

        if not device_id:
            return jsonify({"status":"error","msg":"Missing X-Device-ID header"}), 400
        if not total_chunks_str or not chunk_id_str:
            return jsonify({"status":"error","msg":"Missing chunk headers"}), 400

        # 2. Get the raw text data
        # We decode the raw bytes (request.data) into a text string
        point_data = request.data.decode('utf-8', errors='ignore')
        if not point_data:
             return jsonify({"status":"error","msg":"Empty payload"}), 400
        
        # 3. Convert headers to integer
        try:
            total_chunks = int(total_chunks_str)
            chunk_id = int(chunk_id_str)
        except ValueError:
            return jsonify({"status":"error","msg":"Invalid chunk header values"}), 400

        silo = SiloMeta.query.filter_by(device_id=device_id).first()
        if not silo:
            return jsonify({"status":"error","msg":"Unknown device_id"}), 400

        
        thailand_tz = pytz.timezone('Asia/Bangkok')
        current_time_utc = datetime.now(timezone.utc)
        current_time_thailand = current_time_utc.astimezone(thailand_tz)
        #date_hour_str = current_time_thailand.strftime('%Y%m%d_%H')
        
        
        # 5. Save the raw text chunk to DB
        record = SiloData(
            device_id = silo.device_id,
            batch_id = batch_id,
            timestamp = current_time_thailand,
            total_chunks = total_chunks,
            chunk_id = chunk_id,
            point_cloud = point_data # Store the raw text
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

        # 6. Call try_merge
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
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
