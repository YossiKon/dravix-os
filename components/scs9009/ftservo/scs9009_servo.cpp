#include "scs9009_servo.h"


namespace esphome::scs9009 {

static const char *TAG = "ftservo.scs9009";

void SCS9009Servo::setup() {
  ESP_LOGD(TAG, "Setting up servo %d", this->addr_);
  // dravix: the one line that proves THIS driver (not the BSP's) is compiled in
  ESP_LOGI(TAG, "dravix non-blocking servo driver (vendored + patched) for servo %d", this->addr_);

  // dravix: ready as soon as it answers; otherwise ask again every 5 s and never give up. The stock
  // driver marked the servo failed after one retry: a software restart (a tile change, private
  // mode) that caught the servo mid-packet or before its power was back left the head ignoring
  // every move until a power cycle (2026-11-27).
  if ( this->parent_->ping(this->addr_) != -1 ) {
    this->servo_ready_ = true;
    return;
  }
  this->status_set_warning(LOG_STR("Initial ping with servo failed, asking again every 5 s"));
  this->set_interval("ping_check", 5000, [this]() {
    if ( this->parent_->ping(this->addr_) != -1 ) {
      this->servo_ready_ = true; // mark servo ready
      ESP_LOGI(TAG, "Servo %d is ready", this->addr_);
      this->status_clear_warning();
      this->cancel_interval("ping_check");
    }
  });

}

void SCS9009Servo::loop() {

}

bool SCS9009Servo::read_torque_enable() {
  int ret = this->parent_->read_torque_enable(this->addr_);
  return static_cast<bool>(ret);
}

void SCS9009Servo::write_torque_enable(bool enable) {
  this->parent_->enable_torque(this->addr_, enable);
}


bool SCS9009Servo::read_sensor_value(ftservo::ServoSensorField field, int &value) {
  switch (field) {
    case ftservo::ServoSensorField::POSITION:
      value = this->parent_->read_pos(this->addr_);
      return true;
    case ftservo::ServoSensorField::SPEED:
      value = this->parent_->read_speed(this->addr_);
      return true;
    case ftservo::ServoSensorField::LOAD:
      value = this->parent_->read_load(this->addr_);
      return true;
    case ftservo::ServoSensorField::VOLTAGE:
      value = this->parent_->read_voltage(this->addr_);
      return true;
    case ftservo::ServoSensorField::CURRENT:
      value = this->parent_->read_current(this->addr_);
      return true;
    case ftservo::ServoSensorField::TEMPERATURE:
      value = this->parent_->read_temperature(this->addr_);
      return true;
    default:
      return false;
  }
}


void SCS9009Servo::move(int position, uint16_t time, uint16_t speed) {
  if (!this->servo_ready_) {
    return;
  }

  this->parent_->write_pos(this->addr_, position, time, speed);
  // dravix: the stock driver slept 200 ms here on every move, in the main loop. Gone.
}

// dravix: the stock driver slept in the main loop until the servo had finished travelling
// and only then released its torque. A Component can schedule that instead — the loop stays
// free (microphone audio, the speaker, the API all live there). A second move before the
// first has settled simply pushes the release back (same timeout name = replaced).
void SCS9009Servo::release_torque_after(uint32_t ms) {
  if (this->keep_torque_) {            // dravix: this servo holds (the head's tilt)
    this->cancel_timeout("ft_torque_off");
    return;
  }
  this->set_timeout("ft_torque_off", ms, [this]() { this->write_torque_enable(false); });
}


}  // namespace esphome::scs9009
