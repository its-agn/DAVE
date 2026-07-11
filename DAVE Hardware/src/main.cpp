#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

#include "DataStructures.h"
#include "IMUManager.h"

// ==========================================
// 1. Configuration & Constants
// ==========================================
const char* WIFI_SSID = "agn_omen_hotspot";
const char* WIFI_PASS = "DAVEPASS";
const char* SERVER_URL = "http://192.168.137.1:8000/api/swing";

const int SAMPLE_RATE_HZ = 200;
const unsigned long SAMPLE_PERIOD_US = 1000000 / SAMPLE_RATE_HZ; // 5000 microseconds

// Buffer boundaries to prevent RAM explosion
const int MAX_SAMPLES = 300; 

// Threshold variables for swing detection
const float SWING_START_THRESHOLD = 6.0f; // Tune based on raw gyro/accel magnitude
const float SWING_END_THRESHOLD   = 1.0f;
const unsigned long COOLDOWN_MS   = 500;   // Time quiet required to declare swing over

// ==========================================
// 2. State Machine & Data Storage
// ==========================================
enum SystemState {
    STATE_IDLE,
    STATE_RECORDING,
    STATE_TRANSMITTING
};

SystemState currentState = STATE_IDLE;

// Pre-allocated static binary buffer in RAM
// Holds raw calculated metrics for both segments per time slice
struct CompactSample {
    uint32_t time_offset_ms;
    ArmSegmentState forearm;
    ArmSegmentState bicep;
};

CompactSample swingBuffer[MAX_SAMPLES];
int sampleCount = 0;

// ==========================================
// 3. Hardware Initializations
// ==========================================
IMUManager forearmIMU(0x68); // AD0 Low
IMUManager bicepIMU(0x69);   // AD0 High

// Trackers for timing loops
unsigned long lastSampleMicros = 0;
unsigned long swingStartMicros = 0;
unsigned long motionEndTimer = 0;

// Forward Declarations
void handleIdleState();
void handleRecordingState();
void streamDataToLaptop();

void printTelemetryDashboard(const ArmSegmentState& forearm, const ArmSegmentState& bicep);
bool isBackendHealthy();

// ==========================================
// 4. Main Core Functions
// ==========================================
void setup() {
    Serial.begin(115200);
    Wire.begin(21, 22); // Explicitly pin down SDA=21, SCL=22
    Wire.setClock(400000); // Kick I2C bus up to 400kHz Fast Mode
    
    // Initialize your IMU instances
    if (!bicepIMU.begin()) {
        Serial.println("Bicep IMU Failed! Check AD0/Power lines.");
        while(1); // Freeze if hardware is missing
    }

    if (!forearmIMU.begin()) {
        Serial.println("Forearm IMU Failed! Check AD0/Power lines.");
        while(1); // Freeze if hardware is missing
    }

    WiFi.disconnect(true); // Clear out any glitched persistent credentials
    delay(100);
    WiFi.mode(WIFI_STA);   // Explicitly force Station (Client) Mode

    // --- STATIC IP CONFIGURATION FOR WINDOWS HOTSPOT ---
    IPAddress local_IP(192, 168, 137, 50);   // The IP your ESP32 will take
    IPAddress gateway(192, 168, 137, 1);    // Your laptop's hotspot IP
    IPAddress subnet(255, 255, 255, 0);
    IPAddress dns(192, 168, 137, 1);

    if (!WiFi.config(local_IP, gateway, subnet, dns)) {
        Serial.println("Static IP Configuration Failed!");
    }
    // ----------------------------------------------------

    WiFi.begin(WIFI_SSID, WIFI_PASS);
    
    Serial.println("\nConnecting to Wi-Fi...");
    
    int attemptCounter = 0;
    while (WiFi.status() != WL_CONNECTED) {
        delay(1000);
        attemptCounter++;
        
        int statusCode = WiFi.status();
        Serial.printf("Attempt %d - Status Code: %d\n", attemptCounter, statusCode);
        
        if (attemptCounter > 15) {
            Serial.println("\n[DIAGNOSTIC] Connection timing out. Re-issuing begin...");
            WiFi.begin(WIFI_SSID, WIFI_PASS);
            attemptCounter = 0;
        }
    }
    
    Serial.println("\nConnected! Ready for telemetry.");

    isBackendHealthy();
}

