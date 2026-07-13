import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import i2c, sensor
from esphome.const import (
    CONF_ID,
    CONF_TEMPERATURE,
    CONF_ACCELERATION_X,
    CONF_ACCELERATION_Y,
    CONF_ACCELERATION_Z,
    CONF_GYROSCOPE_X,
    CONF_GYROSCOPE_Y,
    CONF_GYROSCOPE_Z,
    CONF_FIELD_STRENGTH_X,
    CONF_FIELD_STRENGTH_Y,
    CONF_FIELD_STRENGTH_Z,
    DEVICE_CLASS_TEMPERATURE,
    STATE_CLASS_MEASUREMENT,
    UNIT_METER_PER_SECOND_SQUARED,
    ICON_ACCELERATION_X,
    ICON_ACCELERATION_Y,
    ICON_ACCELERATION_Z,
    ICON_GYROSCOPE_X,
    ICON_GYROSCOPE_Y,
    ICON_GYROSCOPE_Z,
    ICON_MAGNET,
    UNIT_DEGREE_PER_SECOND,
    UNIT_CELSIUS,
    UNIT_MICROTESLA
)

DEPENDENCIES = ["i2c"]

bmi270_bmm150_ns = cg.esphome_ns.namespace("bmi270_bmm150")
BMI270BMM150Sensor = bmi270_bmm150_ns.class_(
    "BMI270BMM150Sensor", cg.PollingComponent, i2c.I2CDevice
)

accel_schema = {
    "unit_of_measurement": UNIT_METER_PER_SECOND_SQUARED,
    "accuracy_decimals": 2,
    "state_class": STATE_CLASS_MEASUREMENT,
}
gyro_schema = {
    "unit_of_measurement": UNIT_DEGREE_PER_SECOND,
    "accuracy_decimals": 2,
    "state_class": STATE_CLASS_MEASUREMENT,
}
mag_schema = {
    "unit_of_measurement": UNIT_MICROTESLA,
    "accuracy_decimals": 2,
    "state_class": STATE_CLASS_MEASUREMENT,
}

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(BMI270BMM150Sensor),
            cv.Optional(CONF_ACCELERATION_X): sensor.sensor_schema(
                icon=ICON_ACCELERATION_X,
                **accel_schema,
            ),
            cv.Optional(CONF_ACCELERATION_Y): sensor.sensor_schema(
                icon=ICON_ACCELERATION_Y,
                **accel_schema,
            ),
            cv.Optional(CONF_ACCELERATION_Z): sensor.sensor_schema(
                icon=ICON_ACCELERATION_Z,
                **accel_schema,
            ),
            cv.Optional(CONF_GYROSCOPE_X): sensor.sensor_schema(
                icon=ICON_GYROSCOPE_X,
                **gyro_schema,
            ),
            cv.Optional(CONF_GYROSCOPE_Y): sensor.sensor_schema(
                icon=ICON_GYROSCOPE_Y,
                **gyro_schema,
            ),
            cv.Optional(CONF_GYROSCOPE_Z): sensor.sensor_schema(
                icon=ICON_GYROSCOPE_Z,
                **gyro_schema,
            ),
            cv.Optional(CONF_FIELD_STRENGTH_X): sensor.sensor_schema(
                icon=ICON_MAGNET,
                **mag_schema,
            ),
            cv.Optional(CONF_FIELD_STRENGTH_Y): sensor.sensor_schema(
                icon=ICON_MAGNET,
                **mag_schema,
            ),
            cv.Optional(CONF_FIELD_STRENGTH_Z): sensor.sensor_schema(
                icon=ICON_MAGNET,
                **mag_schema,
            ),
            cv.Optional(CONF_TEMPERATURE): sensor.sensor_schema(
                unit_of_measurement=UNIT_CELSIUS,
                accuracy_decimals=0,
                device_class=DEVICE_CLASS_TEMPERATURE,
                state_class=STATE_CLASS_MEASUREMENT,
            ),
        }
    )
    .extend(cv.polling_component_schema("60s"))
    .extend(i2c.i2c_device_schema(0x68)) # 0x68 is the default address of the BMI270
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await i2c.register_i2c_device(var, config)

    for d in ["x", "y", "z"]:
        key = f"acceleration_{d}"
        if key in config:
          sens = await sensor.new_sensor(config[key])
          cg.add(getattr(var, f"set_accel_{d}_sensor")(sens))
        key = f"gyroscope_{d}"
        if key in config:
          sens = await sensor.new_sensor(config[key])
          cg.add(getattr(var, f"set_gyro_{d}_sensor")(sens))
        key = f"field_strength_{d}"
        if key in config:
          sens = await sensor.new_sensor(config[key])
          cg.add(getattr(var, f"set_mag_{d}_sensor")(sens))

    if CONF_TEMPERATURE in config:
      sens = await sensor.new_sensor(config[CONF_TEMPERATURE])
      cg.add(var.set_temperature_sensor(sens))