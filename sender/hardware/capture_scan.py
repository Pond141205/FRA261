import serial
import serial.tools.list_ports # ใช้สำหรับช่วยหา Port
import time

# --- การตั้งค่า ---
BAUD_RATE = 115200
OUTPUT_FILE = 'scan_data.xyz' # ชื่อไฟล์ที่จะเซฟ
SERIAL_PORT = None # เดี๋ยวเราจะให้มันหาเอง

# --- ฟังก์ชันช่วยหา Port ---
def find_arduino_port():
    """พยายามหา Port ของ Arduino อัตโนมัติ"""
    print("Searching for Arduino port...")
    ports = serial.tools.list_ports.comports()
    for port in ports:
        # ลองค้นหาจากชื่อที่มักจะเป็นของ Arduino/ESP
        if 'CH340' in port.description or \
           'USB-SERIAL' in port.description or \
           'CP210' in port.description or \
           'Arduino' in port.description:
            print(f"Found! Using port: {port.device}")
            return port.device
            
    print("--- WARNING ---")
    print("Could not automatically find Arduino.")
    print("Please enter the port manually (e.g., COM5 or /dev/ttyUSB0):")
    return input("Port: ")

# --- ฟังก์ชันหลัก ---
def start_capture():
    global SERIAL_PORT
    SERIAL_PORT = find_arduino_port()

    print(f"\nAttempting to connect to {SERIAL_PORT} at {BAUD_RATE} baud.")
    print("!!! สำคัญ: ปิด Arduino Serial Monitor ก่อนรันสคริปต์นี้ !!!")

    try:
        # เปิดการเชื่อมต่อ Serial
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        
        # รอ Arduino รีเซ็ตตัวเอง (เป็นเรื่องปกติเมื่อเปิด Port)
        print("Waiting for device to initialize...")
        time.sleep(2) 
        ser.flushInput() # ล้างข้อมูลขยะที่อาจค้างอยู่
        
        print(f"Connected. Capturing data to '{OUTPUT_FILE}'...")
        print("Press Ctrl+C to stop capturing.")

        # เปิดไฟล์ .xyz เพื่อรอเขียน
        with open(OUTPUT_FILE, 'w') as f:
            line_count = 0
            while True:
                try:
                    # 1. อ่าน 1 บรรทัด (เป็น bytes)
                    line_bytes = ser.readline()
                    
                    if not line_bytes:
                        continue # ถ้าว่าง (timeout) ก็ข้ามไป

                    # 2. แปลงจาก bytes เป็น string
                    line_str = line_bytes.decode('utf-8').strip()

                    # 3. (สำคัญ) กรองข้อมูล
                    if line_str and (line_str[0].isdigit() or line_str[0] == '-'):
                        # ถ้าบรรทัดนั้นขึ้นต้นด้วยตัวเลข หรือ เครื่องหมายลบ
                        # แปลว่านี่คือข้อมูล x y z ที่เราต้องการ
                        f.write(line_str + '\n')
                        line_count += 1
                        
                        # พิมพ์ออกหน้าจอทุกๆ 100 จุด เพื่อให้รู้ว่าทำงานอยู่
                        if line_count % 100 == 0:
                            print(f"Captured {line_count} points...")
                    
                    elif line_str:
                        # ถ้าเป็นบรรทัดอื่น (เช่น "Scan Complete.")
                        # ให้พิมพ์เป็นสถานะแทน
                        print(f"[STATUS] {line_str}")

                except Exception as e:
                    print(f"Warning: Could not read line. {e}")

    except serial.SerialException as e:
        print("\n--- ERROR ---")
        print(f"Serial Error: {e}")
        print(f"ไม่สามารถเปิด Port {SERIAL_PORT} ได้")
        print("1. Arduino เสียบสายอยู่หรือไม่?")
        print("2. คุณปิด Serial Monitor ใน Arduino IDE แล้วหรือยัง?")
        print("3. Port ที่เลือกถูกต้องหรือไม่?")
        
    except KeyboardInterrupt:
        # เมื่อผู้ใช้กด Ctrl+C
        print("\n---------------------------------")
        print("Capture stopped by user.")
        
    finally:
        # ปิด Port เสมอ ไม่ว่าจะเกิดอะไรขึ้น
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print(f"Port {SERIAL_PORT} closed.")
            print(f"File '{OUTPUT_FILE}' saved successfully.")

# --- เริ่มการทำงาน ---
if __name__ == "__main__":
    start_capture()