void loop() {
    // forearmIMU.update();
    // bicepIMU.update();
    // printTelemetryDashboard(forearmIMU.getState(), bicepIMU.getState());

    switch (currentState) {
        case STATE_IDLE:
            handleIdleState();
            break;
            
        case STATE_RECORDING:
            handleRecordingState();
            break;
            
        case STATE_TRANSMITTING:
            streamDataToLaptop();
            break;
    }
}

// ==========================================
// 5. State Machine Implementations
// ==========================================

void handleIdleState() {
    // --------------------------------------------------
    // 1. Run low-frequency sensor update to maintain
    //    filter alignment
    // --------------------------------------------------

    // Store the last time the IMUs were updated while idle.
    // "static" keeps this value between function calls.
    static unsigned long lastIdleUpdateMicros = 0;

    // Get the current ESP32 time in microseconds.
    unsigned long currentMicros = micros();

    // Only update the IMUs every 20,000 microseconds.
    // 20,000 us = 20 ms = 50 Hz idle update rate.
    if (currentMicros - lastIdleUpdateMicros < 20000) {
        return;
    }

    // Save the time of this idle update.
    lastIdleUpdateMicros = currentMicros;

    // Update both IMUs so the Mahony filters continue
    // receiving accelerometer and gyroscope measurements.
    forearmIMU.update();
    bicepIMU.update();


    // --------------------------------------------------
    // 2. Calculate dynamic acceleration or angular
    //    velocity magnitude
    // --------------------------------------------------

    // Get the newest calculated state from each IMU.
    ArmSegmentState forearmState = forearmIMU.getState();
    ArmSegmentState bicepState = bicepIMU.getState();

    // Calculate the forearm angular velocity magnitude.
    // Magnitude = sqrt(x^2 + y^2 + z^2)
    float forearmMagnitude = sqrt(
        forearmState.angularVelocity.x * forearmState.angularVelocity.x +
        forearmState.angularVelocity.y * forearmState.angularVelocity.y +
        forearmState.angularVelocity.z * forearmState.angularVelocity.z
    );

    // Calculate the bicep angular velocity magnitude.
    // Magnitude = sqrt(x^2 + y^2 + z^2)
    float bicepMagnitude = sqrt(
        bicepState.angularVelocity.x * bicepState.angularVelocity.x +
        bicepState.angularVelocity.y * bicepState.angularVelocity.y +
        bicepState.angularVelocity.z * bicepState.angularVelocity.z
    );

    // Use whichever IMU currently has the greater amount
    // of angular motion as the system motion magnitude.
    float magnitude = max(forearmMagnitude, bicepMagnitude);

    Serial.printf("Magnitude: %f\n", magnitude);


    // --------------------------------------------------
    // 3. IF magnitude > SWING_START_THRESHOLD:
    //      - Reset sampleCount to 0
    //      - Flip currentState = STATE_RECORDING
    // --------------------------------------------------

    // Check whether the detected motion is greater than
    // the configured swing-start threshold.
    if (magnitude > SWING_START_THRESHOLD) {
        Serial.println("\n[SYSTEM] Swing Detected! Freezing idle and starting capture...");

        // Lock the absolute clock grid baselines
        unsigned long lockTime = micros();
        lastSampleMicros = lockTime;
        swingStartMicros = lockTime;

        // Clear previous sample trackers
        sampleCount = 0;
        motionEndTimer = 0;

        // Change the state machine from IDLE to RECORDING.
        currentState = STATE_RECORDING;
    }
}

