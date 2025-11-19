#include <AccelStepper.h>
#include "PanTiltScanner.h"
#include <Wire.h> // <-- ตรวจสอบว่ามีบรรทัดนี้

// --- พิน Hardware (อัปเดต) ---
const int RED_LED_PIN = 15;
const int YELLOW_LED_PIN = 2; // (ส้ม/เหลือง)
const int GREEN_LED_PIN = 4;
const int BUZZER_PIN = 23;
const int ENABLE_PIN = 27;  // <-- เพิ่มพิน Enable

// --- สร้าง Object (เหมือนเดิม) ---
PanTiltScanner scanner(26, 32, 33, 25); 

// (LidarReadTask และตัวแปร Core 1 ทั้งหมด... ถูกย้ายไปใน Class แล้ว)

// -----------------------------------------------------------------
// Setup (Core 0) (อัปเดต)
// -----------------------------------------------------------------
void setup()
{
  Serial.begin(115200);
  Wire.begin(); 

  // --- ตั้งค่าพิน Hardware ---
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(YELLOW_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, HIGH); // (สำหรับ Active-LOW Buzzer)
  pinMode(ENABLE_PIN, OUTPUT);  // <-- ตั้งค่าพิน Enable
  
  // --- ตั้งค่ามอเตอร์ ---
  long MAX_SPEED = 16000;
  long MAX_ACCEL = 8000;
  long SCAN_SPEED_YAW = 1000; 
  
  // ++ อัปเดต: ส่งพินทั้งหมดไปให้ Class ++
  scanner.begin(MAX_SPEED, MAX_ACCEL, BUZZER_PIN, RED_LED_PIN, YELLOW_LED_PIN, GREEN_LED_PIN, ENABLE_PIN); 
  
  // --- ตั้งค่าพารามิเตอร์สแกน (เหมือนเดิม) ---
  scanner.setScanParameters(
    -180.0,180.0 , //yaw
    -90.0, 0.0, 10.0, //pitch 
    SCAN_SPEED_YAW 
  );

  // --- ตั้งค่าแกน (เหมือนเดิม) ---
  scanner.setInvertVertical(false); 
  scanner.setZAxisUp(false); 

  Serial.println("System Ready. Waiting for server command...");
}

// -----------------------------------------------------------------
// Loop (Core 0) (เหมือนเดิม)
// -----------------------------------------------------------------
void loop()
{
  // 1. (สำคัญ) ต้องเรียก .run() ตลอดเวลา
  scanner.run();

  if (scanner.hasNewLidarData()) 
  {
    // 2.1 ดึงข้อมูลระยะทาง (ซึ่งจะรีเซ็ตธง _newLidarData)
    float distance = scanner.getAndConsumeLidarData();
    
    // 2.2 ส่งระยะทางไปคำนวณ XYZ และเพิ่มลงในคิว
    // (ฟังก์ชันนี้จะเช็คเองว่าอยู่ในสถานะ SCANNING หรือไม่)
    scanner.logCurrentPosition(distance);
  }
  //

  // 2. ตรวจสอบคำสั่ง Serial (เหมือนเดิม)
  if (Serial.available() > 0) 
  {
    char command = Serial.read(); 
    if (command != '\n' && command != '\r') 
    {
      if (command == '1') {
        if (scanner.getState() == IDLE || scanner.getState() == FINISHED) {
          Serial.println("Server command '1' received. Starting full scan...");
          scanner.StartFullScan(); 
        } else {
          Serial.println("Scanner is busy!"); 
        }
      }
      else {
        Serial.printf("Unknown command: %c\n", command);
      }
    }
  }

  // 3. "ดึงข้อมูล X Y Z" (Getter) (เหมือนเดิม)
  XYZPoint newPoint; 
  if (scanner.GetNextPoint(newPoint)) 
  {
    Serial.printf("%.2f %.2f %.2f\n", newPoint.x, newPoint.y, newPoint.z);
  }
  
  // 4. โค้ดป้องกัน Watchdog Crash (เหมือนเดิม)
  ScanState currentState = scanner.getState();
    if (currentState == IDLE || currentState == FINISHED)
    {
      vTaskDelay(1 / portTICK_PERIOD_MS); 
    }
}