import open3d as o3d
import numpy as np

# --- SETTINGS ---
INPUT_MESH = "silo_mesh.ply" # The mesh file you generated

def main():
    # 1. Load the Mesh
    print(f"Loading {INPUT_MESH}...")
    mesh = o3d.io.read_triangle_mesh(INPUT_MESH)
    
    if mesh.is_empty():
        print("Error: Mesh is empty or file not found.")
        return

    # 2. Check if Watertight
    # A true volume calculation requires a closed shape (no holes).
    print(f"Is mesh watertight? {mesh.is_watertight()}")

    if not mesh.is_watertight():
        print("Mesh is open (has holes). Attempting to close holes for volume calculation...")
        
        # Technique A: Convex Hull (Easiest, but ignores the funnel shape)
        # This wraps the object in 'shrink wrap'. It will overestimate slightly.
        hull, _ = mesh.compute_convex_hull()
        hull_volume = hull.get_volume()
        print(f"\n--- Approximation 1: Convex Hull ---")
        print(f"Volume: {hull_volume:.2f} cubic units")
        
        # Technique B: Hole Filling (Better for shape preservation)
        # Open3D doesn't have a simple 'cap holes' for huge holes, 
        # but we can approximate by creating a watertight Poisson mesh again with high depth
        # OR we can assume the Convex Hull is 'close enough' for a silo shape.
        
        # Let's stick to Convex Hull for robustness on scanned data,
        # but we can also print the Bounding Box volume as a sanity check.
        
    else:
        # If it's already watertight, calculation is exact.
        print(f"Volume: {mesh.get_volume():.2f} cubic units")

    # 3. Calculate Bounding Box Volume (Cylinder approximation)
    # V = pi * r^2 * h
    aabb = mesh.get_axis_aligned_bounding_box()
    extent = aabb.get_extent()
    print(f"\n--- Approximation 2: Bounding Box Dimensions ---")
    print(f"Width (X): {extent[0]:.2f}")
    print(f"Depth (Y): {extent[1]:.2f}")
    print(f"Height (Z): {extent[2]:.2f}")
    
    # Estimated Radius (Average of X and Y / 2)
    radius = (extent[0] + extent[1]) / 4.0
    height = extent[2]
    
    # Cylinder Volume Formula
    cylinder_vol = np.pi * (radius ** 2) * height
    print(f"Estimated Cylinder Volume (Pi*r^2*h): {cylinder_vol:.2f} cubic units")
    
    # 4. Visualization
    print("\nDisplaying Convex Hull (Red line) vs Original Mesh...")
    hull_ls = o3d.geometry.LineSet.create_from_triangle_mesh(hull)
    hull_ls.paint_uniform_color([1, 0, 0])
    o3d.visualization.draw_geometries([mesh, hull_ls], window_name="Volume Viz")

if __name__ == "__main__":
    main()