void handleRecordingState() {
    unsigned long currentMicros = micros();
    
    // Strict, drift-free deterministic execution grid
    if (currentMicros - lastSampleMicros >= SAMPLE_PERIOD_US) {
        // Step forward by exactly one sample period to eliminate execution jitter
        lastSampleMicros += SAMPLE_PERIOD_US; 
        
        // 1. Call update() on both IMU managers
        forearmIMU.update();
        bicepIMU.update();

        // 2. Fetch data states and pack into swingBuffer[sampleCount]
        ArmSegmentState forearmState = forearmIMU.getState();
        ArmSegmentState bicepState = bicepIMU.getState();

        // Calculate beautiful, clean ascending millisecond offsets starting from 0ms
        uint32_t relativeTimeMs = (lastSampleMicros - swingStartMicros) / 1000;

        CompactSample sample = {
            .time_offset_ms = relativeTimeMs,
            .forearm = forearmState,
            .bicep = bicepState
        };

        swingBuffer[sampleCount] = sample;

        // 3. Increment sampleCount
        sampleCount++;
        
        // 4. Safety Guard: Check if buffer is completely filled
        if (sampleCount >= MAX_SAMPLES) {
            currentState = STATE_TRANSMITTING;
            return;
        }
        
        // 5. Check Cooldown Thresholds to determine if movement stopped
        float forearmMagnitude = sqrt(
            forearmState.angularVelocity.x * forearmState.angularVelocity.x +
            forearmState.angularVelocity.y * forearmState.angularVelocity.y +
            forearmState.angularVelocity.z * forearmState.angularVelocity.z
        );

        float bicepMagnitude = sqrt(
            bicepState.angularVelocity.x * bicepState.angularVelocity.x +
            bicepState.angularVelocity.y * bicepState.angularVelocity.y +
            bicepState.angularVelocity.z * bicepState.angularVelocity.z
        );

        float magnitude = max(forearmMagnitude, bicepMagnitude);

        if (magnitude < SWING_END_THRESHOLD) {
            motionEndTimer += SAMPLE_PERIOD_US;
            if (motionEndTimer >= COOLDOWN_MS * 1000) {
                currentState = STATE_TRANSMITTING;
            }
        } else {
            motionEndTimer = 0;
        }      
    }
}

