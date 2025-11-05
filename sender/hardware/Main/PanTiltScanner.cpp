#include "PanTiltScanner.h"

// --- Constructor (ไม่เปลี่ยน) ---
PanTiltScanner::PanTiltScanner(int yaw_dir_pin, int yaw_step_pin, int pitch_dir_pin, int pitch_step_pin)
  : _yawStepper(AccelStepper::DRIVER, yaw_step_pin, yaw_dir_pin),
    _pitchStepper(AccelStepper::DRIVER, pitch_step_pin, pitch_dir_pin)
{
}

// --- Setup (ไม่เปลี่ยน) ---
void PanTiltScanner::begin(long max_speed, long max_accel, int buzzer_pin)
{
  _yawStepper.setMaxSpeed(max_speed);
  _yawStepper.setAcceleration(max_accel);
  _yawStepper.setCurrentPosition(0); 
  _pitchStepper.setMaxSpeed(max_speed);
  _pitchStepper.setAcceleration(max_accel);
  _pitchStepper.setCurrentPosition(0);
  _BUZZER_PIN = buzzer_pin;
  if (_BUZZER_PIN != -1) {
    // ติ๊ด ติ๊ด (Beep 2 ครั้ง ตอนเริ่ม)
    digitalWrite(_BUZZER_PIN, 0); delay(50);
    digitalWrite(_BUZZER_PIN, 1);  delay(50);
    digitalWrite(_BUZZER_PIN, 0); delay(50);
    digitalWrite(_BUZZER_PIN, 1);
  }
  Serial.println("[Core 0] Motor Controller Initialized (Scan-While-Moving).");
}

// --- ฟังก์ชัน State Machine (แก้ไข startScanning) ---
void PanTiltScanner::setScanParameters(float y_start, float y_end, float p_start, float p_end, float p_step, long scan_speed)
{
  _yaw_start_deg = y_start;
  _yaw_end_deg = y_end;
  _pitch_start_deg = p_start;
  _pitch_end_deg = p_end;
  _pitch_step_deg = p_step;
  _scan_speed_yaw = scan_speed;
}

void PanTiltScanner::startScanning()
{
  Serial.println("[Core 0] Moving to starting position...");
  _current_pitch_target_deg = _pitch_start_deg;
  _pitchStepper.moveTo(_PitchDegToSteps(_current_pitch_target_deg));
  _yawStepper.moveTo(_YawDegToSteps(_yaw_start_deg));
  
  // ++ FIX: รีเซ็ตทิศทางตอนเริ่ม ++
  _is_scanning_fwd = true; 
  
  _state = MOVING_TO_START;
}

