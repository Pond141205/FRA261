import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull
from datetime import datetime
import json
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy 

# --- 1. SETUP: Initialize App and DB ---
# Define basedir relative to the location of this script
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)

# INTEGRATING YOUR SPECIFIC DATABASE URI
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'Database', 'Server_db.sqlite3') 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 2. MODEL DEFINITIONS (Must be defined or imported here) ---
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

# --- 3. GLOBAL CONSTANTS (from previous steps) ---
CEMENT_DENSITY = 1440.0 
TOTAL_SILO_CAPACITY_M3 = 0.288583 
# ---------------------------------------------


def run_mesh_reconstruction():
    """
    Finds the next unprocessed point cloud, calculates the volume 
    using the Hybrid Convex Hull method, and updates DB tables.
    Returns: True if work was done, False otherwise.
    """
    # This block is REQUIRED to make SQLAlchemy work in a standalone script
    with app.app_context():
        
        # 1. FIND JOB
        job = MergedData.query.filter_by(mesh_processed=False).order_by(MergedData.timestamp.asc()).first()
        
        if not job:
            return False
            
        print(f"\n--- Job Found: Device {job.device_id}, Batch {job.batch_id} ---")
        
        try:
            # Load points from the TEXT column. Assuming JSON format.
            points_list = json.loads(job.merged_points)
            points = np.array(points_list, dtype=np.float64)

            # --- 2. VOLUME CALCULATION (Hybrid Convex Hull) ---
            
            # 2a. CLEANING (Open3D)
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            print(f"Loaded {len(points)} points. Cleaning dust...")
            pcd_clean, ind = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
            cleaned_points = np.asarray(pcd_clean.points)
            
            # 2b. VOLUME (SciPy Convex Hull)
            hull = ConvexHull(cleaned_points)
            air_volume = hull.volume

            # 2c. UNIT & BOUNDARY CHECK
            if air_volume > TOTAL_SILO_CAPACITY_M3 * 10: 
                air_volume /= 1_000_000_000.0
                print("   [Conversion]: Applied mm -> m conversion.")
            
            material_volume = TOTAL_SILO_CAPACITY_M3 - air_volume
            
            if material_volume < 0:
                print(f"   [WARNING]: Negative Volume calculated. Treating as 0.")
                material_volume = 0.0 
            
            # --- 3. DATABASE UPDATES ---
            
            # 3a. Update MergedData (Mark as done)
            job.mesh_processed = True
            
            # 3b. Insert VolumeData (Store result)
            new_volume_entry = VolumeData(
                timestamp=datetime.utcnow(),
                device_id=job.device_id,
                volume=material_volume 
            )
            db.session.add(new_volume_entry)
            
            # 3c. Commit changes
            db.session.commit()
            
            print(f"-> SUCCESSFULLY processed. Volume saved: {material_volume:.4f} m^3")
            
            return True 
            
        except Exception as e:
            db.session.rollback()
            print(f"-> FAILED processing batch {job.batch_id}. Error: {e}")
            return False
