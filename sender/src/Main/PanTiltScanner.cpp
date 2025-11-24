#include "PanTiltScanner.h"

// --- CONFIG FOR WAVESHARE TOF (D) ---
#define TOF_RX_PIN 16
#define TOF_TX_PIN 17
#define TOF_BAUD_RATE 921600
#define TOF_HEADER 0x57
#define TOF_FUNC_MARK 0x00
#define TOF_FRAME_LEN 16

PanTiltScanner::PanTiltScanner(int yaw_dir_pin, int yaw_step_pin, int pitch_dir_pin, int pitch_step_pin)
  : _yawStepper(AccelStepper::DRIVER, yaw_step_pin, yaw_dir_pin),
    _pitchStepper(AccelStepper::DRIVER, pitch_step_pin, pitch_dir_pin)
{
}

bool PanTiltScanner::hasNewLidarData() { return _newLidarData; }

float PanTiltScanner::getAndConsumeLidarData() {
  _newLidarData = false; 
  return _latestLidarDistance;
}

// -----------------------------------------------------------------
// INITIALIZATION
// -----------------------------------------------------------------
void PanTiltScanner::begin(long max_speed, long max_accel, int status_led_pin, int enable_pin, AS5600* yawEnc, AS5600* pitchEnc)
{
  _yawStepper.setMaxSpeed(max_speed);
  _yawStepper.setAcceleration(max_accel);
  _pitchStepper.setMaxSpeed(max_speed);
  _pitchStepper.setAcceleration(max_accel);
  
  _yawEncoder = yawEnc;
  _pitchEncoder = pitchEnc;
  _STATUS_LED_PIN = status_led_pin;
  _ENABLE_PIN = enable_pin;

  if (_STATUS_LED_PIN != -1) pinMode(_STATUS_LED_PIN, OUTPUT);
  if (_ENABLE_PIN != -1) pinMode(_ENABLE_PIN, OUTPUT);

  // We DO NOT read start offset anymore. 
  // We rely on YAW_HOME_ANGLE (288) and PITCH_HOME_ANGLE (61) defined in .h

  Serial.println("[Scanner] Init Complete. Hardware Targets: Yaw=288, Pitch=61.");
  _state = IDLE; 
}

// -----------------------------------------------------------------
// DRIVE TO ABSOLUTE ZERO (INTEGRATED FROM TEST SKETCH)
// -----------------------------------------------------------------
void PanTiltScanner::DriveToAbsoluteZero() {
  Serial.println("\n--- HOMING SEQUENCE START ---");
  
  // 1. Setup for Homing (Slower, Safe)
  _yawStepper.setMaxSpeed(1000);
  _yawStepper.setAcceleration(2000);
  _pitchStepper.setMaxSpeed(1000);
  _pitchStepper.setAcceleration(2000);

  if (_ENABLE_PIN != -1) digitalWrite(_ENABLE_PIN, LOW); // Enable Motors

  // --- HOME YAW to 288.0 ---
  if (_yawEncoder) {
    Serial.print("Homing Yaw to "); Serial.println(YAW_HOME_ANGLE);
    bool isHome = false;
    int attempts = 0;
    
    while (!isHome && attempts < 25) {
      float raw = (_yawEncoder->readAngle() * 360.0) / 4096.0; // Read RAW
      float error = _getShortestPathError(raw, YAW_HOME_ANGLE); // Calc error to 288
      
      Serial.printf("[YAW] Raw: %.2f | Error: %.2f\n", raw, error);

      if (abs(error) <= HOMING_DEADZONE) {
        isHome = true;
      } else {
        long steps = _YawDegToSteps(error);
        if (INVERT_YAW_HOMING) steps = -steps; // Apply Tested Inversion

        // Minimum move check to overcome friction
        if (abs(steps) < 10) steps = (steps > 0) ? 10 : -10;

        _yawStepper.move(steps);
        while (_yawStepper.distanceToGo() != 0) _yawStepper.run();
        delay(500); // Settle time
      }
      attempts++;
    }
    _yawStepper.setCurrentPosition(0); // 0 Steps = 288 Degrees
  }

  // --- HOME PITCH to 61.0 ---
  if (_pitchEncoder) {
    Serial.print("Homing Pitch to "); Serial.println(PITCH_HOME_ANGLE);
    bool isHome = false;
    int attempts = 0;
    
    while (!isHome && attempts < 25) {
      float raw = (_pitchEncoder->readAngle() * 360.0) / 4096.0;
      float error = _getShortestPathError(raw, PITCH_HOME_ANGLE);
      
      Serial.printf("[PITCH] Raw: %.2f | Error: %.2f\n", raw, error);

      if (abs(error) <= HOMING_DEADZONE) {
        isHome = true;
      } else {
        long steps = _PitchDegToSteps(error);
        if (INVERT_PITCH_HOMING) steps = -steps; // Apply Tested Inversion

        if (abs(steps) < 50) steps = (steps > 0) ? 50 : -50;

        _pitchStepper.move(steps);
        while (_pitchStepper.distanceToGo() != 0) _pitchStepper.run();
        delay(500);
      }
      attempts++;
    }
    _pitchStepper.setCurrentPosition(0); // 0 Steps = 61 Degrees
  }

  // Restore High Speeds for Scanning
  _yawStepper.setMaxSpeed(16000);     // Restore from setup
  _yawStepper.setAcceleration(8000);
  _pitchStepper.setMaxSpeed(16000);
  _pitchStepper.setAcceleration(8000);

  _state = IDLE;
  Serial.println("--- HOMING COMPLETE ---");
}

