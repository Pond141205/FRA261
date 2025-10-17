#include "config.h"
#include "lidar_reader.h"
#include "cellular_client.h"
#include "pointcloud_encoder.h"

void setup() {
  Serial.begin(115200);
  lidar_init();
  cellular_init(APN);
}

void loop() {
  float distances[100];
  int count = lidar_scan(distances);
  String payload = encode_pointcloud(DEVICE_ID, distances, count);
  cellular_post(SERVER_URL, payload);
  delay(SCAN_INTERVAL_MS);
}