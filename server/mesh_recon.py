import open3d as o3d
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import Delaunay
import random

def read_custom_xyz(filepath):
    points = []
    with open(filepath, 'r') as f:
        lines = f.readlines()
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 3:
                try:
                    points.append([float(parts[-3]), float(parts[-2]), float(parts[-1])])
                except ValueError:
                    continue
    return np.array(points)

def fit_circle_ransac(x, y, fixed_radius, iterations=5000, threshold=0.5):
    best_center = (np.mean(x), np.mean(y))
    max_inliers = -1
    n_points = len(x)
    if n_points < 3: return best_center
    for _ in range(iterations):
        try:
            idx = random.sample(range(n_points), 2)
            p1, p2 = np.array([x[idx[0]], y[idx[0]]]), np.array([x[idx[1]], y[idx[1]]])
            d2 = np.sum((p1 - p2)**2)
            dist = np.sqrt(d2)
            if dist > 2 * fixed_radius or dist == 0: continue
            mid = (p1 + p2) / 2
            h = np.sqrt(max(0, fixed_radius**2 - (dist/2)**2))
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            for cx, cy in [(mid[0] - h * (dy/dist), mid[1] + h * (dx/dist)), (mid[0] + h * (dy/dist), mid[1] - h * (dx/dist))]:
                dists = np.sqrt((x - cx)**2 + (y - cy)**2)
                curr = np.sum(np.abs(dists - fixed_radius) < threshold)
                if curr > max_inliers:
                    max_inliers = curr
                    best_center = (cx, cy)
        except: continue
    return best_center

def create_synthetic_wall_ring(cx, cy, radius, z_base, num_points=100):
    theta = np.linspace(0, 2*np.pi, num_points, endpoint=False)
    wall_x = cx + radius * np.cos(theta)
    wall_y = cy + radius * np.sin(theta)
    wall_z = np.full(num_points, z_base)
    return np.column_stack((wall_x, wall_y, wall_z))

def create_extruded_wall_mesh(cx, cy, radius, z_bottom, z_top, segments=100):
    vertices = []
    triangles = []
    for i in range(segments):
        theta = 2 * np.pi * i / segments
        x = cx + radius * np.cos(theta)
        y = cy + radius * np.sin(theta)
        vertices.append([x, y, z_bottom])
    for i in range(segments):
        theta = 2 * np.pi * i / segments
        x = cx + radius * np.cos(theta)
        y = cy + radius * np.sin(theta)
        vertices.append([x, y, z_top])
    for i in range(segments):
        current = i
        next_i = (i + 1) % segments
        b1, b2 = current, next_i
        t1, t2 = current + segments, next_i + segments
        triangles.append([b1, t1, t2])
        triangles.append([b1, t2, b2])
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(vertices)
    mesh.triangles = o3d.utility.Vector3iVector(triangles)
    mesh.compute_vertex_normals()
    return mesh

# --- NEW FUNCTION: สร้างฝาปิด (Cap) ---
def create_lid_mesh(cx, cy, radius, z_height, segments=100):
    vertices = [[cx, cy, z_height]] # จุดกึ่งกลาง (index 0)
    for i in range(segments):
        theta = 2 * np.pi * i / segments
        x = cx + radius * np.cos(theta)
        y = cy + radius * np.sin(theta)
        vertices.append([x, y, z_height])
        
    triangles = []
    for i in range(segments):
        # เชื่อมจุดกึ่งกลาง (0) กับจุดขอบ i+1 และจุดขอบถัดไป
        v1 = i + 1
        v2 = (i + 1) % segments + 1 if (i + 1) < segments else 1
        triangles.append([0, v1, v2])
        
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(vertices)
    mesh.triangles = o3d.utility.Vector3iVector(triangles)
    mesh.compute_vertex_normals()
    mesh.paint_uniform_color([0.8, 0.2, 0.2]) # สีแดงเหมือนผนัง
    return mesh

def process_silo_extruded_with_cap(pcd_points, silo_diameter_cm=59.0, grid_res=1.0):
    # 1. Init
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pcd_points)
    pcd_denoised, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    points_clean = np.asarray(pcd_denoised.points)
    
    # *** FIX: หาความสูงปากถังจากข้อมูลดิบทั้งหมด ***
    z_max_scan = np.max(points_clean[:, 2])+21.5
    print(f"Detected Silo Top Height: {z_max_scan:.2f}")

    # 2. Find Center
    x = points_clean[:, 0]
    y = points_clean[:, 1]
    rough_cx, rough_cy = np.median(x), np.median(y)
    dist_rough = np.sqrt((x - rough_cx)**2 + (y - rough_cy)**2)
    wall_mask = dist_rough > np.percentile(dist_rough, 80)
    target_radius = silo_diameter_cm / 2.0
    cx, cy = fit_circle_ransac(x[wall_mask], y[wall_mask], target_radius)
    print(f"Center: ({cx:.2f}, {cy:.2f})")

    # 3. Filter Cement
    dist_final = np.sqrt((x - cx)**2 + (y - cy)**2)
    mask_cement = dist_final <= (target_radius * 0.85)
    points_cement = points_clean[mask_cement]

    # 4. Max Z Filter
    grid_dict = {}
    for p in points_cement:
        gx = int(np.round(p[0]/grid_res))
        gy = int(np.round(p[1]/grid_res))
        if (gx,gy) not in grid_dict or p[2] > grid_dict[(gx,gy)][2]:
            grid_dict[(gx,gy)] = p
    surface_pts = np.array(list(grid_dict.values()))

    # --- 5. CEMENT MESH ---
    avg_cement_z = np.mean(surface_pts[:, 2])
    wall_points_bottom = create_synthetic_wall_ring(cx, cy, target_radius, avg_cement_z, num_points=100)
    combined_points = np.vstack((surface_pts, wall_points_bottom))
    tri = Delaunay(combined_points[:, :2])
    
    mesh_cement = o3d.geometry.TriangleMesh()
    mesh_cement.vertices = o3d.utility.Vector3dVector(combined_points)
    mesh_cement.triangles = o3d.utility.Vector3iVector(tri.simplices)
    mesh_cement.compute_vertex_normals()
    mesh_cement.paint_uniform_color([0.2, 0.8, 0.2]) # สีเขียว

    # --- 6. EXTRUDE WALL & CAP ---
    # สร้างผนัง
    mesh_wall = create_extruded_wall_mesh(cx, cy, target_radius, avg_cement_z, z_max_scan)
    mesh_wall.paint_uniform_color([0.8, 0.2, 0.2]) # สีแดง
    
    # สร้างฝาปิด (Lid)
    mesh_lid = create_lid_mesh(cx, cy, target_radius, z_max_scan)
    
    # Volume
    cell_area = grid_res**2
    vol = sum([max(0, z_max_scan - p[2])*cell_area for p in surface_pts])
    total_vol = vol / (0.85**2)

    return mesh_cement, mesh_wall, mesh_lid, total_vol

# --- RUN ---
filename = "S001_01-20251123_17_CMD.xyz"
try:
    raw = read_custom_xyz(filename)
    if len(raw) > 0:
        mesh_c, mesh_w, mesh_l, vol = process_silo_extruded_with_cap(raw, silo_diameter_cm=59)
        print(f"Estimated Total Volume: {vol/1000:.2f} Liters")
        
        # แสดงผล: ผิวปูน + ผนัง + ฝาปิด
        o3d.visualization.draw_geometries([mesh_c, mesh_w, mesh_l], window_name="Extruded Wall with Cap")
except Exception as e:
    print(f"Error: {e}")