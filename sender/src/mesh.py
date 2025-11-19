import open3d as o3d
import numpy as np
import os

# --- SETTINGS ---
INPUT_FILE = "scan_data_55.xyz"  # The file you captured
OUTPUT_MESH = "silo_mesh.ply" # The output mesh file
POISSON_DEPTH = 7             # Higher = More detail (8-10 is good)

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: File '{INPUT_FILE}' not found!")
        return

    print(f"Loading point cloud from {INPUT_FILE}...")
    pcd = o3d.io.read_point_cloud(INPUT_FILE, format='xyz')
    print(f"Loaded {len(pcd.points)} points.")

    # 1. Pre-processing: Remove Statistical Outliers (Noise)
    print("Removing noise (outliers)...")
    # nb_neighbors: how many neighbors to look at
    # std_ratio: threshold (lower = more aggressive removal)
    cl, ind = pcd.remove_statistical_outlier(nb_neighbors=10, std_ratio=2.0)
    pcd_clean = pcd.select_by_index(ind)
    print(f"Retained {len(pcd_clean.points)} points after cleaning.")

    # 2. Estimate Normals (Crucial for Meshing)
    # Poisson reconstruction needs to know which way is "out" vs "in"
    print("Estimating normals...")
    pcd_clean.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=10.0, max_nn=30))
    
    # Orient normals outwards (assuming sensor was inside looking out)
    # We orient them towards the center (0,0,0) and then flip them if needed
    pcd_clean.orient_normals_towards_camera_location(camera_location=np.array([0., 0., 0.]))
    
    # NOTE: Since the sensor is INSIDE the silo, normals pointing to (0,0,0) might be
    # pointing "backwards" relative to the surface. We might need to flip them.
    # Try commenting/uncommenting this line if your mesh looks "inside out" (black faces).
    pcd_clean.normals = o3d.utility.Vector3dVector(-np.asarray(pcd_clean.normals))

    # 3. Surface Reconstruction (Poisson)
    print(f"Running Poisson Surface Reconstruction (Depth={POISSON_DEPTH})...")
    with o3d.utility.VerbosityContextManager(o3d.utility.VerbosityLevel.Debug) as cm:
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd_clean, depth=POISSON_DEPTH
        )

    # 4. Cleaning the Mesh
    # Poisson creates a "watertight" blob that might include extra bubbles around sparse areas.
    # We filter out triangles that had very few points supporting them (low density).
    print("Trimming low-density mesh areas...")
    densities = np.asarray(densities)
    density_threshold = np.percentile(densities, 10) # Filter bottom 10% density
    vertices_to_remove = densities < density_threshold
    mesh.remove_vertices_by_mask(vertices_to_remove)

    # 5. Save and Visualize
    print(f"Saving mesh to {OUTPUT_MESH}...")
    o3d.io.write_triangle_mesh(OUTPUT_MESH, mesh)
    
    print("Displaying result...")
    # Draw point cloud (black) and mesh (shiny) together
    mesh.compute_vertex_normals()
    mesh.paint_uniform_color([0.7, 0.7, 0.7]) # Gray mesh
    pcd_clean.paint_uniform_color([0, 0, 0])  # Black dots
    
    o3d.visualization.draw_geometries([mesh, pcd_clean], window_name="Silo Mesh Result")

if __name__ == "__main__":
    main()