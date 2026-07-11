#ifndef DATA_STRUCTURES_H
#define DATA_STRUCTURES_H

#include <cstdint>

struct Vector3D {
    float x;
    float y;
    float z;
};

struct Quaternion4D {
    float w;
    float x;
    float y;
    float z;
};

// Unified telemetry payload for a single arm segment
struct ArmSegmentState {
    uint32_t timestamp;         // Milliseconds since boot
    uint8_t i2cAddress;         // 0x68 (Forearm) or 0x69 (Bicep)
    
    Vector3D absoluteAccel;    // Raw accelerometer data (m/s^2)
    Quaternion4D orientation;   // AHRS fused orientation
    Vector3D angularVelocity;   // Raw gyro data (rad/s)
    Vector3D angularAccel;      // Derived angular acceleration (rad/s^2)
    Vector3D relativeAccel;       // Accel minus gravity vector (m/s^2)
    Vector3D gravityVector;     // Extracted gravity direction
    Vector3D position;          // Experimental tracking placeholder
};

#endif // DATA_STRUCTURES_H