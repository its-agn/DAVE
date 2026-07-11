#include "ImuManager.h"

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>

namespace {
constexpr float GRAVITY_MPS2 = 9.80665f;
constexpr float FILTER_SAMPLE_RATE_HZ = 100.0f;

// Hamilton product: returns q1 * q2 (w, x, y, z convention)
Quaternion4D quaternionMultiply(const Quaternion4D& q1, const Quaternion4D& q2) {
    Quaternion4D result;
    result.w = q1.w * q2.w - q1.x * q2.x - q1.y * q2.y - q1.z * q2.z;
    result.x = q1.w * q2.x + q1.x * q2.w + q1.y * q2.z - q1.z * q2.y;
    result.y = q1.w * q2.y - q1.x * q2.z + q1.y * q2.w + q1.z * q2.x;
    result.z = q1.w * q2.z + q1.x * q2.y - q1.y * q2.x + q1.z * q2.w;
    return result;
}
}

// Constructor
IMUManager::IMUManager(uint8_t i2cAddress)
    : _address(i2cAddress),
      _lastUpdateTime(0),
      _currentState{},
      _lastAngularVelocity{0.0f, 0.0f, 0.0f},
      _gyroBias{0.0f, 0.0f, 0.0f},
      _referenceOrientationInverse{1.0f, 0.0f, 0.0f, 0.0f},
      _isCalibrated(false) {
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
    // Raw gyroscope data in rad/s, with stationary bias
    // (estimated during calibrate()) removed
    // -------------------------------------------------

    _currentState.angularVelocity.x = gyro.gyro.x - _gyroBias.x;
    _currentState.angularVelocity.y = gyro.gyro.y - _gyroBias.y;
    _currentState.angularVelocity.z = gyro.gyro.z - _gyroBias.z;


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
    // Convert bias-corrected gyro from rad/s to deg/s
    // for Mahony filter
    // -------------------------------------------------
    
    const float gyroXDeg =
        _currentState.angularVelocity.x * SENSORS_RADS_TO_DPS;

    const float gyroYDeg =
        _currentState.angularVelocity.y * SENSORS_RADS_TO_DPS;

    const float gyroZDeg =
        _currentState.angularVelocity.z * SENSORS_RADS_TO_DPS;


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
    // Zero orientation relative to the calibration pose
    // so every run starts from the same reported
    // orientation, regardless of how the arm was
    // physically pointed during calibrate()
    // -------------------------------------------------

    if (_isCalibrated) {
        _currentState.orientation = quaternionMultiply(
            _referenceOrientationInverse,
            _currentState.orientation
        );
    }


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

// Blocking calibration: estimate gyro bias, let the filter settle onto
// gravity, then lock the current quaternion as the "zero" reference pose.
// Call this while the arm is held still in whatever pose you want every
// run to start from.
bool IMUManager::calibrate(uint16_t biasSampleCount, uint16_t settleTimeMs) {
    // -------------------------------------------------
    // 1. Gyro bias estimation
    // Average raw gyro readings while stationary so
    // angularVelocity (and its angularAccel derivative)
    // reads ~0 at rest instead of drifting.
    // -------------------------------------------------

    float sumX = 0.0f;
    float sumY = 0.0f;
    float sumZ = 0.0f;

    for (uint16_t i = 0; i < biasSampleCount; i++) {
        sensors_event_t accel;
        sensors_event_t gyro;
        sensors_event_t temp;

        if (!_mpu.getEvent(&accel, &gyro, &temp)) {
            return false;
        }

        sumX += gyro.gyro.x;
        sumY += gyro.gyro.y;
        sumZ += gyro.gyro.z;

        delay(5); // ~200 Hz sampling during calibration
    }

    _gyroBias.x = sumX / static_cast<float>(biasSampleCount);
    _gyroBias.y = sumY / static_cast<float>(biasSampleCount);
    _gyroBias.z = sumZ / static_cast<float>(biasSampleCount);

    // -------------------------------------------------
    // 2. Let the Mahony filter converge
    // The filter needs a bit of time to fuse gravity and
    // settle before its quaternion is trustworthy enough
    // to lock as the reference pose.
    // -------------------------------------------------

    _isCalibrated = false; // ensure update() doesn't try to zero against a stale reference while settling
    _lastUpdateTime = micros();

    const unsigned long settleStart = millis();
    while (millis() - settleStart < settleTimeMs) {
        update();
        delay(5);
    }

    // -------------------------------------------------
    // 3. Lock the current orientation as the zero pose
    // Store its conjugate (== inverse for a unit
    // quaternion) so future calls can rotate any
    // orientation into this pose's reference frame.
    // -------------------------------------------------

    const Quaternion4D q = _currentState.orientation;
    _referenceOrientationInverse = { q.w, -q.x, -q.y, -q.z };

    _isCalibrated = true;

    return true;
}