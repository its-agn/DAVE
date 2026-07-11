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
const char* WIFI_SSID = "Your_Gym_WiFi";
const char* WIFI_PASS = "Your_Password";
const char* SERVER_URL = "http://192.168.1.X:8000/api/swing";

const int SAMPLE_RATE_HZ = 500;
const unsigned long SAMPLE_PERIOD_US = 1000000 / SAMPLE_RATE_HZ; // 2000 microseconds

// Buffer boundaries to prevent RAM explosion
const int MAX_SAMPLES = 1000; 

// Threshold variables for swing detection
const float SWING_START_THRESHOLD = 25.0f; // Tune based on raw gyro/accel magnitude
const float SWING_END_THRESHOLD   = 5.0f;
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
unsigned long motionEndTimer = 0;

// Forward Declarations
void handleIdleState();
void handleRecordingState();
void streamDataToLaptop();

// ==========================================
// 4. Main Core Functions
// ==========================================
void setup() {
    Serial.begin(115200);
    Wire.begin(21, 22); // Explicitly pin down SDA=21, SCL=22
    Wire.setClock(400000); // Kick I2C bus up to 400kHz Fast Mode
    
    // Initialize your IMU instances
    if (!forearmIMU.begin() || !bicepIMU.begin()) {
        Serial.println("Hardware Init Failed! Check AD0/Power lines.");
        while(1); // Freeze if hardware is missing
    }
    
    // Connect to local Wi-Fi router
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("Connecting to Wi-Fi...");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nConnected! Ready for telemetry.");
}

void loop() {
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


    // --------------------------------------------------
    // 3. IF magnitude > SWING_START_THRESHOLD:
    //      - Reset sampleCount to 0
    //      - Flip currentState = STATE_RECORDING
    // --------------------------------------------------

    // Check whether the detected motion is greater than
    // the configured swing-start threshold.
    if (magnitude > SWING_START_THRESHOLD) {

        // Clear the previous sample count so the new swing
        // begins writing at the start of swingBuffer.
        sampleCount = 0;

        // Change the state machine from IDLE to RECORDING.
        currentState = STATE_RECORDING;
    }
}

void handleRecordingState() {
    unsigned long currentMicros = micros();
    
    // Strict, deterministic execution loop based on microsecond interval
    if (currentMicros - lastSampleMicros >= SAMPLE_PERIOD_US) {
        lastSampleMicros = currentMicros;
        
        // 1. Call update() on both IMU managers
        // 2. Fetch data states and pack into swingBuffer[sampleCount]
        // 3. Increment sampleCount
        
        // 4. Safety Guard: Check if buffer is completely filled
        if (sampleCount >= MAX_SAMPLES) {
            currentState = STATE_TRANSMITTING;
            return;
        }
        
        // 5. Check Cooldown Thresholds to determine if movement stopped
        //    IF motion < SWING_END_THRESHOLD:
        //        Check if duration has crossed COOLDOWN_MS
        //        IF yes: currentState = STATE_TRANSMITTING
    }
}

void streamDataToLaptop() {
    Serial.println("Swing detected and frozen. Initiating transmission...");
    
    WiFiClient client;
    HTTPClient http;
    
    if (http.begin(client, SERVER_URL)) {
        http.addHeader("Content-Type", "application/json");
        
        // Start network tracking payload connection
        // Note: For advanced chunked streaming, you will hook into http.POST(stream)
        
        // TODO: Loop through swingBuffer from 0 to sampleCount.
        // In each pass, clear a small local JsonDocument, map the single row,
        // and serialize directly down into the client socket pipe.
        
        int httpResponseCode = http.POST("placeholder"); 
        
        if (httpResponseCode > 0) {
            Serial.printf("Server Response: %d\n", httpResponseCode);
        } else {
            Serial.printf("Transmission failed: %s\n", http.errorToString(httpResponseCode).c_str());
        }
        
        http.end();
    }
    
    // Reset control variables back to clean baseline state
    sampleCount = 0;
    currentState = STATE_IDLE;
    Serial.println("System reset to IDLE. Listening for next swing...");
}