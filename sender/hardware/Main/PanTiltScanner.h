#ifndef PAN_TILT_SCANNER_H
#define PAN_TILT_SCANNER_H

#include <Arduino.h>
#include <math.h>
#include <AccelStepper.h>

// สถานะ (เหมือนเดิม)
enum ScanState {
  IDLE,
  MOVING_TO_START, 
  SCANNING_FWD,    
  SCANNING_REV,    
  CHANGING_ROW, 
  RETURNING_HOME,   
  FINISHED
};

class PanTiltScanner
{
public:
  // --- ฟังก์ชัน Public (เหมือนเดิม) ---
  PanTiltScanner(int yaw_dir_pin, int yaw_step_pin, int pitch_dir_pin, int pitch_step_pin);
  void begin(long max_speed, long max_accel, int buzzer_pin);
  void setScanParameters(float y_start, float y_end, float p_start, float p_end, float p_step, long scan_speed);
  void startScanning();
  void run(); 
  void logCurrentPosition(float distance); 
  void ResetOrigin(); 
  float GetCurrentYaw();
  float GetCurrentPitch();

  // ++ เพิ่มฟังก์ชัน Public 2 ตัวนี้ ++
  void setInvertVertical(bool invert);
  void setZAxisUp(bool z_is_up);

// -----------------------------------------------------------------
// ++ นี่คือส่วนที่ผมทำพลาด และเติมให้ครบแล้ว ++
// -----------------------------------------------------------------
private:
  // --- Constants ---
  const float _YAW_STEPS_PER_REV = (200.0 * 4.0) * 16.0;
  const float _PITCH_STEPS_PER_REV = (200.0 * 3.0) * 16.0;

  // --- Objects ---
  AccelStepper _yawStepper;
  AccelStepper _pitchStepper;

  // --- Private Helper Functions (นี่คือที่ขาดไปครับ) ---
  void _CalculateAndPrintXYZ(float distance_cm, float yaw_deg, float pitch_deg);
  long _YawDegToSteps(float deg);
  long _PitchDegToSteps(float deg);     // <-- ขาดตัวนี้
  float _YawStepsToDeg(long steps);     // <-- ขาดตัวนี้
  float _PitchStepsToDeg(long steps);   // <-- ขาดตัวนี้

  
  // --- State Machine Variables ---
  ScanState _state = IDLE;
  float _yaw_start_deg, _yaw_end_deg;
  float _pitch_start_deg, _pitch_end_deg, _pitch_step_deg;
  long _scan_speed_yaw; 
  float _current_pitch_target_deg;
  bool _is_scanning_fwd = true; 
  // ++ เพิ่มตัวแปร Private 2 ตัวนี้ (สำหรับเก็บค่า setting) ++
  bool _invert_vertical_axis = false;
  bool _z_axis_is_up = false;
  int _BUZZER_PIN = -1;
};
// -----------------------------------------------------------------

#endif