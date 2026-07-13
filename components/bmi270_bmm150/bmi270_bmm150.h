#pragma once

#include "esphome/core/component.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/i2c/i2c.h"

namespace esphome {
namespace bmi270_bmm150 {

class BMI270BMM150Sensor : public PollingComponent, public i2c::I2CDevice {
  public:
    enum imu_spec_t
    {
      imu_spec_none  = 0,
      imu_spec_accel = 0b0001,
      imu_spec_gyro  = 0b0010,
      imu_spec_mag   = 0b0100,
    };

    void setup() override;
    void dump_config() override;
    void update() override;
    float get_setup_priority() const override;

    void set_auxilliary_sensor_address(uint8_t aux_address) { this->auxilliary_sensor_address_ = aux_address; }

    void set_accel_x_sensor(sensor::Sensor *accel_x_sensor) { accel_x_sensor_ = accel_x_sensor; }
    void set_accel_y_sensor(sensor::Sensor *accel_y_sensor) { accel_y_sensor_ = accel_y_sensor; }
    void set_accel_z_sensor(sensor::Sensor *accel_z_sensor) { accel_z_sensor_ = accel_z_sensor; }
    void set_gyro_x_sensor(sensor::Sensor *gyro_x_sensor) { gyro_x_sensor_ = gyro_x_sensor; }
    void set_gyro_y_sensor(sensor::Sensor *gyro_y_sensor) { gyro_y_sensor_ = gyro_y_sensor; }
    void set_gyro_z_sensor(sensor::Sensor *gyro_z_sensor) { gyro_z_sensor_ = gyro_z_sensor; }
    void set_mag_x_sensor(sensor::Sensor *mag_x_sensor) { mag_x_sensor_ = mag_x_sensor; }
    void set_mag_y_sensor(sensor::Sensor *mag_y_sensor) { mag_y_sensor_ = mag_y_sensor; }
    void set_mag_z_sensor(sensor::Sensor *mag_z_sensor) { mag_z_sensor_ = mag_z_sensor; }
    void set_temperature_sensor(sensor::Sensor *temperature_sensor) { temperature_sensor_ = temperature_sensor; }

    imu_spec_t get_specification() const { return specification_; }


  protected:

    struct point3d_i16_t
    {
      union
      {
        int16_t value[3];
        struct
        {
          int16_t x;
          int16_t y;
          int16_t z;
        };
      } __attribute__((__packed__));
    };

    struct imu_raw_data_t
    {
      union
      {
        int16_t value[10] = { 0, };
        point3d_i16_t sensor[3];
        struct
        {
          point3d_i16_t accel;
          point3d_i16_t gyro;
          point3d_i16_t mag;
          int16_t temp;
        } __attribute__((__packed__));
      };
    };

    struct imu_3d_t
    {
      union
      {
        float value[3];
        struct
        {
          float x;
          float y;
          float z;
        };
      };
    };

    struct imu_data_t
    {
      union
      {
        float value[9];
        imu_3d_t sensor[3];
        struct
        {
          imu_3d_t accel;
          imu_3d_t gyro;
          imu_3d_t mag;
        };
      };
    };

    struct imu_convert_param_t
    {
        float accel_res = 8.0f / 32768.0f;
        float gyro_res = 2000.0f / 32768.0f;
        float mag_res = 10.0f * 4912.0f / 32768.0f;
        float temp_res = 1.0f / 512.0f;
        float temp_offset = 23.0f;
    };

    void internal_setup_(int stage, int retry = 1);
    void internal_setup_auxilliary_sensor_(int stage, int retry = 1);

    bool _upload_file(const uint8_t *config_data, size_t write_len);

    bool write_register_(uint8_t reg, const uint8_t *value, size_t len = 1);
    bool read_register_(uint8_t reg, uint8_t data);

    using StatusCallback = std::function<void(bool)>;
    void checkStatus(int retry = 1, StatusCallback callback = [](bool) {});

    imu_spec_t getImuRawData(imu_raw_data_t* data);
    void getImuData(imu_data_t* data);
    bool getTemp(float* t);

      
  private:

    sensor::Sensor *accel_x_sensor_{nullptr};
    sensor::Sensor *accel_y_sensor_{nullptr};
    sensor::Sensor *accel_z_sensor_{nullptr};
    sensor::Sensor *gyro_x_sensor_{nullptr};
    sensor::Sensor *gyro_y_sensor_{nullptr};
    sensor::Sensor *gyro_z_sensor_{nullptr};
    sensor::Sensor *mag_x_sensor_{nullptr};
    sensor::Sensor *mag_y_sensor_{nullptr};
    sensor::Sensor *mag_z_sensor_{nullptr};
    sensor::Sensor *temperature_sensor_{nullptr};

    bool setup_complete_{false};
    esphome::i2c::ErrorCode last_error_;

    imu_spec_t specification_{imu_spec_none};

    bool enable_auxilliary_sensor_{false};
    //TODO: Make configurable in component
    uint8_t auxilliary_sensor_address_{0x10};

    imu_raw_data_t raw_data_;
    imu_convert_param_t convert_param_;
};

}  // namespace bmi270_bmm150
}  // namespace esphome