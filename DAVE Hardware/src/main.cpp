#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>

Adafruit_MPU6050 mpuForearm;
Adafruit_MPU6050 mpuUpperArm;


void setup() {
    Serial.begin(115200);
    
    // Initialize Sensor 1 (AD0 Low)
    if (!mpuForearm.begin(0x68)) {
        Serial.println("Failed to find Forearm MPU6050 at 0x68!");
    }
    
    // Initialize Sensor 2 (AD0 High)
    if (!mpuUpperArm.begin(0x69)) {
        Serial.println("Failed to find Upper Arm MPU6050 at 0x69!");
    }
    
    Serial.println("Both sensors connected successfully!");
}

void loop() {
  // put your main code here, to run repeatedly:
}
