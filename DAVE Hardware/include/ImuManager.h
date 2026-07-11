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

    // -------------------------------------------------
    // Calibration state
    // -------------------------------------------------
    Vector3D _gyroBias;                        // rad/s offset subtracted from every raw gyro sample
    Quaternion4D _referenceOrientationInverse;  // conjugate of the quaternion captured at calibration
    bool _isCalibrated;

public:
    // Constructor accepts the designated I2C address
    IMUManager(uint8_t i2cAddress);

    // Initializes the hardware and configures max ranges
    bool begin();

    // Runs a single step of the data retrieval and sensor fusion math
    void update();

    // Blocking calibration routine. Call this while the arm is held still
    // in the reference pose you want every run to start from.
    //
    // 1. Samples raw gyro for `biasSampleCount` readings to estimate the
    //    stationary gyro bias (removes drift in angularVelocity/angularAccel).
    // 2. Runs the Mahony filter for `settleTimeMs` so it converges onto
    //    gravity, then locks the resulting quaternion as the "zero" pose.
    //
    // After this call, getState().orientation will read (1,0,0,0) at the
    // calibration pose, and all future orientations are expressed relative
    // to it — so two separate runs that start with the same physical pose
    // will report the same starting orientation regardless of how the arm
    // happened to be oriented relative to the room.
    bool calibrate(uint16_t biasSampleCount = 200, uint16_t settleTimeMs = 2000);

    // Returns the completely populated telemetry state
    ArmSegmentState getState() const { return _currentState; }

    bool isCalibrated() const { return _isCalibrated; }
};

#endif // IMU_MANAGER_H