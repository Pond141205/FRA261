import requests
import time

# ---------- CONFIG ----------
API_URL = "https://unconserving-madelyn-glottogonic.ngrok-free.dev/upload_chunk"
DEVICE_ID = "TEST_DEVICE"
BATCH_ID = "TESTBATCH001"
TOTAL_CHUNKS = 3

# ---------- TEST DATA (Fake Point Cloud) ----------
chunks = [
    "0.1 0.2 0.3\n0.5 0.2 0.1\n0.3 0.3 0.7\n",
    "0.4 0.1 1.2\n0.9 0.2 0.2\n0.8 0.3 0.3\n",
    "1.0 0.2 1.2\n1.2 0.4 0.5\n0.7 0.8 0.9\n"
]

# ---------- SEND TEST CHUNKS ----------
for i, chunk in enumerate(chunks):
    headers = {
        "X-Device-ID": DEVICE_ID,
        "X-Batch-ID": BATCH_ID,
        "X-Total-Chunks": str(TOTAL_CHUNKS),
        "X-Chunk-ID": str(i + 1)
    }

    try:
        r = requests.post(API_URL, headers=headers, data=chunk.encode('utf-8'))
        print(f"Chunk {i+1}/{TOTAL_CHUNKS}:", r.json())
    except Exception as e:
        print("เกิดข้อผิดพลาด:", e)

    time.sleep(1)  # กัน spam เร็วเกินไป

print("📌 ส่งข้อมูลทดสอบครบแล้ว!")
