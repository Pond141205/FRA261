#include "PanTiltScanner.h"

// --- ค่าคงที่สำหรับ Calibration (จากโค้ดใหม่ของคุณ) ---
const float CALIB_A = 0.0002;
const float CALIB_B = 1.0310;
const float CALIB_C = -6.9883;

// --- Constructor (ไม่เปลี่ยน) ---
PanTiltScanner::PanTiltScanner(int yaw_dir_pin, int yaw_step_pin, int pitch_dir_pin, int pitch_step_pin)
  : _yawStepper(AccelStepper::DRIVER, yaw_step_pin, yaw_dir_pin),
    _pitchStepper(AccelStepper::DRIVER, pitch_step_pin, pitch_dir_pin)
{
}
bool PanTiltScanner::hasNewLidarData()
{
  return _newLidarData;
}

float PanTiltScanner::getAndConsumeLidarData()
{
  _newLidarData = false; // "บริโภค" (Consume) ข้อมูล
  return _latestLidarDistance;
}

// -----------------------------------------------------------------
// ++ begin() (เวอร์ชันอัปเดต) ++
// -----------------------------------------------------------------
void PanTiltScanner::begin(long max_speed, long max_accel, int buzzer_pin, int red_pin, int yellow_pin, int green_pin, int enable_pin)
{
  _yawStepper.setMaxSpeed(max_speed);
  _yawStepper.setAcceleration(max_accel);
  _yawStepper.setCurrentPosition(0); 
  _pitchStepper.setMaxSpeed(max_speed);
  _pitchStepper.setAcceleration(max_accel);
  _pitchStepper.setCurrentPosition(0);
  
  // --- บันทึกพิน ---
  _BUZZER_PIN = buzzer_pin;
  _RED_PIN = red_pin;
  _YELLOW_PIN = yellow_pin;
  _GREEN_PIN = green_pin;
  _ENABLE_PIN = enable_pin;
  
  // --- ส่งเสียงตอนเริ่ม (Active-LOW) ---
  if (_BUZZER_PIN != -1) {
    digitalWrite(_BUZZER_PIN, LOW);  delay(50); 
    digitalWrite(_BUZZER_PIN, HIGH); delay(50); 
    digitalWrite(_BUZZER_PIN, LOW);  delay(50); 
    digitalWrite(_BUZZER_PIN, HIGH);           
  }
  
  Serial.println("[Core 0] Motor Controller Initialized.");
  _state = IDLE; 
  _updateLEDs(); // ตั้งค่าไฟเขียว (Idle) + ปิด Enable
}

// -----------------------------------------------------------------
// ++ เพิ่มฟังก์ชันที่หายไปนี้ (แก้บั๊กครั้งที่แล้ว) ++
// -----------------------------------------------------------------
void PanTiltScanner::setScanParameters(float y_start, float y_end, float p_start, float p_end, float p_step, long scan_speed)
{
  _yaw_start_deg = y_start;
  _yaw_end_deg = y_end;
  _pitch_start_deg = p_start;
  _pitch_end_deg = p_end;
  _pitch_step_deg = p_step;
  _scan_speed_yaw = scan_speed;
}

// --- Task สำหรับ Core 1 (ย้าย Wire.begin() เข้ามาที่นี่) ---
void PanTiltScanner::LidarReadTask(void * pvParameters)
{
  PanTiltScanner* scanner = static_cast<PanTiltScanner*>(pvParameters);

  // ปลุกระบบ I2C "ภายใน Core 1"
  Wire.begin(21, 22); // (SDA, SCL)
  Wire.setClock(400000); 
  
  scanner->_lidar.begin(0, true);
  scanner->_lidar.configure(0);
  Serial.println("[Core 1] Lidar Task started.");

  for(;;)
  {
    float dist = scanner->_lidar.distance(true); 
    
    // ++ ใช้ลอจิก Error จากโค้ด Calibrate ของคุณ ++
    if (dist <= 0) { // Lidar คืนค่า 0 หรือ 1 เมื่อ Error
        scanner->_lidarError = true;
        scanner->_newLidarData = false;
    } else {
        scanner->_lidarError = false;
        scanner->_latestLidarDistance = dist;
        scanner->_newLidarData = true;
    }
    
    vTaskDelay(20 / portTICK_PERIOD_MS); 
  }
}

