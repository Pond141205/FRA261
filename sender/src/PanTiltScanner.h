#ifndef PAN_TILT_SCANNER_H
#define PAN_TILT_SCANNER_H

#include <Arduino.h>
#include <math.h>
#include <AccelStepper.h>
#include <LIDARLite.h>
#include <queue>      
#include <Wire.h> 

// --- สถานะการทำงาน ---
enum ScanState {
  IDLE,
  MOVING_TO_START, 
  SCANNING_FWD,    
  SCANNING_REV,    
  CHANGING_ROW,    
  RETURNING_HOME,
  FINISHED
};

// ++ สร้าง Struct สำหรับเก็บข้อมูล XYZ ++
struct XYZPoint {
  float x;
  float y;
  float z;
};

class PanTiltScanner
{
public:
  // --- ฟังก์ชัน Public (สำหรับ .ino เรียกใช้) ---
  PanTiltScanner(int yaw_dir_pin, int yaw_step_pin, int pitch_dir_pin, int pitch_step_pin);
  
  // ++ อัปเดต: เพิ่มพิน LED/Enable ++
  void begin(long max_speed, long max_accel, int buzzer_pin, int red_pin, int yellow_pin, int green_pin, int enable_pin);
  
  void setScanParameters(float y_start, float y_end, float p_start, float p_end, float p_step, long scan_speed);
  void StartFullScan(); 
  void run(); 
  void logCurrentPosition(float distance); 

  bool hasNewLidarData();
  float getAndConsumeLidarData();
  
  // --- ฟังก์ชัน Getter ---
  bool GetNextPoint(XYZPoint &point); 
  size_t getQueueSize();
  ScanState getState(); 
  float GetCurrentYaw();
  float GetCurrentPitch();

  // --- ฟังก์ชันตั้งค่า ---
  void ResetOrigin(); 
  void setInvertVertical(bool invert);
  void setZAxisUp(bool z_is_up);
  void setLEDError(bool error);

private:
  // --- Task สำหรับ Core 1 ---
  static void LidarReadTask(void * pvParameters); 

  // --- Private Helper Functions ---
  void _startStateMachine(); 
  XYZPoint _CalculateXYZ(float distance_cm, float yaw_deg, float pitch_deg); 
  long _YawDegToSteps(float deg);
  long _PitchDegToSteps(float deg);
  float _YawStepsToDeg(long steps);
  float _PitchStepsToDeg(long steps);
  float _calibrateLidar(float raw_dist); // <-- เราจะเปลี่ยนเนื้อหาของฟังก์ชันนี้
  void _updateLEDs(); // <-- เราจะเปลี่ยนเนื้อหาของฟังก์ชันนี้

  // --- ตัวแปร Hardware ---
  const float _YAW_STEPS_PER_REV = (200.0 * 4.0) * 16.0;
  const float _PITCH_STEPS_PER_REV = (200.0 * 3.0) * 16.0;
  AccelStepper _yawStepper;
  AccelStepper _pitchStepper;
  LIDARLite _lidar; 

  // --- ตัวแปร State Machine ---
  ScanState _state = IDLE;
  float _yaw_start_deg, _yaw_end_deg;
  float _pitch_start_deg, _pitch_end_deg, _pitch_step_deg;
  long _scan_speed_yaw; 
  float _current_pitch_target_deg;
  bool _is_scanning_fwd = true; 

  // --- ตัวแปร Hardware Pins & States ---
  int _BUZZER_PIN = -1;
  int _RED_PIN = -1;
  int _YELLOW_PIN = -1;
  int _GREEN_PIN = -1;
  int _ENABLE_PIN = -1; // <-- เพิ่ม
  bool _errorState = false;
  bool _invert_vertical = false;
  bool _z_axis_is_up = false;
  
  // --- ตัวแปรสำหรับ Multitasking ---
  TaskHandle_t _lidarTaskHandle = NULL;
  volatile float _latestLidarDistance = 0.0;
  volatile bool _newLidarData = false;
  volatile bool _lidarError = false;

  // ++ คิวสำหรับเก็บข้อมูล XYZ ++
  std::queue<XYZPoint> _pointQueue;
};

#endif