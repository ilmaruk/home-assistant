import unittest
from unittest.mock import MagicMock, patch

from homeassistant.components.sensor.sensehat import SenseHatSensor, _get_temperature_average, \
    _normalise_current_temperature, _get_cpu_temperature, _update_readings_history


class TestSenseHat(unittest.TestCase):

    def test_get_current_temperature_average(self) -> None:
        self.assertEqual(_get_temperature_average([20, None, 21.2, None, 22.4]), 21.2)

    def test_get_current_temperature_average_all_none(self) -> None:
        self.assertIsNone(_get_temperature_average([None, None, None]))

    @patch('os.popen')
    def test_get_cpu_temperature(self, mock_os_popen: MagicMock) -> None:
        mock_os_popen.return_value.readline.return_value = "temp=48.9'C\n"
        self.assertEqual(_get_cpu_temperature(), 48.9)

    @patch('os.popen')
    def test_normalise_current_temperature(self, mock_os_popen: MagicMock) -> None:
        mock_os_popen.return_value.readline.return_value = "temp=48.9'C\n"
        self.assertEqual(_normalise_current_temperature(34.5, hat_attached=True), 24.9)

    def test_normalise_current_temperature_no_temperature(self) -> None:
        self.assertIsNone(_normalise_current_temperature(None, hat_attached=False))

    def test_normalise_current_temperature_not_attached(self) -> None:
        self.assertEqual(_normalise_current_temperature(24.9, hat_attached=False), 24.9)

    def test_update_reading_history(self) -> None:
        history = []
        _update_readings_history(history, new_reading=23.4, max_history_size=5)
        self.assertEqual(history, [23.4])

    def test_update_reading_history_full(self) -> None:
        history = [10, 11, 12]
        _update_readings_history(history, new_reading=13, max_history_size=3)
        self.assertEqual(history, [11, 12, 13])

    def test_update_reading_history_overfull(self) -> None:
        history = [10, 11, 12, 13]
        _update_readings_history(history, new_reading=14, max_history_size=3)
        self.assertEqual(history, [12, 13, 14])


class TestSenseHatSensor(unittest.TestCase):
    """Test the SenseHAT sensor."""

    def setUp(self):
        super().setUp()
        self._sense_hat = MagicMock()

    def test_update_humidity(self):
        self._test_update('humidity', 56.7)

    def test_failed_update_humidity(self):
        self._test_update('humidity', None)

    def test_update_pressure(self):
        self._test_update('pressure', 1234.5)

    def test_failed_update_pressure(self):
        self._test_update('pressure', None)

    def test_update_temperature(self):
        self._sense_hat.get_temperature_from_humidity.return_value = 19.5
        self._sense_hat.get_temperature_from_pressure.return_value = 21.5
        sut = self._make_sut('temperature')
        sut.update()
        self.assertEqual(sut.state, 20.5)

    def test_update_temperature_only_from_humidity(self):
        self._sense_hat.get_temperature_from_humidity.return_value = 19.5
        self._sense_hat.get_temperature_from_pressure.return_value = None
        sut = self._make_sut('temperature')
        sut.update()
        self.assertEqual(sut.state, 19.5)

    def test_update_temperature_only_from_pressure(self):
        self._sense_hat.get_temperature_from_humidity.return_value = None
        self._sense_hat.get_temperature_from_pressure.return_value = 21.5
        sut = self._make_sut('temperature')
        sut.update()
        self.assertEqual(sut.state, 21.5)

    def test_update_temperature_no_readings_no_history(self):
        self._sense_hat.get_temperature_from_humidity.return_value = None
        self._sense_hat.get_temperature_from_pressure.return_value = None
        sut = self._make_sut('temperature')
        sut.update()
        self.assertIsNone(sut.state)

    def test_update_temperature_no_readings_with_history(self):
        sut = self._make_sut('temperature')
        self._sense_hat.get_temperature_from_humidity.return_value = 20
        self._sense_hat.get_temperature_from_pressure.return_value = 21
        sut.update()
        self.assertEqual(sut.state, 20.5)
        self._sense_hat.get_temperature_from_humidity.return_value = None
        self._sense_hat.get_temperature_from_pressure.return_value = None
        sut.update()
        self.assertEqual(sut.state, 20.5)

    def _test_update(self, sensor_type, reading_value):
        getattr(self._sense_hat, "get_{}".format(sensor_type)).return_value = reading_value
        sut = self._make_sut(sensor_type)
        sut.update()
        self.assertEqual(sut.state, reading_value)

    def _make_sut(self, sensor_type: str) -> SenseHatSensor:
        # hat_attached=False so that temperature is not affected by the CPU temperature
        return SenseHatSensor(self._sense_hat, hat_attached=False, sensor_type=sensor_type)