// -----------------------------------------------------------------
// ++ _calibrateLidar() (แทนที่ด้วยลอจิกใหม่ของคุณ) ++
// -----------------------------------------------------------------
float PanTiltScanner::_calibrateLidar(float raw_dist)
{
  // 1. นำไปเข้าสมการ Polynomial
  float calibratedDistance = (CALIB_A * raw_dist * raw_dist) + (CALIB_B * raw_dist) + CALIB_C - 3;
  
  // 2. นำไปเข้าลอจิก if/else if ที่คุณให้มา
  if (calibratedDistance < 0) {
    calibratedDistance += 7;
  } else if (calibratedDistance < 6) {
    calibratedDistance += 3;
  } else if (calibratedDistance < 11) {
    calibratedDistance += 3;
  } else if (calibratedDistance < 16) {
    calibratedDistance += 2;
  } else if (calibratedDistance < 22) {
    calibratedDistance += 3;
  } else if (calibratedDistance < 30) {
    calibratedDistance -= 3;
  } else if (calibratedDistance < 40) {
    calibratedDistance += 3;
  } else if (calibratedDistance < 45) {
    calibratedDistance += 0;
  } else if (calibratedDistance < 50) {
    calibratedDistance -= 3;
  } else if (calibratedDistance < 68) {
    calibratedDistance -= 3;
  } else if (calibratedDistance < 72) {
    calibratedDistance -= 3;
  } else if (calibratedDistance < 75) {
    calibratedDistance += 3;
  } else if (calibratedDistance < 80) {
    calibratedDistance += 3;
  }

  return calibratedDistance;
  // return calibratedDistance = raw_dist;
}

// -----------------------------------------------------------------
// ++ _updateLEDs() (อัปเดตลอจิก Active HIGH/LOW) ++
// -----------------------------------------------------------------
void PanTiltScanner::_updateLEDs()
{
  // --- LED Logic (Active HIGH) ---
  if (_RED_PIN != -1) {
    if (_errorState) {
      // สถานะ Error (สีแดง)
      digitalWrite(_RED_PIN, HIGH);
      digitalWrite(_YELLOW_PIN, LOW);
      digitalWrite(_GREEN_PIN, LOW);
    } else if (_state == IDLE || _state == FINISHED) {
      // สถานะ ว่างงาน (สีเขียว)
      digitalWrite(_RED_PIN, LOW);
      digitalWrite(_YELLOW_PIN, LOW);
      digitalWrite(_GREEN_PIN, HIGH);
    } else {
      // สถานะ ทำงาน (สีเหลือง)
      digitalWrite(_RED_PIN, LOW);
      digitalWrite(_YELLOW_PIN, HIGH);
      digitalWrite(_GREEN_PIN, LOW);
    }
  }

  // --- Enable Pin Logic (Active LOW) ---
  if (_ENABLE_PIN != -1) {
    if (_state == IDLE || _state == FINISHED || _errorState) {
      digitalWrite(_ENABLE_PIN, HIGH); // ปิดมอเตอร์ (ไม่กินไฟ)
    } else {
      digitalWrite(_ENABLE_PIN, LOW); // เปิดมอเตอร์ (ทำงาน)
    }
  }
}

// -----------------------------------------------------------------
// (ฟังก์ชันที่เหลือทั้งหมดเหมือนเดิมเป๊ะ)
// (StartFullScan, run, logCurrentPosition, _CalculateXYZ, 
//  setLEDError, ResetOrigin, set... , Get..., ...ToSteps, ...ToDeg)
// -----------------------------------------------------------------

