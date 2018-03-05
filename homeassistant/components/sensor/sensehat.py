"""
Support for Sense HAT sensors.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/sensor.sensehat
"""
import os
import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (TEMP_CELSIUS, CONF_DISPLAY_OPTIONS, CONF_NAME)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

REQUIREMENTS = ['sense-hat==2.2.0']

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'sensehat'
CONF_IS_HAT_ATTACHED = 'is_hat_attached'
CONF_TEMPERATURE_FROM_SENSOR = 'temperature_from_sensor'

HUMIDITY_SENSOR = 'humidity'
PRESSURE_SENSOR = 'pressure'
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)
MAX_READING_HISTORY_SIZE = 5

SENSOR_TYPES = {
    'temperature': ['temperature', TEMP_CELSIUS],
    'humidity': ['humidity', '%'],
    'pressure': ['pressure', 'mb'],
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DISPLAY_OPTIONS, default=SENSOR_TYPES.keys()):
        [vol.In(SENSOR_TYPES)],
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_IS_HAT_ATTACHED, default=True): cv.boolean,
    vol.Optional(CONF_TEMPERATURE_FROM_SENSOR, default='both'): cv.string,
})


class GenericSensor(Entity):

    def __init__(self, sense_hat, name, unit_of_measurement):
        self._sense_hat = sense_hat
        self._name = name
        self._unit_of_measurement = unit_of_measurement
        self._state = None

    def update(self):
        raise NotImplementedError

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._unit_of_measurement

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state


class HumiditySensor(GenericSensor):

    def __init__(self, sense_hat):
        super().__init__(sense_hat, 'humidity', '%')

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        self._state = self._sense_hat.get_humidity()


class PressureSensor(GenericSensor):

    def __init__(self, sense_hat):
        super().__init__(sense_hat, 'pressure', 'mb')

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        self._state = self._sense_hat.get_pressure()


class TemperatureSensor(GenericSensor):

    def __init__(self, sense_hat, from_sensor, is_attached):
        super().__init__(sense_hat, 'temperature', TEMP_CELSIUS)
        self._from_sensor = from_sensor
        self._is_attached = is_attached
        self._readings_history = []

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        temperature = self._get_temperature()

        # If the SenseHAT is attached, we need to consider the CPU temperature
        temperature = _normalise_current_temperature(temperature,
                                                     self._is_attached)

        # Keep the reading history up to date with the raw values
        _update_readings_history(self._readings_history, temperature,
                                 MAX_READING_HISTORY_SIZE)

        # Return the average of the reading history
        self._state = sum(self._readings_history) / len(self._readings_history)

    def _get_temperature(self):
        if self._from_sensor == 'humidity':
            temperature = self._sense_hat.get_temperature_from_humidity()
        elif self._from_sensor == 'pressure':
            temperature = self._sense_hat.get_temperature_from_pressure()
        else:
            temperature = (self._sense_hat.get_temperature_from_humidity() +
                           self._sense_hat.get_temperature_from_pressure()) / 2

        return temperature


def _sensor_factory(config, sensor_type, sense_hat):
    """Instantiate an instance of the required sensor class."""
    if sensor_type == 'humidity':
        return HumiditySensor(sense_hat)
    elif sensor_type == 'pressure':
        return PressureSensor(sense_hat)
    elif sensor_type == 'temperature':
        return TemperatureSensor(sense_hat,
                                 config[CONF_TEMPERATURE_FROM_SENSOR],
                                 config[CONF_IS_HAT_ATTACHED])
    else:
        return None


def setup_platform(_, config, add_devices, __=None):
    """Set up the Sense HAT sensor platform."""
    from sense_hat import SenseHat
    devices = []
    for sensor_type in config[CONF_DISPLAY_OPTIONS]:
        sensor = _sensor_factory(config, sensor_type, SenseHat())
        if sensor is not None:
            devices.append(sensor)

    add_devices(devices, True)


def _get_cpu_temperature():
    """Get the CPU temperature."""
    cpu_temperature_info = os.popen("vcgencmd measure_temp").readline()
    print(cpu_temperature_info)
    return float(cpu_temperature_info.replace("temp=", "").replace("'C\n", ""))


def _normalise_current_temperature(temperature, hat_attached):
    """If the SenseHAT is attached to the Pi, its temperature is
    affected by the CPU temperature and therefore we need to normalise
    the physical sensor readings.
    """
    if temperature is None or not hat_attached:
        return temperature

    cpu_temperature = _get_cpu_temperature()
    return temperature - ((cpu_temperature - temperature) / 1.5)


def _update_readings_history(readings_history, new_reading, max_history_size):
    """Make sure a readings history doesn't overflow."""
    readings_history.append(new_reading)
    if len(readings_history) > max_history_size:
        for _ in range(len(readings_history) - max_history_size):
            readings_history.pop(0)
