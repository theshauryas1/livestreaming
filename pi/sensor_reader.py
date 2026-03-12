#!/usr/bin/env python3
"""
Nurture Baby Monitor — REAL Sensor Reader
==========================================
Reads from all physical sensors on Raspberry Pi 5:

  MLX90614  I²C 0x5A  → body temp, ambient temp
  BME680    I²C 0x76  → room temp, humidity, pressure, gas resistance
  MH-Z19B   UART      → CO₂ ppm
  ADS1115   I²C 0x48  → analog ADC
    └─ A0: MQ135      → gas/air quality index
    └─ A1: MAX9814    → microphone amplitude → cry detection
  Buzzer    GPIO 17   → alert output (optional)

Requirements (install with install_sensors.sh):
  pip3 install smbus2 adafruit-circuitpython-mlx90614
               adafruit-circuitpython-bme680
               adafruit-circuitpython-ads1x15
               mh-z19 RPi.GPIO

Usage (standalone test):
  python3 sensor_reader.py

Returns a dict compatible with /api/status JSON format.
"""

import time

# ─── I²C bus ─────────────────────────────────────────────────────────────────
try:
    import board
    import busio
    _i2c = busio.I2C(board.SCL, board.SDA)
    I2C_OK = True
except Exception as e:
    print(f"[sensor] I²C init failed: {e}")
    I2C_OK = False

# ─── MLX90614 — infrared body temperature (I²C 0x5A) ─────────────────────────
try:
    import adafruit_mlx90614
    _mlx = adafruit_mlx90614.MLX90614(_i2c) if I2C_OK else None
    MLX_OK = _mlx is not None
    if MLX_OK:
        print("[sensor] ✓ MLX90614 ready")
except Exception as e:
    _mlx = None
    MLX_OK = False
    print(f"[sensor] ✗ MLX90614: {e}")

# ─── BME680 — room temp, humidity, pressure, VOC (I²C 0x76) ──────────────────
try:
    import adafruit_bme680
    _bme = adafruit_bme680.Adafruit_BME680_I2C(_i2c, address=0x76) if I2C_OK else None
    if _bme:
        _bme.sea_level_pressure = 1013.25   # adjust for your altitude
        _bme.filter_size = 3
    BME_OK = _bme is not None
    if BME_OK:
        print("[sensor] ✓ BME680 ready")
except Exception as e:
    _bme = None
    BME_OK = False
    print(f"[sensor] ✗ BME680: {e}")

# ─── MH-Z19B — CO₂ sensor (UART /dev/serial0, 9600 baud) ────────────────────
try:
    import mh_z19
    MHZ_OK = True
    print("[sensor] ✓ MH-Z19B ready")
except Exception as e:
    MHZ_OK = False
    print(f"[sensor] ✗ MH-Z19B: {e}")

# ─── ADS1115 — ADC for MQ135 (A0) and MAX9814 (A1) (I²C 0x48) ──────────────
try:
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    _ads = ADS.ADS1115(_i2c, address=0x48) if I2C_OK else None
    if _ads:
        _chan_mq135  = AnalogIn(_ads, ADS.P0)   # MQ135 on A0
        _chan_mic    = AnalogIn(_ads, ADS.P1)   # MAX9814 on A1
    ADS_OK = _ads is not None
    if ADS_OK:
        print("[sensor] ✓ ADS1115 ready (MQ135 A0, MAX9814 A1)")
except Exception as e:
    _ads = None
    ADS_OK = False
    print(f"[sensor] ✗ ADS1115: {e}")

# ─── Buzzer — GPIO 17 (optional) ─────────────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(17, GPIO.OUT, initial=GPIO.LOW)
    BUZZER_OK = True
    print("[sensor] ✓ Buzzer GPIO17 ready")
except Exception as e:
    BUZZER_OK = False
    print(f"[sensor] ✗ Buzzer: {e}")

# ─── Cry detection calibration ───────────────────────────────────────────────
# Adjust CRY_THRESHOLD based on your environment.
# MAX9814 output: ~1.25V quiet, spikes to ~2.5V on loud sounds.
# ADS1115 at 3.3V reference: values 0–26400 ≈ 0–3.3V (16-bit, GAIN=1)
CRY_THRESHOLD_RAW = 18000   # ~2.25V — tune this

# How many consecutive loud samples = cry
CRY_SAMPLES    = 5
CRY_WINDOW_SEC = 0.5
_cry_ring = []   # rolling window of mic readings


