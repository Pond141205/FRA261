#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// --- WiFi ---
const char* ssid = "******";
const char* password = "******";

// --- Server ---
const char* serverUrl = "http://192.168.1.107:5000/upload_chunk";

// --- Device ID ---
#define DEVICE_ID "S001_01"

// --- Chunk config ---
const int total_chunks = 5;
const int points_per_chunk = 3;

// --- Retry settings ---
const int maxRetries = 3;
const int delayBetweenRetries = 2000; // ms

// --- Batch interval ---
const unsigned long batchInterval = 60 * 60 * 1000UL; // 1 hour

void setup() {
  Serial.begin(115200);
  connectWiFi();
  randomSeed(analogRead(0));
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  Serial.println("Starting new batch...");

  for (int chunk_id = 1; chunk_id <= total_chunks; chunk_id++) {
    bool sent = sendChunk(chunk_id);
    if (!sent) {
      Serial.printf("[Chunk %d] Failed after %d retries. Skipping.\n", chunk_id, maxRetries);
    }
    delay(3000); // space between chunks
  }

  Serial.println("Batch complete. Waiting for next batch...");
  delay(batchInterval);
}

void connectWiFi() {
  Serial.printf("Connecting to WiFi: %s\n", ssid);
  WiFi.begin(ssid, password);
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    retry++;
    if (retry > 60) { // 30s timeout
      Serial.println("\nWiFi connect timeout, retrying...");
      WiFi.begin(ssid, password);
      retry = 0;
    }
  }
  Serial.println("\n✅ WiFi connected!");
  Serial.print("IP address: "); Serial.println(WiFi.localIP());
}

// Generate random mock points (replace with real sensor data)
void generatePoint(JsonArray &pt) {
  pt.add(random(0, 500) / 100.0); // x
  pt.add(random(0, 500) / 100.0); // y
  pt.add(random(0, 500) / 100.0); // z
}

bool sendChunk(int chunk_id) {
  int attempt = 0;
  while (attempt < maxRetries) {
    if (WiFi.status() != WL_CONNECTED) connectWiFi();

    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-ID", DEVICE_ID);

    StaticJsonDocument<1024> doc;
    JsonObject chunk = doc.createNestedObject("chunk");
    chunk["total_chunks"] = total_chunks;
    chunk["chunk_id"] = chunk_id;

    JsonArray points = chunk.createNestedArray("points");
    for (int i = 0; i < points_per_chunk; i++) {
      JsonArray pt = points.createNestedArray();
      generatePoint(pt);
    }

    String payload;
    serializeJson(doc, payload);

    int httpCode = http.POST(payload);
    if (httpCode > 0) {
      String response = http.getString();
      Serial.printf("[Chunk %d] Response: %s\n", chunk_id, response.c_str());

      // Check if server accepted chunk
      if (httpCode == 200) {
        http.end();
        return true; // success
      } else {
        Serial.printf("[Chunk %d] Server error, HTTP code: %d\n", chunk_id, httpCode);
      }
    } else {
      Serial.printf("[Chunk %d] HTTP failed: %s\n", chunk_id, http.errorToString(httpCode).c_str());
    }

    http.end();
    attempt++;
    delay(delayBetweenRetries);
  }

  return false; // failed after retries
}
// Note: This code is designed for Arduino framework with WiFi capabilities. But there is no real point cloud data source; it generates random points for testing purposes.