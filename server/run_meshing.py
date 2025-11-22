import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull
from datetime import datetime
import json
import os
import io # Crucial for reading .xyz text data from the string
from flask import Flask
from flask_sqlalchemy import SQLAlchemy 

# ====================================================================
# 1. DATABASE & APP SETUP (SQLite)
# ====================================================================
# Define basedir relative to the location of this script
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)

# CONFIGURATION: Uses your specified relative SQLite path
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'Database', 'Server_db.sqlite3') 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- GLOBAL CONSTANTS (from previous steps) ---
# Accurate geometric volume: 288,582.8 cm^3 converted to m^3
TOTAL_SILO_CAPACITY_M3 = 0.288583 
CEMENT_DENSITY = 1440.0 # kg/m^3 
# ---------------------------------------------

# ====================================================================
# 2. MODEL DEFINITIONS (Must match your primary app file)
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
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    device_id = db.Column(db.String(50))
    volume = db.Column(db.Float)

# ====================================================================
# 3. WORKER FUNCTION
# ====================================================================
def run_mesh_reconstruction():
    """
    Finds the next unprocessed point cloud, calculates the volume, and updates DB.
    """
    # **REQUIRED:** Enters the Flask application context to access the database
    with app.app_context():
        
        # 1. FIND JOB
        job = MergedData.query.filter_by(mesh_processed=False).order_by(MergedData.timestamp.asc()).first()
        
        if not job:
            return False
            
        print(f"\n--- Job Found: Device {job.device_id}, Batch {job.batch_id} ---")
        
        try:
            # 2a. LOAD POINTS (The Fix for .xyz format)
            # Use io.StringIO to treat the stored text (.xyz data) as a file stream,
            # and np.loadtxt to parse the space-separated coordinates.
            data_stream = io.StringIO(job.merged_points)
            points = np.loadtxt(data_stream, dtype=np.float64)
            
            if points.shape[0] < 100:
                 raise ValueError("Insufficient points for meshing after loading.")
            
            # 2b. CLEANING (Open3D)
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            print(f"Loaded {len(points)} points. Cleaning dust...")
            pcd_clean, ind = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
            cleaned_points = np.asarray(pcd_clean.points)
            
            # 2c. VOLUME CALCULATION (SciPy Convex Hull)
            # Convex Hull guarantees a watertight volume, solving previous errors.
            print("3. Computing Convex Hull Volume...")
            hull = ConvexHull(cleaned_points)
            air_volume = hull.volume

            # 2d. UNIT CHECK
            if air_volume > TOTAL_SILO_CAPACITY_M3 * 10: 
                air_volume /= 1_000_000_000.0
                print("   [Conversion]: Applied mm -> m conversion.")
            
            # Material Volume = Total Silo Capacity - Air Volume
            material_volume = TOTAL_SILO_CAPACITY_M3 - air_volume
            
            if material_volume < 0:
                print(f"   [WARNING]: Negative Volume calculated. Treating as 0.")
                material_volume = 0.0 
            
            # --- 4. DATABASE UPDATES ---
            
            # Mark the job as processed
            job.mesh_processed = True
            
            # Store the resulting material volume
            new_volume_entry = VolumeData(
                timestamp=datetime.utcnow(),
                device_id=job.device_id,
                volume=material_volume 
            )
            db.session.add(new_volume_entry)
            db.session.commit()
            
            print(f"-> SUCCESSFULLY processed. Volume saved: {material_volume:.4f} m^3")
            
            return True 
            
        except Exception as e:
            # Rollback transaction on failure to prevent corrupted database state
            db.session.rollback()
            print(f"-> FAILED processing batch {job.batch_id}. Error: {e}")
            return False 

# ====================================================================
# 4. ENTRY POINT
# ====================================================================

if __name__ == "__main__":
    # This function is typically called by your worker.py script's continuous loop
    # For testing:
    if run_mesh_reconstruction():
        print("Work cycle complete.")
    else:
        print("No work pending.")