void streamDataToLaptop() {
    Serial.println("\n===========================================");
    Serial.printf("[DEBUG] Swing frozen. Initiating transmission...\n");
    Serial.printf("[DEBUG] Total Samples Captured: %d\n", sampleCount);
    
    if (sampleCount == 0) {
        Serial.println("[DEBUG] CRITICAL ERROR: sampleCount is 0! The recording loop was skipped.");
        motionEndTimer = 0;
        currentState = STATE_IDLE;
        return;
    }
    Serial.println("===========================================\n");

    int stream_start = millis();
    WiFiClient client;

    String serverURL = SERVER_URL;
    serverURL.replace("http://", "");

    int pathIndex = serverURL.indexOf('/');
    String hostAndPort = serverURL.substring(0, pathIndex);
    String apiPath = serverURL.substring(pathIndex);

    uint16_t port = 80;
    int portIndex = hostAndPort.indexOf(':');
    String host = hostAndPort;

    if (portIndex >= 0) {
        port = hostAndPort.substring(portIndex + 1).toInt();
        host = hostAndPort.substring(0, portIndex);
    }

    if (!client.connect(host.c_str(), port)) {
        Serial.println("Transmission failed: Could not connect to server.");
        motionEndTimer = 0;
        sampleCount = 0;
        currentState = STATE_IDLE;
        return;
    }

    // Set no delay AFTER a successful connection establishes a valid socket
    client.setNoDelay(true);

    // WiFiClient::write() may write fewer bytes than requested. Keep writing
    // until the full section is sent or the connection fails/times out.
    auto writeAll = [&client](const uint8_t* data, size_t length) -> bool {
        size_t totalWritten = 0;
        unsigned long lastProgress = millis();

        while (totalWritten < length) {
            if (!client.connected()) {
                return false;
            }

            size_t written = client.write(
                data + totalWritten,
                length - totalWritten
            );

            if (written > 0) {
                totalWritten += written;
                lastProgress = millis();
            }
            else {
                if (millis() - lastProgress > 5000) {
                    return false;
                }
                delay(1);
            }
        }

        return true;
    };

    String requestHeaders;
    requestHeaders.reserve(192);
    requestHeaders += "POST ";
    requestHeaders += apiPath;
    requestHeaders += " HTTP/1.1\r\nHost: ";
    requestHeaders += host;
    requestHeaders += ":";
    requestHeaders += String(port);
    requestHeaders += "\r\nContent-Type: application/json";
    requestHeaders += "\r\nTransfer-Encoding: chunked";
    requestHeaders += "\r\nConnection: close\r\n\r\n";

    if (!writeAll(
            reinterpret_cast<const uint8_t*>(requestHeaders.c_str()),
            requestHeaders.length()
        )) {
        Serial.println("Transmission failed while sending HTTP headers.");
        client.stop();
        motionEndTimer = 0;
        sampleCount = 0;
        currentState = STATE_IDLE;
        return;
    }

    auto flushChunkBuffer = [&writeAll](String& buffer) -> bool {
        if (buffer.length() == 0) {
            return true;
        }

        String chunkHeader = String(buffer.length(), HEX);
        chunkHeader.toUpperCase();
        chunkHeader += "\r\n";

        static const char chunkEnding[] = "\r\n";

        bool success = writeAll(
            reinterpret_cast<const uint8_t*>(chunkHeader.c_str()),
            chunkHeader.length()
        );
        success = success && writeAll(
            reinterpret_cast<const uint8_t*>(buffer.c_str()),
            buffer.length()
        );
        success = success && writeAll(
            reinterpret_cast<const uint8_t*>(chunkEnding),
            sizeof(chunkEnding) - 1
        );

        if (success) {
            buffer = "";
        }

        return success;
    };

    String chunkBuffer;
    chunkBuffer.reserve(4096); 
    
    JsonDocument sampleDocument;
    String tempSampleString;
    tempSampleString.reserve(512);

    chunkBuffer = "{\"side\":\"R\",\"IMU 1\":[";
    bool transmissionSucceeded = true;

    for (int i = 0; i < sampleCount; i++) {
        sampleDocument.clear();
        sampleDocument["timestamp_s"] = swingBuffer[i].time_offset_ms / 1000.0;
        
        sampleDocument["accel_mps2"]["x"] = swingBuffer[i].forearm.absoluteAccel.x;
        sampleDocument["accel_mps2"]["y"] = swingBuffer[i].forearm.absoluteAccel.y;
        sampleDocument["accel_mps2"]["z"] = swingBuffer[i].forearm.absoluteAccel.z;

        sampleDocument["gyro_rads"]["x"] = swingBuffer[i].forearm.angularVelocity.x;
        sampleDocument["gyro_rads"]["y"] = swingBuffer[i].forearm.angularVelocity.y;
        sampleDocument["gyro_rads"]["z"] = swingBuffer[i].forearm.angularVelocity.z;

        sampleDocument["quaternion_wxyz"]["w"] = swingBuffer[i].forearm.orientation.w;
        sampleDocument["quaternion_wxyz"]["x"] = swingBuffer[i].forearm.orientation.x;
        sampleDocument["quaternion_wxyz"]["y"] = swingBuffer[i].forearm.orientation.y;
        sampleDocument["quaternion_wxyz"]["z"] = swingBuffer[i].forearm.orientation.z;

        sampleDocument["linear_accel_mps2"]["x"] = swingBuffer[i].forearm.relativeAccel.x;
        sampleDocument["linear_accel_mps2"]["y"] = swingBuffer[i].forearm.relativeAccel.y;
        sampleDocument["linear_accel_mps2"]["z"] = swingBuffer[i].forearm.relativeAccel.z;

        sampleDocument["gravity_mps2"]["x"] = swingBuffer[i].forearm.gravityVector.x;
        sampleDocument["gravity_mps2"]["y"] = swingBuffer[i].forearm.gravityVector.y;
        sampleDocument["gravity_mps2"]["z"] = swingBuffer[i].forearm.gravityVector.z;

        if (i > 0) {
            chunkBuffer += ",";
        }
        
        tempSampleString = "";
        serializeJson(sampleDocument, tempSampleString);
        
        // --- NEW DIAGNOSTIC CHECK ---
        if (i == 0) {
            Serial.println("[DEBUG] Preview of Sample Index 0 (IMU 1):");
            Serial.println(tempSampleString);
        }
        
        chunkBuffer += tempSampleString;

        if (chunkBuffer.length() > 3500) {
            if (!flushChunkBuffer(chunkBuffer)) {
                transmissionSucceeded = false;
                break;
            }
        }
    }

    if (transmissionSucceeded) {
        chunkBuffer += "],\"IMU 2\":[";
    }

    for (int i = 0; transmissionSucceeded && i < sampleCount; i++) {
        sampleDocument.clear();
        sampleDocument["timestamp_s"] = swingBuffer[i].time_offset_ms / 1000.0;

        sampleDocument["accel_mps2"]["x"] = swingBuffer[i].bicep.absoluteAccel.x;
        sampleDocument["accel_mps2"]["y"] = swingBuffer[i].bicep.absoluteAccel.y;
        sampleDocument["accel_mps2"]["z"] = swingBuffer[i].bicep.absoluteAccel.z;

        sampleDocument["gyro_rads"]["x"] = swingBuffer[i].bicep.angularVelocity.x;
        sampleDocument["gyro_rads"]["y"] = swingBuffer[i].bicep.angularVelocity.y;
        sampleDocument["gyro_rads"]["z"] = swingBuffer[i].bicep.angularVelocity.z;

        sampleDocument["quaternion_wxyz"]["w"] = swingBuffer[i].bicep.orientation.w;
        sampleDocument["quaternion_wxyz"]["x"] = swingBuffer[i].bicep.orientation.x;
        sampleDocument["quaternion_wxyz"]["y"] = swingBuffer[i].bicep.orientation.y;
        sampleDocument["quaternion_wxyz"]["z"] = swingBuffer[i].bicep.orientation.z;

        sampleDocument["linear_accel_mps2"]["x"] = swingBuffer[i].bicep.relativeAccel.x;
        sampleDocument["linear_accel_mps2"]["y"] = swingBuffer[i].bicep.relativeAccel.y;
        sampleDocument["linear_accel_mps2"]["z"] = swingBuffer[i].bicep.relativeAccel.z;

        sampleDocument["gravity_mps2"]["x"] = swingBuffer[i].bicep.gravityVector.x;
        sampleDocument["gravity_mps2"]["y"] = swingBuffer[i].bicep.gravityVector.y;
        sampleDocument["gravity_mps2"]["z"] = swingBuffer[i].bicep.gravityVector.z;

        if (i > 0) {
            chunkBuffer += ",";
        }
        
        tempSampleString = "";
        serializeJson(sampleDocument, tempSampleString);
        chunkBuffer += tempSampleString;

        if (chunkBuffer.length() > 3500) {
            if (!flushChunkBuffer(chunkBuffer)) {
                transmissionSucceeded = false;
                break;
            }
        }
    }

    if (transmissionSucceeded) {
        chunkBuffer += "]}";
        transmissionSucceeded = flushChunkBuffer(chunkBuffer);
    }

    static const char finalChunk[] = "0\r\n\r\n";
    if (transmissionSucceeded) {
        transmissionSucceeded = writeAll(
            reinterpret_cast<const uint8_t*>(finalChunk),
            sizeof(finalChunk) - 1
        );
    }

    if (!transmissionSucceeded) {
        Serial.println(
            "Transmission failed: socket closed before the full JSON body was sent."
        );
        client.stop();
        motionEndTimer = 0;
        sampleCount = 0;
        currentState = STATE_IDLE;
        return;
    }

    unsigned long responseStartTime = millis();
    bool responseReceived = false;

    while (client.connected() && millis() - responseStartTime < 3000) {
        while (client.available()) {
            String responseLine = client.readStringUntil('\n');
            Serial.println(responseLine);
            responseReceived = true;
            responseStartTime = millis(); 
        }
        delay(1);
    }

    if (!responseReceived) {
        Serial.println("Transmission finished: No text response returned from server endpoint.");
    }

    client.stop();
    motionEndTimer = 0;
    sampleCount = 0;
    currentState = STATE_IDLE;
    int stream_end = millis();
    Serial.printf("ms time to parse and send: %d ms\n", stream_end - stream_start);
    Serial.println("System reset to IDLE. Listening for next swing...");
}


