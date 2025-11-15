import numpy as np
import open3d as o3d
import os
import sys

# We import the 'app' and 'db' models from your existing server file
try:
    from app import app, db, MergedData
except ImportError:
    print("Error: Could not import 'app.py'.")
    print("Please make sure this script is in the same directory as your main server file.")
    sys.exit(1)

def run_mesh_reconstruction():
    """
    Connects to the database, fetches the OLDEST unprocessed scan,
    runs mesh reconstruction, and marks it as processed.
    """
    print("--- Starting Mesh Reconstruction ---")
    
    with app.app_context():
        
        # --- 1. Get the next scan in the queue ---
        print("Finding next unprocessed scan in the queue...")
        
        # We now search for the oldest scan that is NOT processed
        scan = MergedData.query.filter_by(mesh_processed=False).order_by(MergedData.timestamp.asc()).first()
        
        if not scan:
            print("No unprocessed scans found. All work is done.")
            return

        print(f"Processing Batch ID: {scan.batch_id}")
        print(f"Total points (estimated): {scan.total_points}")

        # --- 2. Get the merged text string ---
        all_points_string = scan.merged_points
        if not all_points_string:
            print("Error: Merged data is empty.")
            return

        # --- 3. Parse the text into a NumPy array ---
        print("Parsing point cloud data...")
        try:
            points_array = np.fromstring(all_points_string, sep=' ', dtype=np.float64)
            points_array = points_array.reshape(-1, 3)
        except Exception as e:
            print(f"Error parsing string data: {e}")
            return

        # --- 4. Create Open3D point cloud object ---
        print("Creating Open3D point cloud...")
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points_array)

        # --- 5. Pre-processing: Normals ---
        print("Estimating normals...")
        pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30))
        pcd.orient_normals_consistent_tangent_plane(10)

        # --- 6. Run Mesh Reconstruction (Poisson) ---
        print("Reconstructing mesh (this may take a moment)...")
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=9)

        # --- 7. Save the final mesh file ---
        output_dir = "Meshes"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        output_filename = os.path.join(output_dir, f"{scan.batch_id}_mesh.ply")
        o3d.io.write_triangle_mesh(output_filename, mesh)

        # --- 8. UPDATE the database ---
        print(f"Updating database, marking {scan.batch_id} as processed...")
        scan.mesh_processed = True
        db.session.commit()

        print(f"\n✅ Success! Mesh saved to: {output_filename}")

# --- This part runs the script ---
if __name__ == "__main__":
    
    # This script will now automatically find the next job
    # in the queue and process it.
    run_mesh_reconstruction()