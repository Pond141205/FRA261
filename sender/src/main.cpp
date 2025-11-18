#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <SD.h>
#include <FS.h>
#include <SPI.h>

// --- Configuration ---
const char* ssid = "Theeranon_2G";
const char* password = "14122005$";
const char* serverUrl = "https://unconserving-madelyn-glottogonic.ngrok-free.dev/upload_chunk"; 

#define DEVICE_ID "S001_01"
const int SD_CS_PIN = 5;
const size_t CHUNK_SIZE = 32768; // 32 KB per chunk.
const int maxRetries = 3;

const char* logFile = "/activity_log.txt";

  // Time Configuration
const int delayBetweenRetries = 2000;
const long gmtOffset_sec = 7 * 3600; // Thailand time zone gmt +7
const int daylightOffset_sec = 0;
const char* ntpServer = "pool.ntp.org";

int last_scan_hour = -1; // Track last hour runing scan

// --- Define Function  ---
void connectWiFi();
void timeInit();
void lidarScan();
void logToSD(String message);
bool initSDCard();
bool uploadFileInBatches(const char* filename, const char* batch_id);
bool sendChunk(int chunk_id, int total_chunks, uint8_t* dataBuffer, size_t bytesToSend, const char* batch_id);


// ---
// SETUP FUNCTION
// ---
void connectWiFi() {
  Serial.printf("Connecting to WiFi: %s\n", ssid);
  logInfo("Connecting to WiFi: " + String(ssid));

  WiFi.begin(ssid, password);
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    retry++;
    if (retry > 60) {
      Serial.println("\nWiFi connect timeout, retrying...");
      logError("WiFi connect timeout, retrying.");
      WiFi.begin(ssid, password);
      retry = 0;
    }
  }
  Serial.println("\nWiFi connected!");
  Serial.print("IP address: "); Serial.println(WiFi.localIP());
  logSuccess("WiFi connected!");
  logInfo("IP address: " + WiFi.localIP().toString());
}

bool initSDCard() {
  if (!SD.begin(SD_CS_PIN)) {
    Serial.println("[ERROR] SD Card mount failed! Check wiring.");
    return false;
  }
  uint8_t cardType = SD.cardType();
  if (cardType == CARD_NONE) {
    Serial.println("[ERROR] No SD card attached");
    return false;
  }
  Serial.println("[INFO] SD Card initialized.");
  return true;
}

void timeInit() {
  Serial.println("Syncing time with NTP...");
  logInfo("Syncing time with NTP.");
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);

  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    Serial.println("Failed to obtain time. Rebooting...");
    logError("Failed to obtain time. Rebooting.");
    delay(1000);
    ESP.restart();
  }
  Serial.println("Time synced");
  Serial.println(&timeinfo, "%A, %B %d %Y %H:%M:%S");

  logInfo("Time synced.");
  String timeStr = asctime(&timeinfo);
  timeStr.trim(); 
  logInfo("Current time: " + timeStr);
}