// -----------------------------------------------------------------
// ++ "หัวใจ" ของ Core 0 (แก้ไขตรรกะใหม่) ++
// -----------------------------------------------------------------
void PanTiltScanner::run()
{
  // ++ FIX: ถ้า FINISHED แล้ว ก็ยังต้อง .run() เผื่อกำลังกลับบ้าน ++
  if (_state == IDLE) {
    return;
  }

  // --- 1. ขับมอเตอร์ (อันดับแรก) ---
  if (_state == SCANNING_FWD || _state == SCANNING_REV) {
    // ถ้ากำลังสแกน:
    // - Pitch ต้องหยุดนิ่ง (เรียก .run())
    // - Yaw ต้องหมุนด้วยความเร็วคงที่ (เรียก .runSpeed())
    _pitchStepper.run(); 
    _yawStepper.runSpeed(); 
  } else {
    // ถ้ากำลัง "ย้ายที่" หรือ "กลับบ้าน":
    // (MOVING_TO_START, CHANGING_ROW, RETURNING_HOME, FINISHED)
    // - ทั้งคู่ต้องเคลื่อนที่ไปที่เป้าหมาย (เรียก .run())
    _pitchStepper.run();
    _yawStepper.run(); 
  }

  // --- 2. ตรรกะเปลี่ยนสถานะ (อันดับสอง) ---
  float current_yaw = GetCurrentYaw(); 

  switch (_state) {
    case MOVING_TO_START:
      if (!_yawStepper.isRunning() && !_pitchStepper.isRunning()) {
        Serial.println("[Core 0] At start. Begin scanning FWD.");
        _is_scanning_fwd = true;
        _yawStepper.setSpeed(_scan_speed_yaw);
        _state = SCANNING_FWD;
      }
      break;

    case SCANNING_FWD:
      if (current_yaw >= _yaw_end_deg) {
        Serial.println("[Core 0] Hit FWD end. Changing row...");
        _yawStepper.stop(); 
        _state = CHANGING_ROW; 
        _current_pitch_target_deg += _pitch_step_deg; 
        _pitchStepper.moveTo(_PitchDegToSteps(_current_pitch_target_deg)); 
      }
      break;

    case SCANNING_REV:
      if (current_yaw <= _yaw_start_deg) {
        Serial.println("[Core 0] Hit REV end. Changing row...");
        _yawStepper.stop(); 
        _state = CHANGING_ROW; 
        _current_pitch_target_deg += _pitch_step_deg; 
        _pitchStepper.moveTo(_PitchDegToSteps(_current_pitch_target_deg)); 
      }
      break;
      
    case CHANGING_ROW:
      // รอให้มอเตอร์ "ทั้งคู่" หยุดสนิท
      if (!_pitchStepper.isRunning() && !_yawStepper.isRunning()) { 
        
        // เช็กว่าแถวสุดท้ายหรือยัง
        if (_current_pitch_target_deg > _pitch_end_deg) {
          // ++ นี่คือส่วนที่แก้ไข ++
          Serial.println("[Core 0] Scan Complete. Returning to Home (0,0)...");
          _pitchStepper.moveTo(0); // สั่ง Pitch กลับ 0
          _yawStepper.moveTo(0);   // สั่ง Yaw กลับ 0
          _state = RETURNING_HOME; // <-- เปลี่ยนสถานะเป็น "กำลังกลับบ้าน"
          // ----------------------
        } else {
          // (ถ้ายังไม่จบ: เริ่มสแกนแถวต่อไป เหมือนเดิม)
          if (_is_scanning_fwd) { 
             Serial.println("[Core 0] Row changed. Begin scanning REV.");
             _is_scanning_fwd = false;
             _yawStepper.setSpeed(-_scan_speed_yaw); 
             _state = SCANNING_REV;
          } else {
             Serial.println("[Core 0] Row changed. Begin scanning FWD.");
             _is_scanning_fwd = true;
             _yawStepper.setSpeed(_scan_speed_yaw); 
             _state = SCANNING_FWD;
          }
        }
      }
      break;
      
    // ++ เพิ่ม Case นี้เข้าไป ++
    case RETURNING_HOME:
      // เรารอให้มอเตอร์ทั้งคู่ (ที่กำลัง .run() กลับ 0) หยุดสนิท
      if (!_pitchStepper.isRunning() && !_yawStepper.isRunning()) {
        if (_BUZZER_PIN != -1) {
          // ติ๊ด ติ๊ด ติ๊ด (Beep 3 ครั้ง)
          digitalWrite(_BUZZER_PIN, 0); delay(50);
          digitalWrite(_BUZZER_PIN, 1);  delay(50);
          digitalWrite(_BUZZER_PIN, 0); delay(50);
          digitalWrite(_BUZZER_PIN, 1);  delay(50);
          digitalWrite(_BUZZER_PIN, 0); delay(50);
          digitalWrite(_BUZZER_PIN, 1);
        }
        Serial.println("[Core 0] Arrived at Home. System idle.");
        _state = FINISHED; // จบการทำงานจริงๆ
      }
      break;
      
    case FINISHED:
      // ไม่ทำอะไร (มอเตอร์ .run() จนจบไปแล้ว)
      break;
  }
}

