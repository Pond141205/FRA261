#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <SD.h>
#include <FS.h>
#include <SPI.h>
#include <Wire.h>
#include <AS5600.h>
#include "PanTiltScanner.h" 

// --- CONFIGURATION ---
const char* ssid = "FIBO_Academy";
const char* password = "fiboacademy2568";
const char* serverUrl = "https://unconserving-madelyn-glottogonic.ngrok-free.dev/upload_chunk";
#define DEVICE_ID "S001_01"

// --- PINS ---
const int STATUS_LED_PIN = 4; 
const int ENABLE_PIN = 27;

const int SD_SCK = 18; 
const int SD_MISO = 19; 
const int SD_MOSI = 23;
const int SD_CS = 5;

// --- ENCODER OBJECTS ---
TwoWire I2Ctwo = TwoWire(1); 
AS5600 encoderYaw(&Wire);     // Yaw on default pins 21, 22
AS5600 encoderPitch(&I2Ctwo); // Pitch on pins 13, 14

// --- SCANNER OBJECT ---
PanTiltScanner scanner(26, 32, 33, 25); 

File xyzFile;            
bool isRecording = false; 
String currentScanFilename = ""; 
String currentBatchID = "";      

// --- NETWORK & TIME ---
const long gmtOffset_sec = 7 * 3600; 
const int daylightOffset_sec = 0;
const char* ntpServer = "pool.ntp.org";
int last_scan_hour = -1;
const size_t CHUNK_SIZE = 32768; 
const char* logFile = "/activity_log.txt";

long MAX_SPEED = 8000;
long MAX_ACCEL = 4000;
long SCAN_SPEED_YAW = 3000; 

// --- PROTOTYPES ---
void connectWiFi();
void timeInit();
bool initSDCard();
void logInfo(String message);
void logError(String message);
void logSuccess(String message);
void handleSchedule();
void handleSerialCommands(); 
void StartImmediateScan();   
bool uploadFileInBatches(const char* filename, const char* batch_id);
bool sendChunk(int chunk_id, int total_chunks, uint8_t* dataBuffer, size_t bytesToSend, const char* batch_id);
void writeToLog(const char* level, String message);

// -----------------------------------------------------------------
// SETUP
// -----------------------------------------------------------------
void setup() {
  Serial.begin(115200); 
  
  if (!initSDCard()) {
    Serial.println("SD Card Failure.");
    while(1);
  }
  logInfo("--- SYSTEM STARTUP ---");

  pinMode(STATUS_LED_PIN, OUTPUT);
  pinMode(ENABLE_PIN, OUTPUT);
  
  // 1. Initialize Encoders
  // Yaw (Default I2C)
  Wire.begin(21, 22);           
  if (!encoderYaw.begin()) Serial.println("Yaw Encoder Missing");

  // Pitch (Secondary I2C)
  I2Ctwo.begin(13, 14, 400000); 
  if (!encoderPitch.begin()) Serial.println("Pitch Encoder Missing");

  // 2. Network & Time
  digitalWrite(ENABLE_PIN, HIGH); // Disable motors
  digitalWrite(STATUS_LED_PIN, HIGH);
  connectWiFi();
  timeInit();

  // 3. Initialize Scanner with Encoders
  // NOTE: Pass pointers (&) to the encoder objects
  scanner.begin(MAX_SPEED, MAX_ACCEL, STATUS_LED_PIN, ENABLE_PIN, &encoderYaw, &encoderPitch);

  scanner.setScanParameters(
    -180, 180.0, 
    -90.0, 0.0, 1.0,
    SCAN_SPEED_YAW 
   );
  scanner.setInvertVertical(false); 
  scanner.setZAxisUp(true); 

  // 4. *** PHYSICAL HOMING ***
  // This moves the motors until the magnets read 0.0 degrees
  logInfo("Aligning to Hardware Home...");
  scanner.DriveToAbsoluteZero();
  logInfo("Ready.");
}

