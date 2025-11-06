#include <WiFi.h>
#include <HTTPClient.h>
#include <SD.h>
#include <FS.h>
#include <SPI.h>

// --- Configuration ---
const char* ssid = "Theeranon_2G";
const char* password = "14122005$";
const char* serverUrl = "https://unconserving-madelyn-glottogonic.ngrok-free.dev/upload_chunk"; // Your server

#define DEVICE_ID "S001_01"
const int SD_CS_PIN = 5;
const size_t CHUNK_SIZE = 32768; // 32 KB per chunk.
const int maxRetries = 3;
const int delayBetweenRetries = 2000;
const unsigned long batchInterval = 60 * 60 * 1000UL; // 1 hour

// --- Define Function  ---
void connectWiFi();
bool initSDCard();
bool uploadFileInBatches(const char* filename);
bool sendChunk(int chunk_id, int total_chunks, const char* filename, File &file);

// --- Main Setup & Loop ---
void setup() {
  Serial.begin(115200);
  connectWiFi();
  
  if (!initSDCard()) {
    Serial.println("SD Card failed. Halting.");
    while(1); // Stop
  }
}

void loop() {
  // Main task: read the file and send its data
  bool batchSuccess = uploadFileInBatches("/scan_data.xyz");
  
  if (batchSuccess) {
    Serial.println("Batch completed successfully.");
  } else {
    Serial.println("Batch failed.");
  }
  
  Serial.println("Waiting for next batch interval...");
  delay(batchInterval);
}

// ---
// 1. MAIN TASK FUNCTION
// ---
bool uploadFileInBatches(const char* filename) {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

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
  
  Serial.printf("Starting new batch for %s\n", filename);
  Serial.printf("File Size: %u bytes, Chunks: %d\n", fileSize, total_chunks);

  bool allChunksSent = true;
  for (int chunk_id = 1; chunk_id <= total_chunks; chunk_id++) {
    bool sent = sendChunk(chunk_id, total_chunks, filename, file);
    if (!sent) {
      Serial.printf("[Chunk %d] Failed after %d retries. Aborting batch.\n", chunk_id, maxRetries);
      allChunksSent = false;
      break;
    }
    Serial.printf("[Chunk %d/%d] Sent successfully.\n", chunk_id, total_chunks);
  }
  
  file.close();
  return allChunksSent;
}


// ---
// 2. HELPER FUNCTION: SENDS ONE RAW CHUNK
// ---
bool sendChunk(int chunk_id, int total_chunks, const char* filename, File &file) {
  int attempt = 0;
  
  size_t fileSize = file.size();
  size_t startPos = (chunk_id - 1) * CHUNK_SIZE;
  size_t bytesToSend = (startPos + CHUNK_SIZE > fileSize) ? (fileSize - startPos) : CHUNK_SIZE;

  // Allocate memory for the chunk
  uint8_t *dataBuffer = (uint8_t*) malloc(bytesToSend);
  if (dataBuffer == NULL) {
      Serial.println("Failed to allocate memory for chunk buffer!");
      return false;
  }
  
  file.seek(startPos);
  file.read(dataBuffer, bytesToSend);

  while (attempt < maxRetries) {
    if (WiFi.status() != WL_CONNECTED) connectWiFi();

    HTTPClient http;
    http.setInsecure();
    http.begin(serverUrl);
    http.setTimeout(20000); // 20-second timeout

    // Set Content-Type to plain text.
    http.addHeader("Content-Type", "text/plain"); 
    
    // Send headers your server needs to identify the chunk
    http.addHeader("X-Device-ID", DEVICE_ID);
    http.addHeader("X-Chunk-ID", String(chunk_id));
    http.addHeader("X-Total-Chunks", String(total_chunks));

    // Send the POST request with the raw buffer
    int httpCode = http.POST(dataBuffer, bytesToSend);
    
    if (httpCode > 0) {
      String response = http.getString();
      http.end(); 
      
      if (httpCode == 200) { // 200 OK
        free(dataBuffer); 
        return true; // Success
      } else {
        Serial.printf("[Chunk %d] Server error (HTTP %d): %s\n", chunk_id, httpCode, response.c_str());
      }
    } else {
      http.end();
      Serial.printf("[Chunk %d] HTTP failed: %s\n", chunk_id, http.errorToString(httpCode).c_str());
    }

    attempt++;
    delay(delayBetweenRetries);
  }
  
  free(dataBuffer); // Free memory on total failure
  return false; 
}


// ---
// 3. UTILITY FUNCTIONS (Unchanged)
// ---
void connectWiFi() {
  Serial.printf("Connecting to WiFi: %s\n", ssid);
  WiFi.begin(ssid, password);
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    retry++;
    if (retry > 60) {
      Serial.println("\nWiFi connect timeout, retrying...");
      WiFi.begin(ssid, password);
      retry = 0;
    }
  }
  Serial.println("\n✅ WiFi connected!");
  Serial.print("IP address: "); Serial.println(WiFi.localIP());
}

bool initSDCard() {
  if (!SD.begin(SD_CS_PIN)) {
    Serial.println("SD Card mount failed! Check wiring.");
    return false;
  }
  uint8_t cardType = SD.cardType();
  if (cardType == CARD_NONE) {
    Serial.println("No SD card attached");
    return false;
  }
  Serial.println("SD Card initialized.");
  return true;
}