// -----------------------------------------------------------------
// ++ ฟังก์ชันรับข้อมูลจาก Core 1 (แก้ไข: ลบ logic ทิ้ง) ++
// -----------------------------------------------------------------
void PanTiltScanner::logCurrentPosition(float distance)
{
  // ฟังก์ชันนี้มีหน้าที่ "บันทึก" อย่างเดียว
  // มันจะไม่ "ตัดสินใจ" เปลี่ยนสถานะอีกต่อไป
  
  // ถ้าเรา "ไม่ได้" อยู่ในโหมดสแกนจริง ก็ไม่ต้องบันทึก
  // (รวมถึงตอนที่ Yaw กำลังเบรก หรือ Pitch กำลังขยับ)
  if (_state != SCANNING_FWD && _state != SCANNING_REV) {
    return;
  }
  
  // 1. "ประทับตรา" องศาปัจจุบัน (ณ เสี้ยววินาทีนี้)
  float current_yaw = GetCurrentYaw();
  float current_pitch = GetCurrentPitch();

  // (ป้องกันการบันทึกข้อมูลขยะตอนที่ Yaw กำลังเบรก)
  if (_is_scanning_fwd && current_yaw >= _yaw_end_deg) {
    return;
  }
  if (!_is_scanning_fwd && current_yaw <= _yaw_start_deg) {
    return;
  }

  // 2. คำนวณและพิมพ์ XYZ
  _CalculateAndPrintXYZ(distance, current_yaw, current_pitch);
  
  // (ลบตรรกะ if (current_yaw >= ...) ทิ้งทั้งหมด)
}

// -----------------------------------------------------------------
// ฟังก์ชันที่เหลือ (เติมโค้ดให้สมบูรณ์)
// -----------------------------------------------------------------

void PanTiltScanner::ResetOrigin() {
  Serial.println("Resetting Origin...");
  delay(100); 
  _yawStepper.stop(); 
  _pitchStepper.stop();
  _yawStepper.setCurrentPosition(0); 
  _pitchStepper.setCurrentPosition(0);
  _state = IDLE; 
  Serial.println("Origin Reset. Ready.");
}

float PanTiltScanner::GetCurrentYaw() {
  return _YawStepsToDeg(_yawStepper.currentPosition());
}

float PanTiltScanner::GetCurrentPitch() {
  return _PitchStepsToDeg(_pitchStepper.currentPosition());
}

void PanTiltScanner::_CalculateAndPrintXYZ(float distance_cm, float yaw_deg, float pitch_deg) 
{
  float yaw_rad = yaw_deg * (M_PI / 180.0);
  float pitch_rad = pitch_deg * (M_PI / 180.0);

  // --- 1. คำนวณส่วนประกอบพื้นฐาน ---
  // "elevation" คือส่วนประกอบ "แนวตั้ง" (ขึ้น/ลง)
  float elevation = distance_cm * sin(pitch_rad);
  // "planar_dist" คือ "เงา" บนระนาบแนวนอน
  float planar_dist = distance_cm * cos(pitch_rad);

  // --- 2. ใช้ setting กลับด้าน Y/Z (ตามที่คุณต้องการ) ---
  if (_invert_vertical_axis) {
    elevation = -elevation; // กลับค่าแนวตั้ง
  }

  // --- 3. เตรียมตัวแปร X, Y, Z ที่จะพิมพ์ ---
  float out_x, out_y, out_z;

  // --- 4. ใช้ setting ว่าแกนไหนชี้ขึ้น ---
  if (_z_axis_is_up) {
    // โหมด Z-Up (สำหรับหุ่นยนต์/วิศวกรรม)
    // X = Forward (ไปข้างหน้า)
    // Y = Left (ไปทางซ้าย)
    // Z = Up (ชี้ขึ้น)
    out_x = planar_dist * cos(yaw_rad);
    out_y = planar_dist * sin(yaw_rad);
    out_z = elevation;
    
  } else {
    // โหมด Y-Up (สำหรับ 3D Viewer)
    // X = Right (ไปทางขวา)
    // Y = Up (ชี้ขึ้น)
    // Z = Forward (ชี้ไปข้างหน้า/เข้าจอ)
    out_x = planar_dist * sin(yaw_rad);
    out_y = elevation;
    out_z = -planar_dist * cos(yaw_rad);
  }
  
  // --- 5. พิมพ์ผลลัพธ์ ---
  Serial.print(out_x); Serial.print(" ");
  Serial.print(out_y); Serial.print(" ");
  Serial.println(out_z);
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


void PanTiltScanner::setInvertVertical(bool invert)
{
  _invert_vertical_axis = invert;
}

void PanTiltScanner::setZAxisUp(bool z_is_up)
{
  _z_axis_is_up = z_is_up;
}