// -----------------------------------------------------------------
// CORE LOGIC
// -----------------------------------------------------------------

void PanTiltScanner::logCurrentPosition(float distance) 
{
  if (_state != SCANNING_FWD && _state != SCANNING_REV) return;

  // USE ENCODERS FOR CALCULATION
  // GetEncoderYaw() now returns (Raw - 288), so it gives 0.0 when at home.
  float calc_yaw = (_yawEncoder) ? GetEncoderYaw() : GetCurrentYaw();
  float calc_pitch = (_pitchEncoder) ? GetEncoderPitch() : GetCurrentPitch();

  // Bounds Check
  if (_is_scanning_fwd && calc_yaw > (_yaw_end_deg + 5.0)) return; // Increased margin for Deadzone
  if (!_is_scanning_fwd && calc_yaw < (_yaw_start_deg - 5.0)) return;

  float calibrated_dist = _calibrateLidar(distance);
  XYZPoint newPoint = _CalculateXYZ(calibrated_dist, calc_yaw, calc_pitch);
  _pointQueue.push(newPoint);
}

void PanTiltScanner::StartFullScan()
{
  if (_lidarTaskHandle != NULL) {
    vTaskDelete(_lidarTaskHandle);
    _lidarTaskHandle = NULL;
  }
  std::queue<XYZPoint> empty;
  std::swap(_pointQueue, empty);
  
  xTaskCreatePinnedToCore(
    LidarReadTask, "LidarTask", 10000, this, 1, &_lidarTaskHandle, 0
  );
  _startStateMachine();
}

void PanTiltScanner::_startStateMachine()
{
  Serial.println("[Core 0] Starting Scan...");
  _current_pitch_target_deg = _pitch_start_deg;
  
  // Move to Start
  _pitchStepper.moveTo(_PitchDegToSteps(_current_pitch_target_deg));
  _yawStepper.moveTo(_YawDegToSteps(_yaw_start_deg));
  
  _is_scanning_fwd = true; 
  _state = MOVING_TO_START;
}