// ---
// MAIN FUNCTION
// ---
bool uploadFileInBatches(const char* filename, const char* batch_id) {
  if (WiFi.status() != WL_CONNECTED) {
    logError("WiFi connection lost. Reconnecting.");
    connectWiFi();
  }

  File file = SD.open(filename, FILE_READ);
  if (!file) {
    Serial.printf("Failed to open file: %s. Skipping batch.\n", filename);
    return false;
  }

  size_t fileSize = file.size();
  if (fileSize == 0) {
    Serial.printf("File '%s' is empty. Skipping batch.\n", filename);
    file.close();
    return false;
  }
  
  int total_chunks = (fileSize + CHUNK_SIZE - 1) / CHUNK_SIZE;
  
  char logBuffer[128];

  sprintf(logBuffer, "Starting new batch for %s (Batch: %s)", filename, batch_id);
  logInfo(logBuffer);
  sprintf(logBuffer, "File Size: %u bytes, Chunks: %d", fileSize, total_chunks);
  logInfo(logBuffer);

  uint8_t *dataBuffer = (uint8_t*) malloc(CHUNK_SIZE);
    if (dataBuffer == NULL) {
        Serial.println("Failed to allocate memory for chunk buffer! Halting.");
        logError("Failed to allocate memory for chunk buffer! Halting.");
        return false; // Or maybe just skip batch
  }

  bool allChunksSent = true;
  for (int chunk_id = 1; chunk_id <= total_chunks; chunk_id++) {
      
    // Calculate the exact size for this chunk
    size_t startPos = (chunk_id - 1) * CHUNK_SIZE;
    size_t bytesToSend = (startPos + CHUNK_SIZE > fileSize) ? (fileSize - startPos) : CHUNK_SIZE;

    // Read data into the buffer
    file.seek(startPos);
    file.read(dataBuffer, bytesToSend);

    // Pass the buffer and its size to the send function
    bool sent = sendChunk(chunk_id, total_chunks, dataBuffer, bytesToSend, batch_id);
    
    if (!sent) {
        sprintf(logBuffer, "[Chunk %d] Failed after %d retries. Aborting batch.", chunk_id, maxRetries);
        logError(logBuffer);
        allChunksSent = false;
        break;
    }
    sprintf(logBuffer, "[Chunk %d/%d] Sent successfully.", chunk_id, total_chunks);
    logInfo(logBuffer);
  }
  
  free(dataBuffer);
  file.close();
  return allChunksSent;
}

bool sendChunk(int chunk_id, int total_chunks, uint8_t* dataBuffer, size_t bytesToSend, const char* batch_id) {
  int attempt = 0;
  char logBuffer[256];

  while (attempt < maxRetries) {
    if (WiFi.status() != WL_CONNECTED) {
      logError("WiFi connection lost. Reconnecting.");
      connectWiFi();
    }

    WiFiClientSecure secureClient;
    secureClient.setInsecure(); // for testing only

    HTTPClient http;
    http.begin(secureClient, serverUrl);
    http.setTimeout(20000); // 20-second timeout

    // Set Content-Type to plain text.
    http.addHeader("Content-Type", "text/plain"); 
    
    // Send headers your server needs to identify the chunk
    http.addHeader("X-Device-ID", DEVICE_ID);
    http.addHeader("X-Batch-ID", batch_id);
    http.addHeader("X-Chunk-ID", String(chunk_id));
    http.addHeader("X-Total-Chunks", String(total_chunks));

    // Send the POST request with the raw buffer
    int httpCode = http.POST(dataBuffer, bytesToSend);
    
    if (httpCode > 0) {
      String response = http.getString();
      http.end(); 
      
      if (httpCode == 200) { // 200 OK
        return true; // Success
      } else {
        sprintf(logBuffer, "[Chunk %d] Server error (HTTP %d): %s", chunk_id, httpCode, response.c_str());
        logError(logBuffer);
      }
    } else {
        http.end();
        sprintf(logBuffer, "[Chunk %d] HTTP failed: %s", chunk_id, http.errorToString(httpCode).c_str());
        logError(logBuffer);
    }

    attempt++;
    delay(delayBetweenRetries);
  }
  
  return false; 
}

void writeToLog(const char* level, String message) {
    // 1. Get timestamp
    struct tm timeinfo;
    char timestamp[30];
    if (getLocalTime(&timeinfo)) {
        sprintf(timestamp, "[%d-%02d-%02d %02d:%02d:%02d]",
                (timeinfo.tm_year + 1900),
                (timeinfo.tm_mon + 1),
                timeinfo.tm_mday,
                timeinfo.tm_hour,
                timeinfo.tm_min,
                timeinfo.tm_sec);
    } else {
        sprintf(timestamp, "[NO_TIME]");
    }

    // 2. Format the new log entry: [Timestamp] [LEVEL] Message
    String logEntry = String(timestamp) + " " + level + " " + message;

    // 3. Print to Serial
    Serial.println(logEntry);

    // 4. Append to the SD card
    File file = SD.open(logFile, FILE_APPEND);
    if (!file) {
        Serial.println("Failed to open log file for appending");
        return;
    }
    
    if (!file.println(logEntry)) {
        Serial.println("Failed to write to log file");
    }
    
    // Close immediately to save the data
    file.close(); 
}