void PanTiltScanner::StartFullScan()
{
  if (_lidarTaskHandle != NULL) {
    vTaskDelete(_lidarTaskHandle);
    _lidarTaskHandle = NULL;
  }
  std::queue<XYZPoint> empty;
  std::swap(_pointQueue, empty);
  xTaskCreatePinnedToCore(
    LidarReadTask, "LidarTask", 10000, this, 1, &_lidarTaskHandle, 1
  );
  _startStateMachine();
}

void PanTiltScanner::_startStateMachine()
{
  Serial.println("[Core 0] Moving to starting position...");
  _current_pitch_target_deg = _pitch_start_deg;
  _pitchStepper.moveTo(_PitchDegToSteps(_current_pitch_target_deg));
  _yawStepper.moveTo(_YawDegToSteps(_yaw_start_deg));
  _is_scanning_fwd = true; 
  _state = MOVING_TO_START;
  _updateLEDs(); 
}

void PanTiltScanner::run()
{
  if (_state == IDLE) {
    return; 
  }
  if (_state == FINISHED) {
    if (_lidarTaskHandle != NULL) {
      Serial.println("[Core 0] Scan finished. Stopping Lidar Task (Core 1)...");
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
  float current_yaw = GetCurrentYaw(); 
  switch (_state) {
    case MOVING_TO_START:
      if (!_yawStepper.isRunning() && !_pitchStepper.isRunning()) {
        // Serial.println("[Core 0] At start. Begin scanning FWD.");
        _is_scanning_fwd = true; 
        _yawStepper.setSpeed(_scan_speed_yaw);
        _state = SCANNING_FWD;
        _updateLEDs();
      }
      break;
    case SCANNING_FWD:
      if (current_yaw >= _yaw_end_deg) {
        // Serial.println("[Core 0] Hit FWD end. Changing row...");
        _yawStepper.stop(); 
        _state = CHANGING_ROW; 
        _current_pitch_target_deg += _pitch_step_deg; 
        _pitchStepper.moveTo(_PitchDegToSteps(_current_pitch_target_deg)); 
        _updateLEDs();
      }
      break;
    case SCANNING_REV:
      if (current_yaw <= _yaw_start_deg) {
        // Serial.println("[Core 0] Hit REV end. Changing row...");
        _yawStepper.stop(); 
        _state = CHANGING_ROW; 
        _current_pitch_target_deg += _pitch_step_deg; 
        _pitchStepper.moveTo(_PitchDegToSteps(_current_pitch_target_deg)); 
        _updateLEDs();
      }
      break;
    case CHANGING_ROW:
      if (!_pitchStepper.isRunning() && !_yawStepper.isRunning()) { 
        if (_current_pitch_target_deg > _pitch_end_deg) {
          Serial.println("[Core 0] Scan Complete. Returning to Home (0,0)...");
          _pitchStepper.moveTo(0); 
          _yawStepper.moveTo(0);   
          _state = RETURNING_HOME; 
          _updateLEDs();
        } else {
          if (_is_scanning_fwd) { 
            //  Serial.println("[Core 0] Row changed. Begin scanning REV.");
             _is_scanning_fwd = false;
             _yawStepper.setSpeed(-_scan_speed_yaw); 
             _state = SCANNING_REV;
             _updateLEDs();
          } else {
            //  Serial.println("[Core 0] Row changed. Begin scanning FWD.");
             _is_scanning_fwd = true;
             _yawStepper.setSpeed(_scan_speed_yaw); 
             _state = SCANNING_FWD;
             _updateLEDs();
          }
        }
      }
      break;
    case RETURNING_HOME:
      if (!_pitchStepper.isRunning() && !_yawStepper.isRunning()) {
        if (_BUZZER_PIN != -1) {
          digitalWrite(_BUZZER_PIN, LOW);  delay(50); 
          digitalWrite(_BUZZER_PIN, HIGH); delay(50); 
          digitalWrite(_BUZZER_PIN, LOW);  delay(50); 
          digitalWrite(_BUZZER_PIN, HIGH); delay(50); 
          digitalWrite(_BUZZER_PIN, LOW);  delay(50); 
          digitalWrite(_BUZZER_PIN, HIGH);
        }
        Serial.println("[Core 0] Arrived at Home. System idle.");
        _state = FINISHED; 
        _updateLEDs(); 
      }
      break;
    case FINISHED:
      break; 
  }
}

void PanTiltScanner::logCurrentPosition(float distance) 
{
  if (_state != SCANNING_FWD && _state != SCANNING_REV) {
    return;
  }
  float current_yaw = GetCurrentYaw();
  float current_pitch = GetCurrentPitch();
  if (_is_scanning_fwd && current_yaw >= _yaw_end_deg) { return; }
  if (!_is_scanning_fwd && current_yaw <= _yaw_start_deg) { return; }
  float calibrated_dist = _calibrateLidar(distance);
  XYZPoint newPoint = _CalculateXYZ(calibrated_dist, current_yaw, current_pitch);
  _pointQueue.push(newPoint);
}

bool PanTiltScanner::GetNextPoint(XYZPoint &point)
{
  if (_pointQueue.empty()) {
    return false; 
  }
  point = _pointQueue.front(); 
  _pointQueue.pop();           
  return true;                 
}

size_t PanTiltScanner::getQueueSize()
{
  return _pointQueue.size();
}

ScanState PanTiltScanner::getState()
{
  return _state;
}

void PanTiltScanner::setLEDError(bool error) {
  if (_errorState != error) {
    _errorState = error;
    _updateLEDs();
  }
}

void PanTiltScanner::ResetOrigin() {
  Serial.println("Resetting Origin...");
  delay(100); 
  _yawStepper.stop(); 
  _pitchStepper.stop();
  _yawStepper.setCurrentPosition(0); 
  _pitchStepper.setCurrentPosition(0);
  _state = IDLE; 
  _updateLEDs(); 
  Serial.println("Origin Reset. Ready.");
}

void PanTiltScanner::setInvertVertical(bool invert) {
  _invert_vertical = invert;
}

void PanTiltScanner::setZAxisUp(bool z_is_up) {
  _z_axis_is_up = z_is_up;
}

float PanTiltScanner::GetCurrentYaw() {
  return _YawStepsToDeg(_yawStepper.currentPosition());
}

float PanTiltScanner::GetCurrentPitch() {
  return _PitchStepsToDeg(_pitchStepper.currentPosition());
}

XYZPoint PanTiltScanner::_CalculateXYZ(float distance_cm, float yaw_deg, float pitch_deg) {
  float yaw_rad = yaw_deg * (M_PI / 180.0);
  float pitch_rad = pitch_deg * (M_PI / 180.0);
  float elevation = distance_cm * sin(pitch_rad);
  float planar_dist = distance_cm * cos(pitch_rad);
  if (_invert_vertical) {
    elevation = -elevation; 
  }
  XYZPoint point;
  if (_z_axis_is_up) {
    point.x = planar_dist * cos(yaw_rad);
    point.y = planar_dist * sin(yaw_rad);
    point.z = elevation;
  } else {
    point.x = planar_dist * sin(yaw_rad);
    point.y = elevation;
    point.z = -planar_dist * cos(yaw_rad);
  }
  return point;
}

long PanTiltScanner::_YawDegToSteps(float deg) {
  return round(deg * (_YAW_STEPS_PER_REV / 360.0));
}

long PanTiltScanner::_PitchDegToSteps(float deg) {
  return round(deg * (_PITCH_STEPS_PER_REV / 360.0));
}

float PanTiltScanner::_YawStepsToDeg(long steps) {
  return (float)steps * (360.0 / _YAW_STEPS_PER_REV);
}

float PanTiltScanner::_PitchStepsToDeg(long steps) {
  return (float)steps * (360.0 / _PITCH_STEPS_PER_REV);
}