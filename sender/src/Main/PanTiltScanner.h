#ifndef PAN_TILT_SCANNER_H
#define PAN_TILT_SCANNER_H

#include <Arduino.h>
#include <math.h>
#include <AccelStepper.h>
#include <queue>       
#include <Wire.h>
#include <AS5600.h>

// ==========================================
//  MECHANICAL CALIBRATION (FROM TEST SKETCH)
// ==========================================
// The angle the encoder reads when the machine is at "Home"
#define YAW_HOME_ANGLE   288.0 
#define PITCH_HOME_ANGLE 61.0

// Homing Direction Logic (True = Flip direction)
#define INVERT_YAW_HOMING   true  
#define INVERT_PITCH_HOMING false 

// Homing Accuracy (Degrees)
#define HOMING_DEADZONE     4.5   

enum ScanState {
  IDLE,
  MOVING_TO_START, 
  SCANNING_FWD,    
  SCANNING_REV,    
  CHANGING_ROW,    
  RETURNING_HOME,
  FINISHED
};

struct XYZPoint {
  float x;
  float y;
  float z;
};

class PanTiltScanner
{
public:
  PanTiltScanner(int yaw_dir_pin, int yaw_step_pin, int pitch_dir_pin, int pitch_step_pin);
  
  void begin(long max_speed, long max_accel, int status_led_pin, int enable_pin, AS5600* yawEnc, AS5600* pitchEnc);
  
  void setScanParameters(float y_start, float y_end, float p_start, float p_end, float p_step, long scan_speed);
  void StartFullScan(); 
  void run(); 
  void logCurrentPosition(float distance); 

  bool hasNewLidarData();
  float getAndConsumeLidarData();
  
  bool GetNextPoint(XYZPoint &point); 
  size_t getQueueSize();
  ScanState getState(); 

  // --- CLOSED LOOP FUNCTIONS ---
  void DriveToAbsoluteZero(); // Uses the 288/61 Targets
  void ResetOrigin();         
  
  float GetCurrentYaw();      
  float GetCurrentPitch();    
  float GetEncoderYaw();      // Returns (Raw - 288)
  float GetEncoderPitch();    // Returns (Raw - 61)

  void setInvertVertical(bool invert);
  void setZAxisUp(bool z_is_up);
  void setLEDError(bool error);

private:
  static void LidarReadTask(void * pvParameters); 

  void _startStateMachine(); 
  void _handleStatusLED();
  XYZPoint _CalculateXYZ(float distance_cm, float yaw_deg, float pitch_deg); 
  
  long _YawDegToSteps(float deg);
  long _PitchDegToSteps(float deg);
  float _YawStepsToDeg(long steps);
  float _PitchStepsToDeg(long steps);
  float _calibrateLidar(float raw_dist); 
  
  // --- ENCODER HELPERS ---
  float _readEncoderDeg(AS5600* enc, float offset);
  float _getShortestPathError(float current, float target); 

  // --- HARDWARE OBJECTS ---
  const float _YAW_STEPS_PER_REV = (200.0 * 4.0) * 16.0;
  const float _PITCH_STEPS_PER_REV = (200.0 * 3.0) * 16.0;
  
  AccelStepper _yawStepper;
  AccelStepper _pitchStepper;
  
  AS5600* _yawEncoder = NULL;
  AS5600* _pitchEncoder = NULL;

  ScanState _state = IDLE;
  float _yaw_start_deg, _yaw_end_deg;
  float _pitch_start_deg, _pitch_end_deg, _pitch_step_deg;
  long _scan_speed_yaw; 
  float _current_pitch_target_deg;
  bool _is_scanning_fwd = true; 

  int _STATUS_LED_PIN = -1;
  int _ENABLE_PIN = -1;
  bool _errorState = false;
  bool _invert_vertical = false;
  bool _z_axis_is_up = false;
  bool _ledState = false;
  unsigned long _lastBlinkTime = 0;
  
  TaskHandle_t _lidarTaskHandle = NULL;
  volatile float _latestLidarDistance = 0.0;
  volatile bool _newLidarData = false;
  volatile bool _lidarError = false;

  std::queue<XYZPoint> _pointQueue;
};

#endif
