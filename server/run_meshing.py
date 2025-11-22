import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull
from datetime import datetime, timezone # Added timezone import
import json
import os
import io
from flask import Flask
from flask_sqlalchemy import SQLAlchemy 

# ====================================================================
# 1. DATABASE & APP SETUP (SQLite)
# ====================================================================
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'Database', 'Server_db.sqlite3') 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- GLOBAL CONSTANTS ---
TOTAL_SILO_CAPACITY_M3 = 0.288583 
CEMENT_DENSITY = 1440.0 
# ---------------------------------------------

# ====================================================================
# 2. MODEL DEFINITIONS (Updated VolumeData)
# ====================================================================
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
    device_id = db.Column(db.String(50), db.ForeignKey('silo_meta.device_id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    volume = db.Column(db.Float)
    volume_percentage = db.Column(db.Float) # <-- NEW COLUMN
    
# ====================================================================
# 3. WORKER FUNCTION
# ====================================================================
def run_mesh_reconstruction():
    """
    Finds the next unprocessed point cloud, calculates the volume and percentage, 
    and updates DB tables.
    """
    with app.app_context():
        
        job = MergedData.query.filter_by(mesh_processed=False).order_by(MergedData.timestamp.asc()).first()
        
        if not job:
            return False
            
        print(f"\n--- Job Found: Device {job.device_id}, Batch {job.batch_id} ---")
        
        try:
            # 1. LOAD AND CLEAN POINTS
            data_stream = io.StringIO(job.merged_points)
            points = np.loadtxt(data_stream, dtype=np.float64)
            
            if points.shape[0] < 100:
                 raise ValueError("Insufficient points for meshing after loading.")
            
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            print(f"Loaded {len(points)} points. Cleaning dust...")
            pcd_clean, ind = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
            cleaned_points = np.asarray(pcd_clean.points)
            
            # 2. VOLUME CALCULATION (Hybrid Convex Hull)
            hull = ConvexHull(cleaned_points)
            air_volume = hull.volume

            # Unit Check
            if air_volume > TOTAL_SILO_CAPACITY_M3 * 10: 
                air_volume /= 1_000_000_000.0
            
            # 3. FINAL CALCULATIONS
            material_volume = TOTAL_SILO_CAPACITY_M3 - air_volume
            
            if material_volume < 0:
                material_volume = 0.0 
            
            # --- NEW CALCULATION ---
            volume_percentage = (material_volume / TOTAL_SILO_CAPACITY_M3) * 100.0
            # Ensure percentage is clamped between 0 and 100 due to possible scan errors
            volume_percentage = max(0.0, min(100.0, volume_percentage))
            # -----------------------

            # --- 4. DATABASE UPDATES ---
            
            job.mesh_processed = True
            
            # Storing result in VolumeData (with new percentage field)
            new_volume_entry = VolumeData(
                timestamp=datetime.now(timezone.utc),
                device_id=job.device_id,
                volume=material_volume,
                volume_percentage=volume_percentage # <-- NEW FIELD PUSHED
            )
            db.session.add(new_volume_entry)
            db.session.commit()
            
            print(f"-> SUCCESSFULLY processed. Volume saved: {material_volume:.4f} m^3")
            print(f"-> Percentage: {volume_percentage:.2f}% full.")
            
            return True 
            
        except Exception as e:
            db.session.rollback()
            print(f"-> FAILED processing batch {job.batch_id}. Error: {e}")
            return False 

# ====================================================================
# 4. ENTRY POINT (for worker.py)
# ====================================================================

if __name__ == "__main__":
    if run_mesh_reconstruction():
        print("Work cycle complete.")
    else:
        print("No work pending.")
