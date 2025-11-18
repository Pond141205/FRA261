import serial
import serial.tools.list_ports
import time
import numpy as np
import open3d as o3d

# --- Settings ---
BAUD_RATE = 115200
POINTS_PER_UPDATE = 10  # Update screen every 10 points (smoother)

def find_arduino_port():
    print("Searching for Serial port...")
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if 'CH340' in port.description or 'USB-SERIAL' in port.description or 'CP210' in port.description:
            return port.device
    return input("Port not found automatically. Enter manually (e.g., COM3): ")

def main():
    # 1. Setup Serial
    port_name = find_arduino_port()
    try:
        ser = serial.Serial(port_name, BAUD_RATE, timeout=1)
        time.sleep(2) # Wait for reboot
        ser.flushInput()
        print(f"Connected to {port_name}")
        
        # Send Start Command
        print("Sending Start Command '1'...")
        ser.write(b'1')
    except Exception as e:
        print(f"Error opening serial: {e}")
        return

    # 2. Setup Open3D Visualizer
    vis = o3d.visualization.Visualizer()
    vis.create_window(window_name="Real-Time Silo Scan", width=800, height=600)
    
    # Create an empty Point Cloud
    pcd = o3d.geometry.PointCloud()
    # Initialize with one dummy point so Open3D doesn't crash
    pcd.points = o3d.utility.Vector3dVector(np.array([[0,0,0]])) 
    vis.add_geometry(pcd)

    # Create a coordinate frame (X=Red, Y=Green, Z=Blue)
    axis = o3d.geometry.TriangleMesh.create_coordinate_frame(size=20.0, origin=[0, 0, 0])
    vis.add_geometry(axis)

    # Setup View Control
    ctr = vis.get_view_control()
    ctr.set_zoom(0.8)

    print("Starting Real-Time Capture... (Press 'Q' in the window to exit)")
    
    all_points = []
    
    try:
        while True:
            # A. Keep the window responsive
            keep_running = vis.poll_events()
            vis.update_renderer()
            if not keep_running:
                break
            
            # B. Read Serial Data
            if ser.in_waiting:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    
                    # Parse X Y Z
                    if line and (line[0].isdigit() or line[0] == '-'):
                        parts = line.split()
                        if len(parts) == 3:
                            x, y, z = map(float, parts)
                            all_points.append([x, y, z])
                            
                            # C. Update Visualization every N points
                            if len(all_points) % POINTS_PER_UPDATE == 0:
                                # Update the Point Cloud object
                                pcd.points = o3d.utility.Vector3dVector(np.array(all_points))
                                vis.update_geometry(pcd)
                                print(f"Points: {len(all_points)}", end='\r')
                                
                    elif line.startswith("[STATUS]"):
                        print(f"\n{line}")
                        
                except ValueError:
                    pass # Ignore bad parsing
                    
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        ser.close()
        vis.destroy_window()
        print(f"Scan Finished. Total points: {len(all_points)}")
        
        # Optional: Save to file at the end
        if len(all_points) > 0:
            save = input("Save to file? (y/n): ")
            if save.lower() == 'y':
                with open("realtime_data.xyz", "w") as f:
                    for p in all_points:
                        f.write(f"{p[0]} {p[1]} {p[2]}\n")
                print("Saved to realtime_data.xyz")

if __name__ == "__main__":
    main()