// -----------------------------------------------------------------
// MAIN LOOP
// -----------------------------------------------------------------
unsigned long lastTimeCheck = 0;

void loop() {
  // 1. Run Steppers
  scanner.run();

  // 2. Process Lidar Data
  if (isRecording && scanner.hasNewLidarData()) {
    float distance = scanner.getAndConsumeLidarData();
    scanner.logCurrentPosition(distance);
  }

  // 3. Save Data
  XYZPoint newPoint;
  while (scanner.GetNextPoint(newPoint)) {
    if (xyzFile) {
      xyzFile.printf("%.2f %.2f %.2f\n", newPoint.x, newPoint.y, newPoint.z);
    }
  }

  // 4. Check Finish
  if (isRecording && scanner.getState() == FINISHED) {
      logSuccess("Scan Finished. Closing file: " + currentScanFilename);
      xyzFile.close();
      isRecording = false;
      
      logInfo("Starting Upload: " + currentBatchID);
      bool result = uploadFileInBatches(currentScanFilename.c_str(), currentBatchID.c_str());
      
      if (result) logSuccess("Upload Complete.");
      else logError("Upload Failed.");
      
      logInfo("Returning to Zero.");
      scanner.DriveToAbsoluteZero(); // Re-home after scan
  }

  // 5. Schedule & Commands
  if (!isRecording && (millis() - lastTimeCheck > 5000)) {
    handleSchedule();
    lastTimeCheck = millis();
  }
  handleSerialCommands();
}

// -----------------------------------------------------------------
// HELPERS
// -----------------------------------------------------------------
void writeToLog(const char* level, String message) {
    struct tm timeinfo;
    char timestamp[30];
    if (getLocalTime(&timeinfo)) {
        sprintf(timestamp, "[%d-%02d-%02d %02d:%02d:%02d]",
                (timeinfo.tm_year + 1900), (timeinfo.tm_mon + 1), timeinfo.tm_mday,
                timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
    } else {
        sprintf(timestamp, "[NO_TIME]");
    }
    String logEntry = String(timestamp) + " " + level + " " + message;
    Serial.println(logEntry);
    File file = SD.open(logFile, FILE_APPEND);
    if (file) { file.println(logEntry); file.close(); }
}

void logInfo(String message) { writeToLog("[INFO]", message); }
void logError(String message) { writeToLog("[ERROR]", message); }
void logSuccess(String message) { writeToLog("[SUCCESS]", message); }

bool initSDCard() {
  SPIClass * vspi = new SPIClass(VSPI);
  vspi->begin(SD_SCK, SD_MISO, SD_MOSI, SD_CS);
  if (!SD.begin(SD_CS, *vspi)) return false;
  return (SD.cardType() != CARD_NONE);
}

void connectWiFi() {
  if(WiFi.status() == WL_CONNECTED) return;
  Serial.printf("Connecting to %s ", ssid);
  WiFi.begin(ssid, password);
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 20) {
    delay(500); Serial.print("."); retry++;
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? "\nWiFi Connected." : "\nWiFi Fail.");
}

void timeInit() {
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  struct tm timeinfo;
  for(int i=0; i<10; i++){ if(getLocalTime(&timeinfo)) break; delay(1000); Serial.print("."); }
  Serial.println("\nTime Synced.");
}

void handleSerialCommands() {
  if (Serial.available() > 0) {
    char command = Serial.read(); 
    if (command == '2') {
      if (!isRecording && (scanner.getState() == IDLE || scanner.getState() == FINISHED)) {
        logInfo("Command '2': Immediate Scan");
        StartImmediateScan(); 
      } else {
        Serial.println("Busy!"); 
      }
    }
  }
}

