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

void printTelemetryDashboard(const ArmSegmentState& forearm, const ArmSegmentState& bicep);

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
    // WiFi.begin(WIFI_SSID, WIFI_PASS);
    // Serial.print("Connecting to Wi-Fi...");
    // while (WiFi.status() != WL_CONNECTED) {
    //     delay(500);
    //     Serial.print(".");
    // }
    Serial.println("\nConnected! Ready for telemetry.");
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
        forearmIMU.update();
        bicepIMU.update();

        // 2. Fetch data states and pack into swingBuffer[sampleCount]
        ArmSegmentState forearmState = forearmIMU.getState();
        ArmSegmentState bicepState = bicepIMU.getState();

        CompactSample sample = {
            .time_offset_ms = (currentMicros - lastSampleMicros) / 1000,
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
        //    IF motion < SWING_END_THRESHOLD:
        //        Check if duration has crossed COOLDOWN_MS
        //        IF yes: currentState = STATE_TRANSMITTING
        
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
    Serial.println("Swing detected and frozen. Initiating transmission...");

    WiFiClient client;

    // --------------------------------------------------
    // Break SERVER_URL into the server host and API path
    //
    // Example:
    // http://192.168.1.100:8000/api/swing
    //
    // Host = 192.168.1.100
    // Port = 8000
    // Path = /api/swing
    // --------------------------------------------------

    String serverURL = SERVER_URL;

    // Remove "http://" from the beginning of the URL.
    serverURL.replace("http://", "");

    // Find where the API path begins.
    int pathIndex = serverURL.indexOf('/');

    // Store the host/port section.
    String hostAndPort = serverURL.substring(0, pathIndex);

    // Store the API endpoint path.
    String apiPath = serverURL.substring(pathIndex);

    // Default HTTP port.
    uint16_t port = 80;

    // Check whether a custom port was included.
    int portIndex = hostAndPort.indexOf(':');

    // Store the server hostname or IP address.
    String host = hostAndPort;

    if (portIndex >= 0) {
        // Extract the custom port number.
        port = hostAndPort.substring(portIndex + 1).toInt();

        // Remove the port from the host string.
        host = hostAndPort.substring(0, portIndex);
    }


    // --------------------------------------------------
    // Connect directly to the laptop server
    // --------------------------------------------------

    if (!client.connect(host.c_str(), port)) {
        Serial.println("Transmission failed: Could not connect to server.");

        // Reset control variables back to clean baseline state.
        sampleCount = 0;
        currentState = STATE_IDLE;

        Serial.println("System reset to IDLE. Listening for next swing...");

        return;
    }


    // --------------------------------------------------
    // Send HTTP POST headers
    //
    // Chunked transfer encoding allows the ESP32 to send
    // JSON in small sections instead of creating one huge
    // JSON String containing the entire swing.
    // --------------------------------------------------

    client.print("POST ");
    client.print(apiPath);
    client.println(" HTTP/1.1");

    client.print("Host: ");
    client.println(host);

    client.println("Content-Type: application/json");
    client.println("Transfer-Encoding: chunked");
    client.println("Connection: close");
    client.println();


    // --------------------------------------------------
    // Helper function for sending raw JSON text as one
    // HTTP chunk.
    // --------------------------------------------------

    auto sendRawChunk = [&client](const char* text) {
        // Find the number of bytes in this JSON section.
        size_t chunkLength = strlen(text);

        // Send chunk size in hexadecimal.
        client.printf("%X\r\n", chunkLength);

        // Send the JSON text.
        client.print(text);

        // End the HTTP chunk.
        client.print("\r\n");
    };


    // --------------------------------------------------
    // Small local JSON document used for one IMU sample.
    //
    // The document is cleared and reused for every row.
    // This prevents a large JSON document from consuming
    // all available ESP32 RAM.
    // --------------------------------------------------

    JsonDocument sampleDocument;


    // --------------------------------------------------
    // Helper function for serializing one JsonDocument
    // directly into the client socket.
    // --------------------------------------------------

    auto sendJsonChunk = [&client](JsonDocument& document) {
        // Calculate serialized JSON size before sending it.
        size_t chunkLength = measureJson(document);

        // Send chunk size in hexadecimal.
        client.printf("%X\r\n", chunkLength);

        // Serialize JSON directly into the network socket.
        serializeJson(document, client);

        // End the HTTP chunk.
        client.print("\r\n");
    };


    // --------------------------------------------------
    // Begin top-level JSON object
    //
    // {
    //   "side": "R",
    //   "original": {
    // --------------------------------------------------

    sendRawChunk("{\"side\":\"R\",\"original\":{\"IMU 1\":[");


    // --------------------------------------------------
    // Loop through swingBuffer from 0 to sampleCount.
    //
    // IMU 1 = Forearm IMU
    //
    // Each pass:
    // 1. Clear the small local JsonDocument
    // 2. Map one forearm sample
    // 3. Serialize directly into the client socket
    // --------------------------------------------------

    for (int i = 0; i < sampleCount; i++) {
        // Clear all data from the previous sample.
        sampleDocument.clear();


        // --------------------------------------------------
        // Timestamp
        //
        // ArmSegmentState stores milliseconds since boot.
        // Divide by 1000 to transmit seconds.
        // --------------------------------------------------

        sampleDocument["timestamp_s"] =
            swingBuffer[i].forearm.timestamp / 1000.0;


        // --------------------------------------------------
        // Absolute/raw accelerometer values
        // Units: m/s^2
        // --------------------------------------------------

        sampleDocument["accel_mps2"]["x"] =
            swingBuffer[i].forearm.absoluteAccel.x;

        sampleDocument["accel_mps2"]["y"] =
            swingBuffer[i].forearm.absoluteAccel.y;

        sampleDocument["accel_mps2"]["z"] =
            swingBuffer[i].forearm.absoluteAccel.z;


        // --------------------------------------------------
        // Gyroscope values
        // Units: rad/s
        // --------------------------------------------------

        sampleDocument["gyro_rads"]["x"] =
            swingBuffer[i].forearm.angularVelocity.x;

        sampleDocument["gyro_rads"]["y"] =
            swingBuffer[i].forearm.angularVelocity.y;

        sampleDocument["gyro_rads"]["z"] =
            swingBuffer[i].forearm.angularVelocity.z;


        // --------------------------------------------------
        // Quaternion orientation
        // Format: w, x, y, z
        // --------------------------------------------------

        sampleDocument["quaternion_wxyz"]["w"] =
            swingBuffer[i].forearm.orientation.w;

        sampleDocument["quaternion_wxyz"]["x"] =
            swingBuffer[i].forearm.orientation.x;

        sampleDocument["quaternion_wxyz"]["y"] =
            swingBuffer[i].forearm.orientation.y;

        sampleDocument["quaternion_wxyz"]["z"] =
            swingBuffer[i].forearm.orientation.z;


        // --------------------------------------------------
        // Relative/linear acceleration
        // Gravity has been removed
        // Units: m/s^2
        // --------------------------------------------------

        sampleDocument["linear_accel_mps2"]["x"] =
            swingBuffer[i].forearm.relativeAccel.x;

        sampleDocument["linear_accel_mps2"]["y"] =
            swingBuffer[i].forearm.relativeAccel.y;

        sampleDocument["linear_accel_mps2"]["z"] =
            swingBuffer[i].forearm.relativeAccel.z;


        // --------------------------------------------------
        // Gravity vector
        // Units: m/s^2
        // --------------------------------------------------

        sampleDocument["gravity_mps2"]["x"] =
            swingBuffer[i].forearm.gravityVector.x;

        sampleDocument["gravity_mps2"]["y"] =
            swingBuffer[i].forearm.gravityVector.y;

        sampleDocument["gravity_mps2"]["z"] =
            swingBuffer[i].forearm.gravityVector.z;


        // --------------------------------------------------
        // Add a comma before every sample except the first.
        //
        // JSON arrays require:
        // {...},{...},{...}
        // --------------------------------------------------

        if (i > 0) {
            sendRawChunk(",");
        }


        // --------------------------------------------------
        // Serialize the single forearm sample directly down
        // into the client socket pipe.
        // --------------------------------------------------

        sendJsonChunk(sampleDocument);
    }


    // --------------------------------------------------
    // Close IMU 1 array and begin IMU 2 array
    // --------------------------------------------------

    sendRawChunk("],\"IMU 2\":[");


    // --------------------------------------------------
    // Loop through swingBuffer from 0 to sampleCount.
    //
    // IMU 2 = Bicep / Upper Arm IMU
    // --------------------------------------------------

    for (int i = 0; i < sampleCount; i++) {
        // Clear all data from the previous sample.
        sampleDocument.clear();


        // --------------------------------------------------
        // Timestamp in seconds
        // --------------------------------------------------

        sampleDocument["timestamp_s"] =
            swingBuffer[i].bicep.timestamp / 1000.0;


        // --------------------------------------------------
        // Absolute/raw accelerometer values
        // Units: m/s^2
        // --------------------------------------------------

        sampleDocument["accel_mps2"]["x"] =
            swingBuffer[i].bicep.absoluteAccel.x;

        sampleDocument["accel_mps2"]["y"] =
            swingBuffer[i].bicep.absoluteAccel.y;

        sampleDocument["accel_mps2"]["z"] =
            swingBuffer[i].bicep.absoluteAccel.z;


        // --------------------------------------------------
        // Gyroscope values
        // Units: rad/s
        // --------------------------------------------------

        sampleDocument["gyro_rads"]["x"] =
            swingBuffer[i].bicep.angularVelocity.x;

        sampleDocument["gyro_rads"]["y"] =
            swingBuffer[i].bicep.angularVelocity.y;

        sampleDocument["gyro_rads"]["z"] =
            swingBuffer[i].bicep.angularVelocity.z;


        // --------------------------------------------------
        // Quaternion orientation
        // Format: w, x, y, z
        // --------------------------------------------------

        sampleDocument["quaternion_wxyz"]["w"] =
            swingBuffer[i].bicep.orientation.w;

        sampleDocument["quaternion_wxyz"]["x"] =
            swingBuffer[i].bicep.orientation.x;

        sampleDocument["quaternion_wxyz"]["y"] =
            swingBuffer[i].bicep.orientation.y;

        sampleDocument["quaternion_wxyz"]["z"] =
            swingBuffer[i].bicep.orientation.z;


        // --------------------------------------------------
        // Relative/linear acceleration
        // Gravity has been removed
        // Units: m/s^2
        // --------------------------------------------------

        sampleDocument["linear_accel_mps2"]["x"] =
            swingBuffer[i].bicep.relativeAccel.x;

        sampleDocument["linear_accel_mps2"]["y"] =
            swingBuffer[i].bicep.relativeAccel.y;

        sampleDocument["linear_accel_mps2"]["z"] =
            swingBuffer[i].bicep.relativeAccel.z;


        // --------------------------------------------------
        // Gravity vector
        // Units: m/s^2
        // --------------------------------------------------

        sampleDocument["gravity_mps2"]["x"] =
            swingBuffer[i].bicep.gravityVector.x;

        sampleDocument["gravity_mps2"]["y"] =
            swingBuffer[i].bicep.gravityVector.y;

        sampleDocument["gravity_mps2"]["z"] =
            swingBuffer[i].bicep.gravityVector.z;


        // --------------------------------------------------
        // Add commas between JSON array elements.
        // --------------------------------------------------

        if (i > 0) {
            sendRawChunk(",");
        }


        // --------------------------------------------------
        // Serialize the single bicep sample directly down
        // into the client socket pipe.
        // --------------------------------------------------

        sendJsonChunk(sampleDocument);
    }


    // --------------------------------------------------
    // Close the "original" IMU arrays.
    //
    // Add the body measurements from the provided
    // JSON format.
    // --------------------------------------------------

    sendRawChunk(
        "]},"
        "\"body\":{"
        "\"upper_arm_length_m\":0.30,"
        "\"forearm_length_m\":0.27"
        "},"
    );


    // --------------------------------------------------
    // Preprocessing is performed after the raw IMU data
    // reaches the laptop.
    //
    // Keep the same top-level JSON format from message.txt.
    // The ESP32 does not calculate preprocessing frames or
    // the final motion profile here.
    // --------------------------------------------------

    sendRawChunk(
        "\"preprocessing\":{"
        "\"frames\":[],"
        "\"motion_profile\":{}"
        "},"
    );


    // --------------------------------------------------
    // Classification is performed by the laptop/model.
    //
    // Keep the classification object in the JSON structure,
    // but do not create fake model results on the ESP32.
    // --------------------------------------------------

    sendRawChunk(
        "\"classification\":{}"
        "}"
    );


    // --------------------------------------------------
    // Send final zero-length HTTP chunk.
    //
    // This tells the server that the chunked request body
    // is completely finished.
    // --------------------------------------------------

    client.print("0\r\n\r\n");


    // --------------------------------------------------
    // Read the HTTP response status from the laptop.
    // --------------------------------------------------

    unsigned long responseStartTime = millis();

    while (!client.available() &&
           client.connected() &&
           millis() - responseStartTime < 5000) {
        delay(1);
    }

    if (client.available()) {
        // Read the first HTTP response line.
        String responseLine = client.readStringUntil('\n');

        // Print the server response for debugging.
        Serial.print("Server Response: ");
        Serial.println(responseLine);
    } else {
        Serial.println("Transmission failed: No server response.");
    }


    // --------------------------------------------------
    // Close the network connection.
    // --------------------------------------------------

    client.stop();


    // --------------------------------------------------
    // Reset control variables back to clean baseline state
    // --------------------------------------------------

    sampleCount = 0;
    currentState = STATE_IDLE;
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