void PanTiltScanner::run()
{
  _handleStatusLED();

  // // >>> NEW: If a Lidar error occurs, force state to FINISHED (or add an ERROR state)
  // if (_lidarError && _state != IDLE && _state != FINISHED) {
  //     Serial.println("!!! CRITICAL Lidar Error Detected. Stopping Scan. !!!");
  //     _state = FINISHED; 
  //     // Stop steppers immediately to avoid runaway motion
  //     _yawStepper.stop();
  //     _pitchStepper.stop();
  //     // The FINISHED state logic will clean up the task and disable motors
  // }

  if (_ENABLE_PIN != -1) {
    if (_state == IDLE || _state == FINISHED || _errorState) {
      digitalWrite(_ENABLE_PIN, HIGH); 
    } else {
      digitalWrite(_ENABLE_PIN, LOW); 
    }
  }

  if (_state == IDLE) return; 
  
  if (_state == FINISHED) {
    if (_lidarTaskHandle != NULL) {
      vTaskDelete(_lidarTaskHandle);
      _lidarTaskHandle = NULL;
    }
    return; 
  }

  if (_state == SCANNING_FWD || _state == SCANNING_REV) {
    _pitchStepper.run(); 
    _yawStepper.runSpeed(); 
  } else {
    _pitchStepper.run();
    _yawStepper.run(); 
  }

  float current_yaw_steps = _YawStepsToDeg(_yawStepper.currentPosition()); 

  switch (_state) {
    case MOVING_TO_START:
      if (!_yawStepper.isRunning() && !_pitchStepper.isRunning()) {
        _is_scanning_fwd = true; 
        _yawStepper.setSpeed(_scan_speed_yaw);
        _state = SCANNING_FWD;
      }
      break;
    case SCANNING_FWD:
      if (current_yaw_steps >= _yaw_end_deg) {
        _yawStepper.stop();
        _yawStepper.setCurrentPosition(_yawStepper.currentPosition());
        _yawStepper.setSpeed(0);

        //_yawStepper.stop(); 
        _state = CHANGING_ROW; 
        _current_pitch_target_deg += _pitch_step_deg; 
        _pitchStepper.moveTo(_PitchDegToSteps(_current_pitch_target_deg)); 
      }
      break;
    case SCANNING_REV:
      if (current_yaw_steps <= _yaw_start_deg) {
        _yawStepper.stop();
        _yawStepper.setCurrentPosition(_yawStepper.currentPosition());
        _yawStepper.setSpeed(0);

        //_yawStepper.stop(); 
        _state = CHANGING_ROW; 
        _current_pitch_target_deg += _pitch_step_deg; 
        _pitchStepper.moveTo(_PitchDegToSteps(_current_pitch_target_deg)); 
      }
      break;
    case CHANGING_ROW:
      if (!_pitchStepper.isRunning() && !_yawStepper.isRunning()) { 
        if (_current_pitch_target_deg > _pitch_end_deg) {
          Serial.println("Scan Complete. Returning Home...");
          _pitchStepper.moveTo(0); 
          _yawStepper.moveTo(0);   
          _state = RETURNING_HOME; 
        } else {

          _yawStepper.stop();
          _yawStepper.setCurrentPosition(_yawStepper.currentPosition());
          _yawStepper.setSpeed(0);

          if (_is_scanning_fwd) { 
             _is_scanning_fwd = false;
             _yawStepper.setSpeed(-_scan_speed_yaw); 
             _state = SCANNING_REV;
          } else {
             _is_scanning_fwd = true;
             _yawStepper.setSpeed(_scan_speed_yaw); 
             _state = SCANNING_FWD;
          }
        }
      }
      break;
    case RETURNING_HOME:
      if (!_pitchStepper.isRunning() && !_yawStepper.isRunning()) {
        _state = FINISHED; 
      }
      break;
    case FINISHED:
      break; 
  }
}

// -----------------------------------------------------------------
// HELPER FUNCTIONS
// -----------------------------------------------------------------
void PanTiltScanner::LidarReadTask(void * pvParameters)
{
  PanTiltScanner* scanner = static_cast<PanTiltScanner*>(pvParameters);
  Serial2.begin(TOF_BAUD_RATE, SERIAL_8N1, TOF_RX_PIN, TOF_TX_PIN);
  byte buffer[TOF_FRAME_LEN];
  
  for(;;) {
    if (Serial2.available() >= TOF_FRAME_LEN) {
      if (Serial2.read() == TOF_HEADER) {
        if (Serial2.read() == TOF_FUNC_MARK) {
           buffer[0] = TOF_HEADER; buffer[1] = TOF_FUNC_MARK;
           Serial2.readBytes(&buffer[2], TOF_FRAME_LEN - 2);
           uint8_t checksum = 0;
           for (int i = 0; i < TOF_FRAME_LEN - 1; i++) checksum += buffer[i];

           if (checksum == buffer[TOF_FRAME_LEN - 1]) {
             uint32_t dist_mm = buffer[8] | (buffer[9] << 8) | (buffer[10] << 16);
             if (dist_mm > 0 && dist_mm < 50000) { 
               scanner->_latestLidarDistance = (float)dist_mm / 10.0;
               scanner->_newLidarData = true;
               scanner->_lidarError = false;
             } else {
               scanner->_lidarError = true; 
             }
           }
        }
      }
    } else {
      vTaskDelay(1 / portTICK_PERIOD_MS); 
    }
  }
}