void logInfo(String message) {
    writeToLog("[INFO]", message);
}

void logError(String message) {
    writeToLog("[ERROR]", message);
}

void logSuccess(String message) {
    writeToLog("[SUCCESS]", message);
}

void loop_test() { // testing loop

  char logBuffer[128];
  struct tm timeinfo;

  if (!getLocalTime(&timeinfo)) {
    logError("Failed to get local time.");
    delay(1000); 
    return;
  }

  
  char batch_id[32];
  sprintf(batch_id, "%s_%d%02d%02d_%02d", 
          DEVICE_ID,
          (timeinfo.tm_year + 1900), 
          (timeinfo.tm_mon + 1), 
          timeinfo.tm_mday, 
          timeinfo.tm_hour);
  sprintf(logBuffer, "Generated Batch ID: %s", batch_id);
  logInfo(logBuffer);
  // ---

    // Run the scan
    // void lidar fn scan
    
  // Upload the file
  logInfo("Scan complete. Starting file upload...");
  bool batchSuccess = uploadFileInBatches("/scan_data.xyz", batch_id);
  
  if (batchSuccess) {
    logSuccess("Batch completed successfully.");
  } else {
    logError("Batch failed.");
  }

  logInfo("Waiting 30 seconds for next test run...");
  delay(30 * 1000);
}

// --- Main Setup & Loop ---
void setup() {
  Serial.begin(115200);
  
  if (!initSDCard()) {
    Serial.println("SD Card failed. Halting.");
    while(1); // Stop
  }

  logInfo("--- SYSTEM STARTUP ---");
  logSuccess("SD Card initialized successfully.");
  
  connectWiFi();
  timeInit();

  logInfo("Setup complete. Starting main loop.");
}

void loop() {

  loop_test();
  // struct tm timeinfo;
  // if (!getLocalTime(&timeinfo)) {
  //   Serial.println("Failed to get local time.");
  //   logToSD("ERROR: Failed to get local time.");
  //   delay(1000); 
  //   return;
  // }

  // int current_hour = timeinfo.tm_hour;
  // int current_minute = timeinfo.tm_min;

  // bool inScanWindow = (current_hour >= 7 && current_hour <= 16); // scan window (7:00 AM to 4:XX PM)
  // bool atTopOfTheHour = (current_minute == 0);


  
  // if (inScanWindow && atTopOfTheHour && (current_hour != last_scan_hour)) {
    
  //   char logBuffer[128];
  //   sprintf(logBuffer, "Time is %02d:%02d. Starting scheduled scan.", current_hour, current_minute);
  //   logToSD(logBuffer);

  //   // Generate a reliable Batch ID *before* scanning.
    // char batch_id[32];
    // sprintf(batch_id, "%d%02d%02d-%02d0000", 
    //         DEVICE_ID,
    //         (timeinfo.tm_year + 1900), 
    //         (timeinfo.tm_mon + 1), 
    //         timeinfo.tm_mday, 
    //         current_hour);
    // sprintf(logBuffer, "Generated Batch ID: %s", batch_id);
    // logToSD(logBuffer);

  //   // ---
  //   // STEP 1: RUN THE SCAN AND CREATE THE FILE
  //   // ---
    
    
  //   // ---
  //   // STEP 2: UPLOAD THE FILE
  //   // ---
  //   logToSD("Scan complete. Starting file upload...");
  //   bool batchSuccess = uploadFileInBatches("/scan_data.xyz", batch_id);
    
  //   if (batchSuccess) {
  //     Serial.println("Batch completed successfully.");
  //     logToSD("Batch completed successfully.");
  //   } else {
  //     Serial.println("Batch failed.");
  //     logToSD("ERROR: Batch failed.");
  //   }

  //   // CRITICAL: Mark this hour as "done" so we don't run again
  //   last_scan_hour = current_hour;

  // } else if (!inScanWindow && last_scan_hour != -1) {
  //   // Reset the "last scan" tracker when we are outside the window
  //   last_scan_hour = -1;
  // }

  // // Wait 5 seconds before checking the clock again.
  // delay(5000);
}

























