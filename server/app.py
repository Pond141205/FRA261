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
    batch_id = db.Column(db.String(100)) #(e.g., S001_01_20251001_22)
    total_chunks = db.Column(db.Integer)
    chunk_id = db.Column(db.Integer)
    point_cloud_json = db.Column(db.Text)

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
# ... (try_merge function remains the same) ...
merged_batches = set()

def try_merge(batch_id, total_chunks, device_id):
    """
    Checks if a batch is complete and merges it.
    Args:
        batch_id (str): The unique ID (device_id_YYYYMMDD_HH) for the batch.
        total_chunks (int): The expected total number of chunks.
    """
    
    # 1. Check if the batch has already been processed
    if batch_id in merged_batches:
        return None

    # 2. Query all chunks belonging to this specific batch_id
    chunks = SiloData.query.filter_by(batch_id=batch_id).order_by(SiloData.chunk_id).all()
    
    current_chunk_count = len(chunks)
    
    if total_chunks is None or total_chunks == 0:
        # Should not happen if total_chunks is sent correctly, but defensive check
        print(f"[{device_id}] total_chunks not set in payload!")
        return None
        
    if current_chunk_count != total_chunks:
        # Not all chunks have arrived yet
        print(f"[{device_id}] Waiting for all chunks: {current_chunk_count}/{total_chunks}")
        return None

    # --- Merge Logic (Complete batch found) ---
    # Use the timestamp from the first chunk as the official batch time
    batch_timestamp = chunks[0].timestamp 
    
    # Merge all points
    all_points = []
    for c in chunks:
        try:
            points_data = json.loads(c.point_cloud_json)
            all_points.extend(points_data)
        except (TypeError, json.JSONDecodeError) as e:
            print(f"Error decoding JSON for chunk {c.chunk_id} in batch {batch_id}: {e}")
            return None

    merged_array = np.array(all_points)
    print(f"[{device_id}] Merge complete: {merged_array.shape[0]} points")

    # Save merged
    merged_record = MergedData(
        timestamp=batch_timestamp,
        device_id=device_id,
        batch_id=batch_id,
        total_points=merged_array.shape[0], 
        merged_points=json.dumps(all_points)
    )
    
    try:
        db.session.add(merged_record)
        db.session.commit()
        
        # Mark the batch ID as merged
        merged_batches.add(batch_id) 
        return merged_array
        
    except Exception as e:
        db.session.rollback()
        print(f"Error saving MergedData for batch {batch_id}: {e}")
        return None

# -------------------------------
# API Endpoints
# -------------------------------
@app.route("/upload_chunk", methods=["POST"])
def upload_chunk():
    device_id = "UNKNOWN_DEVICE" # Default value in case of early error
    calculated_batch_id = None # Initialize to a safe value
    total_chunks = None # Initialize to a safe value

    # Flag to track if the chunk was new or a duplicate
    is_duplicate_chunk = False 
    
    try:
        # Expecting device_id in headers
        device_id = request.headers.get("X-Device-ID") or request.headers.get("X-Device-Id")
        if not device_id:
            # If device_id is missing, this block executes and returns 400.
            return jsonify({"status":"error","msg":"Missing device_id header"}), 400

        silo = SiloMeta.query.filter_by(device_id=device_id).first()
        if not silo:
            return jsonify({"status":"error","msg":"Unknown device_id"}), 400

        data = request.get_json()
        if not data or "chunk" not in data:
            return jsonify({"status":"error","msg":"Invalid JSON payload"}), 400

        chunk = data["chunk"]
        total_chunks = chunk.get("total_chunks")
        chunk_id = chunk.get("chunk_id")
        points = chunk.get("points")

        if points is None:
            return jsonify({"status":"error","msg":"Missing points in chunk"}), 400
        
        # Define Thailand timezone
        thailand_tz = pytz.timezone('Asia/Bangkok')
        
        current_time_utc = datetime.now(timezone.utc)
        current_time_thailand = current_time_utc.astimezone(thailand_tz)

        # Format: device_id_YYYYMMDD_HH (e.g., S001_01_20251001_22)
        date_hour_str = current_time_thailand.strftime('%Y%m%d_%H')
        calculated_batch_id = f"{device_id}_{date_hour_str}"
        
        
        # Save to DB
        record = SiloData(
            device_id = silo.device_id,
            batch_id = calculated_batch_id,
            timestamp = current_time_thailand,
            total_chunks = chunk.get("total_chunks"),
            chunk_id = chunk.get("chunk_id"),
            point_cloud_json = json.dumps(chunk.get("points"))
        )
        
        # --- CRITICAL DATABASE WRITE SECTION ---
        try:
            db.session.add(record)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            is_duplicate_chunk = True
            print(f"Chunk {chunk_id}/{total_chunks} from {device_id} ALREADY EXISTS. Checking for merge.")
            
        except Exception as e:
            # Ensure rollback on failure to clear the session and release locks
            db.session.rollback()
            raise e # Re-raise the exception to be caught by the outer block
       
        print(f"Received chunk {chunk_id}/{total_chunks} from {device_id} (Batch: {calculated_batch_id})")

        # -----------------------------------------------------
        # Call try_merge after successful commit
        # The try_merge function filters based on device_id and exact timestamp.
        # We pass the device_id and the timestamp we just used for the insert.
        merged_array = try_merge(calculated_batch_id, total_chunks, device_id)

        if merged_array is not None:
             return jsonify({"status":"ok","msg":f"Chunk {chunk_id} saved. Batch **MERGED** successfully."})
        elif 'already exists' in request.args.get('msg', '').lower():
             return jsonify({"status":"ok","msg":f"Chunk {chunk_id} already saved. Waiting for merge."})
        else:
             return jsonify({"status":"ok","msg":f"Chunk {chunk_id} saved. Waiting for more chunks."})
        # -----------------------------------------------------
        
    except Exception as e:
        # db.session.rollback() is already called in the nested try/except, 
        # but a catch-all is good practice here.
        # If the error was from try_merge (which includes a rollback), this is fine.
        
        print(f"Exception for device {device_id}:", e)
        if "database is locked" in str(e):
             return jsonify({"status":"error","msg":"Database is temporarily busy. Please retry shortly."}), 503

        return jsonify({"status":"error","msg":str(e)}), 500


# -------------------------------
# Run Server
#cmd run
#cd "C:\Users\POND\OneDrive\Documents\AllProject\FRA262 studio\Phase 2\code\server"
#venv\Scripts\activate
# -------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)