void PanTiltScanner::_handleStatusLED() {
  if (_STATUS_LED_PIN == -1) return;
  unsigned long currentMillis = millis();
  int blinkInterval = 0;
  if (_errorState || _lidarError) blinkInterval = 100; 
  else if (_state != IDLE && _state != FINISHED) blinkInterval = 500; 
  else blinkInterval = 0; 

  if (blinkInterval == 0) {
     digitalWrite(_STATUS_LED_PIN, HIGH);
     return;
  }
  if (currentMillis - _lastBlinkTime >= blinkInterval) {
    _lastBlinkTime = currentMillis;
    _ledState = !_ledState;
    digitalWrite(_STATUS_LED_PIN, _ledState ? HIGH : LOW);
  }
}

float PanTiltScanner::_readEncoderDeg(AS5600* enc, float offset) {
  if (!enc) return 0.0;
  float rawDeg = (enc->readAngle() * 360.0) / 4096.0;
  
  // SUBTRACT OFFSET (Raw 288 - Offset 288 = 0)
  float realDeg = rawDeg - offset;
  
  while (realDeg > 180.0) realDeg -= 360.0;
  while (realDeg < -180.0) realDeg += 360.0;
  return realDeg;
}

float PanTiltScanner::_getShortestPathError(float current, float target) {
  float error = target - current;
  if (error > 180.0) error -= 360.0;
  if (error < -180.0) error += 360.0;
  return error;
}

// Getters/Setters
float PanTiltScanner::GetCurrentYaw() { return _YawStepsToDeg(_yawStepper.currentPosition()); }
float PanTiltScanner::GetCurrentPitch() { return _PitchStepsToDeg(_pitchStepper.currentPosition()); }

// IMPORTANT: Pass the HOME ANGLE as the offset here
float PanTiltScanner::GetEncoderYaw() { return _readEncoderDeg(_yawEncoder, YAW_HOME_ANGLE); }
float PanTiltScanner::GetEncoderPitch() { return _readEncoderDeg(_pitchEncoder, PITCH_HOME_ANGLE); }

void PanTiltScanner::setScanParameters(float y_start, float y_end, float p_start, float p_end, float p_step, long scan_speed) {
  _yaw_start_deg = y_start; _yaw_end_deg = y_end;
  _pitch_start_deg = p_start; _pitch_end_deg = p_end; _pitch_step_deg = p_step;
  _scan_speed_yaw = scan_speed;
}

void PanTiltScanner::ResetOrigin() {
  Serial.println("Reset Origin -> Re-Homing...");
  DriveToAbsoluteZero(); 
}

bool PanTiltScanner::GetNextPoint(XYZPoint &point) {
  if (_pointQueue.empty()) return false; 
  point = _pointQueue.front(); _pointQueue.pop(); return true; 
}
size_t PanTiltScanner::getQueueSize() { return _pointQueue.size(); }
ScanState PanTiltScanner::getState() { return _state; }
void PanTiltScanner::setLEDError(bool error) { _errorState = error; }
void PanTiltScanner::setInvertVertical(bool invert) { _invert_vertical = invert; }
void PanTiltScanner::setZAxisUp(bool z_is_up) { _z_axis_is_up = z_is_up; }
float PanTiltScanner::_calibrateLidar(float raw_dist) { return raw_dist; }

XYZPoint PanTiltScanner::_CalculateXYZ(float distance_cm, float yaw_deg, float pitch_deg) {
  float theta = yaw_deg * (M_PI / 180.0);
  float delta = pitch_deg * (M_PI / 180.0);
  float rho = distance_cm; 
  float x = rho * cos(delta) * cos(theta);
  float y = rho * cos(delta) * sin(theta);
  float z = rho * sin(delta);
  if (_invert_vertical) z = -z; 
  XYZPoint point;
  if (_z_axis_is_up) { point.x = x; point.y = y; point.z = z; } 
  else { point.x = x; point.y = z; point.z = -y; }
  return point;
}

long PanTiltScanner::_YawDegToSteps(float deg) { return round(deg * (_YAW_STEPS_PER_REV / 360.0)); }
long PanTiltScanner::_PitchDegToSteps(float deg) { return round(deg * (_PITCH_STEPS_PER_REV / 360.0)); }
float PanTiltScanner::_YawStepsToDeg(long steps) { return (float)steps * (360.0 / _YAW_STEPS_PER_REV); }
float PanTiltScanner::_PitchStepsToDeg(long steps) { return (float)steps * (360.0 / _PITCH_STEPS_PER_REV); }