void StartImmediateScan() {
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) return;
    char batch_buff[32];
    sprintf(batch_buff, "%s-%d%02d%02d_%02d_CMD", DEVICE_ID, (timeinfo.tm_year + 1900), (timeinfo.tm_mon + 1), timeinfo.tm_mday, timeinfo.tm_hour);
    currentBatchID = String(batch_buff);
    currentScanFilename = "/" + currentBatchID + ".xyz";
    logInfo("Batch: " + currentBatchID);
    SD.remove(currentScanFilename);
    xyzFile = SD.open(currentScanFilename, FILE_WRITE);
    isRecording = true;
    scanner.DriveToAbsoluteZero();
    scanner.StartFullScan();
}

void handleSchedule() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) return;
  int current_hour = timeinfo.tm_hour;
  int current_minute = timeinfo.tm_min;
  bool inScanWindow = (current_hour >= 7 && current_hour <= 16);
  bool atTopOfTheHour = (current_minute == 0);
 
  if (inScanWindow && atTopOfTheHour && (current_hour != last_scan_hour)) {
    logInfo("Scheduled Scan: " + String(current_hour) + ":00");
    char batch_buff[64];
    sprintf(batch_buff, "%s-%d%02d%02d_%02d", DEVICE_ID, (timeinfo.tm_year + 1900), (timeinfo.tm_mon + 1), timeinfo.tm_mday, timeinfo.tm_hour);
    currentBatchID = String(batch_buff);
    currentScanFilename = "/" + currentBatchID + ".xyz";
    SD.remove(currentScanFilename);
    xyzFile = SD.open(currentScanFilename, FILE_WRITE);
    if (!xyzFile) { logError("SD Error"); return; }
    isRecording = true;
    scanner.DriveToAbsoluteZero();
    scanner.StartFullScan();
    last_scan_hour = current_hour;
  }
  else if (!inScanWindow && last_scan_hour != -1) { last_scan_hour = -1; }
}

bool uploadFileInBatches(const char* filename, const char* batch_id) {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  File file = SD.open(filename, FILE_READ);
  if (!file) return false;
  size_t fileSize = file.size();
  if (fileSize == 0) { file.close(); return false; }
  int total_chunks = (fileSize + CHUNK_SIZE - 1) / CHUNK_SIZE;
  uint8_t *dataBuffer = (uint8_t*) malloc(CHUNK_SIZE);
  if (dataBuffer == NULL) { file.close(); return false; }
  bool allChunksSent = true;
  
  for (int chunk_id = 1; chunk_id <= total_chunks; chunk_id++) {
    size_t startPos = (chunk_id - 1) * CHUNK_SIZE;
    size_t bytesToSend = (startPos + CHUNK_SIZE > fileSize) ? (fileSize - startPos) : CHUNK_SIZE;
    file.seek(startPos);
    file.read(dataBuffer, bytesToSend);
    if (!sendChunk(chunk_id, total_chunks, dataBuffer, bytesToSend, batch_id)) { allChunksSent = false; break; }
    delay(1); 
  }
  free(dataBuffer);
  file.close();
  return allChunksSent;
}

bool sendChunk(int chunk_id, int total_chunks, uint8_t* dataBuffer, size_t bytesToSend, const char* batch_id) {
  int attempt = 0;
  while (attempt < 3) {
    if (WiFi.status() != WL_CONNECTED) connectWiFi();
    WiFiClientSecure secureClient;
    secureClient.setInsecure(); 
    HTTPClient http;
    http.begin(secureClient, serverUrl);
    http.setTimeout(20000);
    http.addHeader("Content-Type", "text/plain"); 
    http.addHeader("X-Device-ID", DEVICE_ID);
    http.addHeader("X-Batch-ID", batch_id);
    http.addHeader("X-Chunk-ID", String(chunk_id));
    http.addHeader("X-Total-Chunks", String(total_chunks));
    int httpCode = http.POST(dataBuffer, bytesToSend);
    http.end();
    if (httpCode == 200) return true;
    attempt++;
    delay(2000);
  }
  return false; 
}
