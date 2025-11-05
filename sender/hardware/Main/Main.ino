#include <AccelStepper.h>
#include "PanTiltScanner.h"
#include <LIDARLite.h> // <-- อย่าลืม!

// -----------------------------------------------------------------
// ++ เพิ่ม 1 บรรทัดนี้ที่นี่ครับ! ++
// (YAW_DIR, YAW_STEP, PITCH_DIR, PITCH_STEP)
PanTiltScanner scanner(26, 32, 33, 25); 
// -----------------------------------------------------------------

const int BUZZER_PIN = 23;
// --- ตัวแปรสำหรับ Core 1 (เหมือนเดิม) ---
TaskHandle_t LidarTaskHandle; 
volatile float latestLidarDistance = 0.0; 
volatile bool newLidarData = false; 

// --- "โปรแกรม" ของ Core 1 (เหมือนเดิม) ---
void LidarReadTask(void * pvParameters)
{
  LIDARLite lidar;
  lidar.begin(0, true);
  lidar.configure(0);
  Serial.println("[Core 1] Lidar Task started.");
  for(;;)
  {
    float dist = lidar.distance(true); 
    latestLidarDistance = dist;
    newLidarData = true;
    vTaskDelay(20 / portTICK_PERIOD_MS); 
  }
}

// -----------------------------------------------------------------
// Setup (Core 0) (เหมือนเดิม)
// -----------------------------------------------------------------
void setup()
{
  Serial.begin(115200);
  delay(10000);
  scanner.setInvertVertical(true);  
  scanner.setZAxisUp(false);
  long MAX_SPEED = 8000;
  long MAX_ACCEL = 4000;
  long SCAN_SPEED_YAW = 3000; 
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, HIGH);
  scanner.begin(MAX_SPEED, MAX_ACCEL, BUZZER_PIN); // <-- ตอนนี้ 'scanner' ถูกต้องแล้ว
  
  xTaskCreatePinnedToCore(
    LidarReadTask, "LidarTask", 10000, NULL, 1, &LidarTaskHandle, 1
  );

  scanner.setScanParameters(
    -45, 45, 
    -90.0, 40.0, 0.05, 
    SCAN_SPEED_YAW 
  );

  scanner.startScanning();
}

// -----------------------------------------------------------------
// Loop (Core 0) (เหมือนเดิม)
// -----------------------------------------------------------------
void loop()
{
  // 1. สั่งให้มอเตอร์ทำงานตลอดเวลา
  scanner.run(); // <-- ตอนนี้ 'scanner' ถูกต้องแล้ว

  // 2. ตรวจสอบว่ามี "ข้อมูลใหม่" จาก Core 1 หรือไม่
  if (newLidarData) {
    float distance = latestLidarDistance;
    newLidarData = false; 
    
    // 3. ถ้ามี ให้ "ประทับตรา" (Timestamp) ข้อมูลนั้นทันที
    scanner.logCurrentPosition(distance);
  }
}