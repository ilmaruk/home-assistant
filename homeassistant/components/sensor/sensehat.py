"""
Support for Sense HAT sensors.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/sensor.sensehat
"""
import os
import logging
from datetime import timedelta

import typing
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

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

MAX_READING_HISTORY_SIZE = 5

SENSOR_TYPES = {
    'temperature': ['temperature', TEMP_CELSIUS],
    'humidity': ['humidity', '%'],
    'pressure': ['pressure', 'mb'],
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DISPLAY_OPTIONS, default=list(SENSOR_TYPES)):
        [vol.In(SENSOR_TYPES)],
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_IS_HAT_ATTACHED, default=True): cv.boolean
})


def setup_platform(_, config, add_devices, __=None) -> None:
    """Set up the Sense HAT sensor platform."""
    from sense_hat import SenseHat
    dev = []
    for sensor_type in config[CONF_DISPLAY_OPTIONS]:
        dev.append(SenseHatSensor(SenseHat(), CONF_IS_HAT_ATTACHED, sensor_type))

    add_devices(dev, True)


def _get_temperature_average(readings: typing.List[typing.Optional[float]]) -> typing.Optional[float]:
    """"Given a list of temperature readings, work out the average temperature, excluding None's."""
    valid_readings: typing.List[float] = [r for r in readings if r is not None]
    if len(valid_readings) == 0:
        return None
    return sum(valid_readings) / len(valid_readings)


def _get_cpu_temperature() -> float:
    """Get the CPU temperature."""
    cpu_temperature_info = os.popen("vcgencmd measure_temp").readline()
    print(cpu_temperature_info)
    return float(cpu_temperature_info.replace("temp=", "").replace("'C\n", ""))


def _normalise_current_temperature(temperature: typing.Optional[float], hat_attached: bool) -> typing.Optional[float]:
    """If the SenseHAT is attached to the Pi, its temperature is affected by the CPU
    temperature and therefore we need to normalise the physical sensor readings."""
    if temperature is None or not hat_attached:
        # The SenseHAT is not attached, so we're good with the temperature reported by the physical sensors
        return temperature

    cpu_temperature = _get_cpu_temperature()
    return temperature - ((cpu_temperature - temperature) / 1.5)


def _update_readings_history(readings_history: typing.List[typing.Optional[float]], new_reading: typing.Optional[float],
                             max_history_size: int=MAX_READING_HISTORY_SIZE) -> None:
    readings_history.append(new_reading)
    if len(readings_history) > max_history_size:
        for _ in range(len(readings_history) - max_history_size):
            readings_history.pop(0)


class SenseHatSensor(Entity):
    """Representation of a SenseHAT sensor."""

    def __init__(self, sense_hat: 'SenseHat', hat_attached: bool, sensor_type: str) -> None:
        """Initialize the sensor."""
        self._sense_hat = sense_hat
        self._hat_attached = hat_attached
        self._type = sensor_type
        self._name = SENSOR_TYPES[sensor_type][0]
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._state = None
        self._readings_history = list()

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self) -> typing.Optional[float]:
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit the value is expressed in."""
        return self._unit_of_measurement

    @property
    def humidity(self) -> typing.Optional[float]:
        return self._sense_hat.get_humidity()

    @property
    def pressure(self) -> typing.Optional[float]:
        return self._sense_hat.get_pressure()

    @property
    def temperature(self) -> typing.Optional[float]:
        # Use all the sensors that can report temperature
        temperature = _get_temperature_average([self._sense_hat.get_temperature_from_humidity(),
                                                self._sense_hat.get_temperature_from_pressure()])

        # If the SenseHAT is attached to the Pi, we need to consider the CPU temperature, too
        temperature = _normalise_current_temperature(temperature, self._hat_attached)

        # Keep the reading history up to date with the raw (not averaged) values
        _update_readings_history(self._readings_history, temperature)

        # Return the average of the reading history
        return _get_temperature_average(self._readings_history)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        self._state = getattr(self, self._type)

        if self._state is None:
            _LOGGER.warning("Unable to update {} sensor reading.".format(self._type))
