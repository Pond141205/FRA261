/*
  LIDARLite Arduino Library
  v3/GetDistanceI2c - المعدل (Modified)

  โค้ดนี้จะรอรับคำสั่ง '1' จาก Serial Monitor
  เมื่อได้รับ '1' จะทำการอ่านค่า 5 ครั้ง,
  "แปลงค่า" ด้วยสมการที่ได้จาก MATLAB,
  พิมพ์ค่าที่แปลงแล้ว (Calibrated) 5 ค่าออกทาง Serial,
  แล้วกลับไปรอรับคำสั่ง '1' อีกครั้ง
*/

#include <Wire.h>
#include <LIDARLite.h>

LIDARLite myLidarLite;

// --- ใส่ค่าคงที่จากสมการของคุณไว้ตรงนี้ ---
// real_distance = A*(sensor_reading)^2 + B*(sensor_reading) + C
const float CALIB_A = 0.0002;
const float CALIB_B = 1.0310;
const float CALIB_C = -6.9883;


void setup()
{
  Serial.begin(115200); // เริ่มการสื่อสาร Serial

  myLidarLite.begin(0, true); // ตั้งค่าเริ่มต้นและ I2C เป็น 400 kHz
  myLidarLite.configure(0); // ใช้การกำหนดค่าเริ่มต้น

  // แจ้งให้ผู้ใช้ทราบว่าพร้อมทำงาน
  Serial.println("Ready. Send '1' to get 5 CALIBRATED readings.");
}

void loop()
{
  // 1. ตรวจสอบว่ามีข้อมูลส่งมาใน Serial หรือไม่
  if (Serial.available() > 0) 
  {
    // 2. อ่านข้อมูลที่ส่งมา (อ่านทีละตัวอักษร)
    char command = Serial.read();

    // 3. ตรวจสอบว่าตัวอักษรที่ส่งมาคือ '1' หรือไม่
    if (command == '1') 
    {
      Serial.println("--- Reading 5 calibrated values ---");
      
      // หมายเหตุ: โค้ดที่คุณส่งมาเปลี่ยนเป็น 5 ครั้งแล้ว ผมจึงแก้คอมเมนต์ให้ตรงกัน
      int numReadings = 5; // จำนวนค่าที่ต้องการอ่าน

      // 4. ถ้าใช่, ให้วนลูป 5 ครั้งเพื่ออ่านและพิมพ์ค่า
      for(int i = 0; i < numReadings; i++)
      {
        // 4.1 อ่านค่าดิบจากเซ็นเซอร์ (เป็น int)
        int sensor_reading_raw = myLidarLite.distance();

        // 4.2 แปลงค่าดิบ (int) เป็น float เพื่อใช้ในการคำนวณ
        float sensor_reading = (float)sensor_reading_raw;
        
        // 4.3 นำไปเข้าสมการ Calibration ที่คุณหามา
        // real_distance = 0.0002 * (sensor_reading)^2 + 1.0310 * (sensor_reading) - 6.9883
        float calibratedDistance = (CALIB_A * sensor_reading * sensor_reading) + (CALIB_B * sensor_reading) + CALIB_C-3;
        if (calibratedDistance<0){
          calibratedDistance += 7;
        }
        else if (calibratedDistance<6){
          calibratedDistance += 3;
        }
        else if (calibratedDistance<11){
          calibratedDistance += 3;
        }
        else if (calibratedDistance<16){
          calibratedDistance += 2;
        }
        else if (calibratedDistance<22){
          calibratedDistance += 3;
        }
        else if (calibratedDistance<30){
          calibratedDistance -= 3;
        }
        else if (calibratedDistance<40){
          calibratedDistance += 3;
        }
        else if (calibratedDistance<45){
          calibratedDistance += 0;
        }
        else if (calibratedDistance<50){
          calibratedDistance -= 3;
        }
        else if (calibratedDistance<68){
          calibratedDistance -= 3;
        }
        else if (calibratedDistance<72){
          calibratedDistance -= 3;
        }
        else if (calibratedDistance<75){
          calibratedDistance += 3;
        }
        else if (calibratedDistance<80){
          calibratedDistance += 3;
        }


        // 4.4 พิมพ์ค่าที่ "แปลงแล้ว" (calibrated) ออกไป
        Serial.println(calibratedDistance);
      }
      
      Serial.println("--- Done. Send '1' again. ---");
    }
  }
  
  // ถ้าไม่มีอะไรส่งมา หรือส่งมาไม่ใช่ '1'
  // โปรแกรมก็จะวนกลับมาที่ loop() เพื่อรอเช็คใหม่
}