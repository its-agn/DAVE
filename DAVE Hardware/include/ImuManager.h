#ifndef IMU_MANAGER_H
#define IMU_MANAGER_H

#include <Adafruit_MPU6050.h>
#include <Adafruit_AHRS_Mahony.h>
#include "DataStructures.h"

class IMUManager {
private:
    Adafruit_MPU6050 _mpu;
    Adafruit_Mahony _filter; // Mahony is highly efficient on ESP32
    uint8_t _address;
    uint32_t _lastUpdateTime;
    
    ArmSegmentState _currentState;
    Vector3D _lastAngularVelocity;

public:
    // Constructor accepts the designated I2C address
    IMUManager(uint8_t i2cAddress);

    // Initializes the hardware and configures max ranges
    bool begin();

    // Runs a single step of the data retrieval and sensor fusion math
    void update();

    // Returns the completely populated telemetry state
    ArmSegmentState getState() const { return _currentState; }
};

#endif // IMU_MANAGER_H