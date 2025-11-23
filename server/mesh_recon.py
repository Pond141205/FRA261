import open3d as o3d
import numpy as np
import copy

def fit_circle_ransac(points_2d, iterations=5000, threshold=0.5):
    """
    หาจุดศูนย์กลางและรัศมีของไซโล (RANSAC)
    """
    best_circle = None
    best_inliers = 0
    n_points = len(points_2d)
    
    print(f"Fitting circle to {n_points} points...")
    
    if n_points < 10: return None

    for _ in range(iterations):
        idx = np.random.choice(n_points, 3, replace=False)
        p1, p2, p3 = points_2d[idx]
        
        temp = p2[0]**2 + p2[1]**2
        bc = (p1[0]**2 + p1[1]**2 - temp) / 2
        cd = (temp - p3[0]**2 - p3[1]**2) / 2
        det = (p1[0] - p2[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p2[1])
        
        if abs(det) < 1e-6: continue
        
        cx = (bc*(p2[1] - p3[1]) - cd*(p1[1] - p2[1])) / det
        cy = ((p1[0] - p2[0])*cd - (p2[0] - p3[0])*bc) / det
        radius = np.sqrt((p1[0] - cx)**2 + (p1[1] - cy)**2)
        
        # กรองรัศมีที่เพี้ยนเกินจริง (เช่น < 10cm หรือ > 150cm)
        if radius < 10 or radius > 150: continue

        dists = np.sqrt((points_2d[:, 0] - cx)**2 + (points_2d[:, 1] - cy)**2)
        inliers = np.sum(np.abs(dists - radius) < threshold)
        
        if inliers > best_inliers:
            best_inliers = inliers
            best_circle = (cx, cy, radius)
            
    return best_circle

def process_silo_high_fidelity(filename, manual_diameter_cm=None, grid_res=0.5):
    print(f"Loading {filename}...")
    try:
        pcd = o3d.io.read_point_cloud(filename)
    except:
        try:
            pts = np.loadtxt(filename)
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(pts[:, :3])
        except Exception as e:
            print(f"Error: {e}")
            return

    if len(pcd.points) == 0: return

    points = np.asarray(pcd.points)
    
    # -------------------------------------------------------
    # 1. หาจุดศูนย์กลางและตัดขอบ
    # -------------------------------------------------------
    points_xy = points[:, :2]
    
    if manual_diameter_cm:
        # ถ้ามีขนาดจริง ใช้จุดกึ่งกลางจาก RANSAC เพื่อความแม่นยำตำแหน่ง
        circle = fit_circle_ransac(points_xy)
        if circle:
            cx, cy, _ = circle
            radius = manual_diameter_cm / 2.0
        else:
            cx, cy = np.median(points_xy[:, 0]), np.median(points_xy[:, 1])
            radius = manual_diameter_cm / 2.0
    else:
        circle = fit_circle_ransac(points_xy)
        if circle:
            cx, cy, radius = circle
        else:
            cx, cy = np.median(points_xy[:, 0]), np.median(points_xy[:, 1])
            radius = 30.0 # Default

    print(f"Using Center: ({cx:.2f}, {cy:.2f}), Radius: {radius:.2f} cm")

    # ตัดจุดที่อยู่นอกวงกลมทิ้ง (Margin 1.5 cm)
    safe_radius = radius - 1.5
    dists = np.sqrt((points[:, 0] - cx)**2 + (points[:, 1] - cy)**2)
    
    points_inside = points[dists < safe_radius]
    points_outside = points[dists >= safe_radius] # เก็บไว้โชว์เป็นขยะ

    # -------------------------------------------------------
    # 2. Grid Max Z Filtering (High Res: 0.5 cm)
    # -------------------------------------------------------
    print(f"Filtering Surface with Grid Resolution: {grid_res} cm...")
    
    grid_map = {}
    noise_points = [] 

    for p in points_inside:
        x, y, z = p
        # คำนวณ Index ของตาราง
        grid_x = int(np.floor(x / grid_res))
        grid_y = int(np.floor(y / grid_res))
        key = (grid_x, grid_y)
        
        if key not in grid_map:
            grid_map[key] = p
        else:
            # เก็บเฉพาะจุดที่สูงที่สุดในช่องตารางนั้น
            if z > grid_map[key][2]:
                noise_points.append(grid_map[key]) 
                grid_map[key] = p
            else:
                noise_points.append(p) 

    surface_points = np.array(list(grid_map.values()))
    print(f"Final Surface Points: {len(surface_points)}")

    # รวมขยะเพื่อแสดงผล (จุดนอกวง + จุดที่จม)
    all_waste = []
    if len(points_outside) > 0: all_waste.append(points_outside)
    if len(noise_points) > 0: all_waste.append(np.array(noise_points))
    
    pcd_surface = o3d.geometry.PointCloud()
    pcd_surface.points = o3d.utility.Vector3dVector(surface_points)
    
    pcd_waste = o3d.geometry.PointCloud()
    if len(all_waste) > 0:
        pcd_waste.points = o3d.utility.Vector3dVector(np.vstack(all_waste))

    # [DEBUG] แสดงจุดก่อนทำ Mesh
    # เขียว = ผิวปูนที่คัดมา
    pcd_surface.paint_uniform_color([0, 1, 0]) 
    # แดง = ขยะที่ทิ้งไป
    pcd_waste.paint_uniform_color([1, 0, 0])   
    # o3d.visualization.draw_geometries([pcd_surface, pcd_waste], window_name="Debug: Green=Surface, Red=Noise")

    # -------------------------------------------------------
    # 3. สร้างฝาปิด (Lid)
    # -------------------------------------------------------
    max_z_sensor = np.max(points[:, 2])
    # ฝาปิดละเอียดเท่ากับ Grid เพื่อความเนียน
    lid_res = grid_res 
    x_range = np.arange(cx - radius, cx + radius, lid_res)
    y_range = np.arange(cy - radius, cy + radius, lid_res)
    
    lid_points = []
    for lx in x_range:
        for ly in y_range:
            if (lx - cx)**2 + (ly - cy)**2 <= radius**2:
                lid_points.append([lx, ly, max_z_sensor])
    
    pcd_lid = o3d.geometry.PointCloud()
    pcd_lid.points = o3d.utility.Vector3dVector(np.array(lid_points))

    # -------------------------------------------------------
    # 4. สร้าง Mesh (High Depth Poisson)
    # -------------------------------------------------------
    pcd_final = pcd_surface + pcd_lid
    # รัศมี Search สำหรับ Normal ต้องเหมาะสมกับ Grid Res
    pcd_final.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=5.0, max_nn=30))
    pcd_final.orient_normals_consistent_tangent_plane(100)

    print("Reconstructing High Fidelity Mesh (Depth=11)...")
    # depth=11 ให้รายละเอียดสูง เหมาะกับ Grid 0.5 cm
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd_final, depth=11, width=0, scale=1.1, linear_fit=False
    )
    
    # ตัดขอบ Mesh ที่เกินออกมา (Trim Low Density)
    densities = np.asarray(densities)
    # ตัดน้อยๆ (0.5%) เพื่อเก็บขอบไว้
    density_threshold = np.percentile(densities, 0.5) 
    mesh.remove_vertices_by_mask(densities < density_threshold)

    # -------------------------------------------------------
    # 5. คำนวณปริมาตร
    # -------------------------------------------------------
    if not mesh.is_watertight():
        print("Info: Closing minor holes with Convex Hull...")
        mesh, _ = mesh.compute_convex_hull()
        
    volume_cm3 = mesh.get_volume()
    volume_m3 = volume_cm3 / 1_000_000.0
    volume_liters = volume_cm3 / 1000.0

    print("="*40)
    print(f"Measured Empty Volume: {volume_m3:.6f} m3")
    print(f"Measured Empty Volume: {volume_liters:.2f} Liters")
    print("="*40)

    # --- Visualization ---
    mesh.compute_vertex_normals()
    mesh.paint_uniform_color([0.1, 0.7, 1.0]) # สีฟ้า
    wireframe = o3d.geometry.LineSet.create_from_triangle_mesh(mesh)
    wireframe.paint_uniform_color([0.1, 0.1, 0.1])
    
    # โชว์เทียบกับจุดผิวปูนสีเขียว (เพื่อให้เห็นว่า Mesh ทับจุดพอดีไหม)
    pcd_surface.paint_uniform_color([0, 1, 0])
    
    o3d.visualization.draw_geometries([mesh, wireframe, pcd_surface], window_name="High Fidelity Result")
    
    return volume_m3

# --- Run ---
filename = "S001_01-20251122_09_CMD.xyz"
# ใช้ Grid Res 0.5 cm ตามที่ตกลงกันครับ
process_silo_high_fidelity(filename, manual_diameter_cm=50.0, grid_res=0.5)