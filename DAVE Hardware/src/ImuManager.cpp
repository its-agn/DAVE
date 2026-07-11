#include "ImuManager.h"

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>

namespace {
constexpr float GRAVITY_MPS2 = 9.80665f;
constexpr float FILTER_SAMPLE_RATE_HZ = 100.0f;
}

// Constructor
IMUManager::IMUManager(uint8_t i2cAddress)
    : _address(i2cAddress),
      _lastUpdateTime(0),
      _currentState{},
      _lastAngularVelocity{0.0f, 0.0f, 0.0f} {
    _currentState.i2cAddress = _address;
}

// Initialize MPU6050 and Mahony filter
bool IMUManager::begin() {
    if (!_mpu.begin(_address, &Wire)) {
        return false;
    }

    _mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    _mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    _mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

    _filter.begin(FILTER_SAMPLE_RATE_HZ);

    _lastUpdateTime = micros();

    _currentState.timestamp = millis();
    _currentState.i2cAddress = _address;

    return true;
}

// Read one IMU sample and update the telemetry state
void IMUManager::update() {
    sensors_event_t accel;
    sensors_event_t gyro;
    sensors_event_t temp;

    if (!_mpu.getEvent(&accel, &gyro, &temp)) {
        return;
    }

    const uint32_t currentTime = micros();

    const float dt =
        static_cast<float>(currentTime - _lastUpdateTime) / 1000000.0f;

    _lastUpdateTime = currentTime;

    if (dt <= 0.0f) {
        return;
    }

    // -------------------------------------------------
    // Timestamp and I2C address
    // -------------------------------------------------

    _currentState.timestamp = millis();
    _currentState.i2cAddress = _address;


    // -------------------------------------------------
    // Absolute acceleration
    // Raw MPU6050 acceleration in m/s^2
    // -------------------------------------------------

    _currentState.absoluteAccel.x = accel.acceleration.x;
    _currentState.absoluteAccel.y = accel.acceleration.y;
    _currentState.absoluteAccel.z = accel.acceleration.z;


    // -------------------------------------------------
    // Angular velocity
    // Raw gyroscope data in rad/s
    // -------------------------------------------------

    _currentState.angularVelocity.x = gyro.gyro.x;
    _currentState.angularVelocity.y = gyro.gyro.y;
    _currentState.angularVelocity.z = gyro.gyro.z;


    // -------------------------------------------------
    // Angular acceleration
    // rad/s^2
    // -------------------------------------------------

    _currentState.angularAccel.x =
        (_currentState.angularVelocity.x -
         _lastAngularVelocity.x) / dt;

    _currentState.angularAccel.y =
        (_currentState.angularVelocity.y -
         _lastAngularVelocity.y) / dt;

    _currentState.angularAccel.z =
        (_currentState.angularVelocity.z -
         _lastAngularVelocity.z) / dt;

    _lastAngularVelocity = _currentState.angularVelocity;


    // -------------------------------------------------
    // Convert gyro from rad/s to deg/s for Mahony filter
    // -------------------------------------------------
    
    const float gyroXDeg =
        gyro.gyro.x * SENSORS_RADS_TO_DPS;

    const float gyroYDeg =
        gyro.gyro.y * SENSORS_RADS_TO_DPS;

    const float gyroZDeg =
        gyro.gyro.z * SENSORS_RADS_TO_DPS;


    // -------------------------------------------------
    // Update Mahony AHRS filter
    // -------------------------------------------------

    _filter.updateIMU(
        gyroXDeg,
        gyroYDeg,
        gyroZDeg,
        accel.acceleration.x,
        accel.acceleration.y,
        accel.acceleration.z,
        dt
    );


    // -------------------------------------------------
    // Quaternion orientation
    // w, x, y, z
    // -------------------------------------------------

    _filter.getQuaternion(
        &_currentState.orientation.w,
        &_currentState.orientation.x,
        &_currentState.orientation.y,
        &_currentState.orientation.z
    );


    // -------------------------------------------------
    // Gravity vector
    // -------------------------------------------------

    float gravityX;
    float gravityY;
    float gravityZ;

    _filter.getGravityVector(
        &gravityX,
        &gravityY,
        &gravityZ
    );

    // Convert gravity direction to m/s^2
    _currentState.gravityVector.x =
        gravityX * GRAVITY_MPS2;

    _currentState.gravityVector.y =
        gravityY * GRAVITY_MPS2;

    _currentState.gravityVector.z =
        gravityZ * GRAVITY_MPS2;


    // -------------------------------------------------
    // Relative acceleration
    //
    // Relative acceleration =
    // absolute acceleration - gravity
    // -------------------------------------------------

    _currentState.relativeAccel.x =
        _currentState.absoluteAccel.x -
        _currentState.gravityVector.x;

    _currentState.relativeAccel.y =
        _currentState.absoluteAccel.y -
        _currentState.gravityVector.y;

    _currentState.relativeAccel.z =
        _currentState.absoluteAccel.z -
        _currentState.gravityVector.z;


    // -------------------------------------------------
    // Position placeholder
    // -------------------------------------------------

    _currentState.position.x = 0.0f;
    _currentState.position.y = 0.0f;
    _currentState.position.z = 0.0f;
}