def _sample_mic_for_cry() -> bool:
    """Sample MAX9814 multiple times over CRY_WINDOW_SEC and decide if crying."""
    global _cry_ring
    if not ADS_OK:
        return False
    readings = []
    for _ in range(CRY_SAMPLES):
        try:
            readings.append(abs(_chan_mic.value))
        except Exception:
            pass
        time.sleep(CRY_WINDOW_SEC / CRY_SAMPLES)
    loud = sum(1 for v in readings if v > CRY_THRESHOLD_RAW)
    # Crying = majority of samples loud
    return loud >= (CRY_SAMPLES // 2 + 1)


# ─── Buzzer helpers ───────────────────────────────────────────────────────────

def buzz(duration_ms: int = 200):
    """Beep the buzzer for duration_ms milliseconds."""
    if not BUZZER_OK:
        return
    try:
        import RPi.GPIO as GPIO
        GPIO.output(17, GPIO.HIGH)
        time.sleep(duration_ms / 1000)
        GPIO.output(17, GPIO.LOW)
    except Exception as e:
        print(f"[buzzer] Error: {e}")


# ─── Public read function ─────────────────────────────────────────────────────

def read_all() -> dict:
    """
    Read all sensors and return a dict matching /api/status JSON schema.
    Falls back to 0.0 / False if a sensor is unavailable.
    """
    data = {
        "active":       True,
        "body_temp":    0.0,
        "ambient_temp": 0.0,
        "room_temp":    0.0,
        "humidity":     0,
        "pressure":     0.0,
        "co2_ppm":      0,
        "gas_index":    0,
        "mq135_raw":    0,
        "cry_detected": False,
    }

    # MLX90614 ──────────────────────────────────────────────────────
    if MLX_OK:
        try:
            data["body_temp"]    = round(_mlx.object_temperature, 2)
            data["ambient_temp"] = round(_mlx.ambient_temperature, 2)
        except Exception as e:
            print(f"[sensor] MLX90614 read error: {e}")

    # BME680 ────────────────────────────────────────────────────────
    if BME_OK:
        try:
            data["room_temp"] = round(_bme.temperature, 2)
            data["humidity"]  = int(_bme.relative_humidity)
            data["pressure"]  = round(_bme.pressure, 2)
            gas_raw           = _bme.gas              # Ω resistance
            # Convert gas resistance to a 0–500000 index (higher = worse air)
            # Lower resistance = more VOCs = higher index
            data["gas_index"] = int(max(0, 500000 - gas_raw)) if gas_raw else 0
        except Exception as e:
            print(f"[sensor] BME680 read error: {e}")

    # MH-Z19B ───────────────────────────────────────────────────────
    if MHZ_OK:
        try:
            result = mh_z19.read_all()
            if result and "co2" in result:
                data["co2_ppm"] = int(result["co2"])
        except Exception as e:
            print(f"[sensor] MH-Z19B read error: {e}")

    # MQ135 via ADS1115 A0 ──────────────────────────────────────────
    if ADS_OK:
        try:
            mq_raw            = abs(_chan_mq135.value)
            data["mq135_raw"] = mq_raw
            # gas_index: scale ADC 0-32767 → 0-300000 range
            data["gas_index"] = max(data["gas_index"], int((mq_raw / 32767) * 300000))
        except Exception as e:
            print(f"[sensor] MQ135/ADS1115 A0 read error: {e}")

    # MAX9814 via ADS1115 A1 — cry detection ────────────────────────
    try:
        data["cry_detected"] = _sample_mic_for_cry()
    except Exception as e:
        print(f"[sensor] MAX9814/cry read error: {e}")

    return data


# ─── Standalone test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== Nurture Sensor Test ===")
    print("Reading sensors every 2 seconds. Press Ctrl+C to stop.\n")
    try:
        while True:
            d = read_all()
            print(
                f"Body:{d['body_temp']:.1f}°C  "
                f"Ambient:{d['ambient_temp']:.1f}°C  "
                f"Room:{d['room_temp']:.1f}°C  "
                f"Hum:{d['humidity']}%  "
                f"Pres:{d['pressure']:.0f}hPa  "
                f"CO₂:{d['co2_ppm']}ppm  "
                f"Gas:{d['gas_index']}  "
                f"Cry:{'YES 🍼' if d['cry_detected'] else 'no'}"
            )
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nDone.")