void printTelemetryDashboard(const ArmSegmentState& forearm, const ArmSegmentState& bicep) {
    // 1. Self-contained throttle: exit early if 200ms haven't elapsed
    static unsigned long lastDebugPrint = 0;
    if (millis() - lastDebugPrint < 200) { 
        return; 
    }
    lastDebugPrint = millis();

    // 2. Teleport cursor back to Row 1, Column 1 (Overwrites inline without flashing)
    Serial.print("\e[H"); 

    Serial.println("=================================================");
    Serial.println("             DAVE HARDWARE TELEMETRY             ");
    Serial.println("=================================================");
    Serial.printf(" System Time: %7u ms                             \n", millis());
    Serial.println("-------------------------------------------------");
    
    // --- FOREARM ROW (0x68) ---
    Serial.println("[FOREARM TRACKER (0x68)]                         ");
    Serial.printf("  Quat (WXYZ):  [%5.2f, %5.2f, %5.2f, %5.2f]     \n", 
                  forearm.orientation.w, forearm.orientation.x, forearm.orientation.y, forearm.orientation.z);
    Serial.printf("  Gyro (rad/s): [X:%5.2f, Y:%5.2f, Z:%5.2f]     \n", 
                  forearm.angularVelocity.x, forearm.angularVelocity.y, forearm.angularVelocity.z);
    Serial.printf("  Lin Acc(m/s2):[X:%5.2f, Y:%5.2f, Z:%5.2f]     \n", 
                  forearm.relativeAccel.x, forearm.relativeAccel.y, forearm.relativeAccel.z);
                  
    Serial.println("-------------------------------------------------");
    
    // --- BICEP ROW (0x69) ---
    Serial.println("[BICEP TRACKER (0x69)]                           ");
    Serial.printf("  Quat (WXYZ):  [%5.2f, %5.2f, %5.2f, %5.2f]     \n", 
                  bicep.orientation.w, bicep.orientation.x, bicep.orientation.y, bicep.orientation.z);
    Serial.printf("  Gyro (rad/s): [X:%5.2f, Y:%5.2f, Z:%5.2f]     \n", 
                  bicep.angularVelocity.x, bicep.angularVelocity.y, bicep.angularVelocity.z);
    Serial.printf("  Lin Acc(m/s2):[X:%5.2f, Y:%5.2f, Z:%5.2f]     \n", 
                  bicep.relativeAccel.x, bicep.relativeAccel.y, bicep.relativeAccel.z);
    Serial.println("=================================================");
}

bool isBackendHealthy() {
    HTTPClient http;
    WiFiClient client; // Re-use a standard client socket for the GET request
    
    const char* HEALTH_URL = "http://192.168.137.1:8000/health";
    
    // Initialize the client target
    if (!http.begin(client, HEALTH_URL)) {
        Serial.println("[HEALTH] Setup failed to initialize endpoint string.");
        return false;
    }
    
    Serial.println("[HEALTH] Pinging laptop backend server...");
    
    // Execute the synchronous GET request
    int httpResponseCode = http.GET();
    bool healthy = false;
    
    // Evaluate the return code
    if (httpResponseCode > 0) {
        Serial.printf("[HEALTH] Server responded with code: %d\n", httpResponseCode);
        
        // If the server returns standard 200 OK, we are green lit
        if (httpResponseCode == HTTP_CODE_OK) { // HTTP_CODE_OK is a built-in macro for 200
            healthy = true;
        }
    } else {
        Serial.printf("[HEALTH] Connection failed! Error code: %s\n", http.errorToString(httpResponseCode).c_str());
    }
    
    // CRITICAL: Always close the socket to free up the ESP32 network stack
    http.end(); 
    return healthy;
}
