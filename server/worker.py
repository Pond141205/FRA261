import time
from run_meshing import run_mesh_reconstruction

def main_worker_loop():
    print("--- Starting Mesh Reconstruction Worker ---")
    print("Worker will check for new scans every 60 seconds.")
    print("To stop, press Ctrl+C")
    
    while True:
        try:
            # Run the meshing function
            # It will return True if it did work, False if it found no jobs
            work_done = run_mesh_reconstruction()
            
            if work_done:
                print("Work complete. Checking again immediately...")
                # Don't sleep, check right away if there's more in the queue
                continue 
            else:
                # No work found, sleep for 60 seconds
                time.sleep(60)

        except Exception as e:
            print(f"An error occurred in the worker loop: {e}")
            print("Restarting loop in 60 seconds...")
            time.sleep(60)

if __name__ == "__main__":
    main_worker_loop()