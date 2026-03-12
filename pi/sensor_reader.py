#!/usr/bin/env python3
"""
Nurture Baby Monitor — Real Sensor Reader
==========================================
Matches YOUR actual hardware wiring on Raspberry Pi 5:

  TCA9548A  I²C Mux   0x70   (smbus2 for channel switching)
  ├── CH 1: BME680    0x77   room temp, humidity, pressure, gas
  ├── CH 2: ADS1115   0x48
  │         ├── A0: MQ135   gas/air quality
  │         └── A1: MAX9814 microphone → cry detection
  ├── CH 3: MLX90614  0x5A   (if wired; skipped if not present)
  MH-Z19B   UART /dev/serial0, 9600 baud  (no mux needed)
  Buzzer    GPIO 17   active HIGH

Channels must be selected BEFORE accessing each sensor.
"""

import time

import smbus2
import board
import busio

# ─── I²C bus ─────────────────────────────────────────────────────────────────
_i2c   = busio.I2C(board.SCL, board.SDA)
_bus   = smbus2.SMBus(1)

MUX_ADDR = 0x70

# ─── Cry detection ───────────────────────────────────────────────────────────
CRY_THRESHOLD_RAW = 18000   # ~2.25V on MAX9814 — tune to your environment
CRY_SAMPLES       = 5
CRY_WINDOW_SEC    = 0.5


def _select_channel(ch: int):
    """Select TCA9548A channel (0–7). Call before every sensor access."""
    try:
        _bus.write_byte(MUX_ADDR, 1 << ch)
        time.sleep(0.05)
    except Exception as e:
        print(f"[mux] Channel {ch} select error: {e}")


# ─── BME680 on Mux Channel 1, address 0x77 ───────────────────────────────────
try:
    import adafruit_bme680
    _select_channel(1)
    _bme = adafruit_bme680.Adafruit_BME680_I2C(_i2c, address=0x77)
    _bme.sea_level_pressure = 1013.25
    _bme.filter_size = 3
    BME_OK = True
    print("[sensor] ✓ BME680 (ch1, 0x77)")
except Exception as e:
    _bme = None
    BME_OK = False
    print(f"[sensor] ✗ BME680: {e}")

# ─── ADS1115 on Mux Channel 2 (MQ135 A0, MAX9814 A1) ─────────────────────────
try:
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    _select_channel(2)
    _ads      = ADS.ADS1115(_i2c)
    _mq135    = AnalogIn(_ads, ADS.P0)   # MQ135  on A0
    _mic      = AnalogIn(_ads, ADS.P1)   # MAX9814 on A1
    ADS_OK    = True
    print("[sensor] ✓ ADS1115 (ch2) — MQ135 A0, MAX9814 A1")
except Exception as e:
    _ads   = None
    ADS_OK = False
    print(f"[sensor] ✗ ADS1115: {e}")

# ─── MLX90614 on Mux Channel 3, address 0x5A (optional) ─────────────────────
try:
    import adafruit_mlx90614
    _select_channel(3)
    _mlx   = adafruit_mlx90614.MLX90614(_i2c)
    MLX_OK = True
    print("[sensor] ✓ MLX90614 (ch3, 0x5A)")
except Exception as e:
    _mlx   = None
    MLX_OK = False
    print(f"[sensor] ✗ MLX90614 (optional): {e}")

# ─── MH-Z19B — UART (no mux, direct serial) ──────────────────────────────────
try:
    import mh_z19
    MHZ_OK = True
    print("[sensor] ✓ MH-Z19B (UART)")
except Exception as e:
    MHZ_OK = False
    print(f"[sensor] ✗ MH-Z19B: {e}")

# ─── Buzzer — GPIO 17 ────────────────────────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(17, GPIO.OUT, initial=GPIO.LOW)
    BUZZER_OK = True
    print("[sensor] ✓ Buzzer GPIO17")
except Exception as e:
    BUZZER_OK = False
    print(f"[sensor] ✗ Buzzer: {e}")


# ─── Buzzer helper ────────────────────────────────────────────────────────────

def buzz(duration_ms: int = 200):
    if not BUZZER_OK:
        return
    try:
        import RPi.GPIO as GPIO
        GPIO.output(17, GPIO.HIGH)
        time.sleep(duration_ms / 1000)
        GPIO.output(17, GPIO.LOW)
    except Exception as e:
        print(f"[buzzer] {e}")


# ─── Cry detection via MAX9814 (ADS1115 A1) ──────────────────────────────────

def _detect_cry() -> bool:
    """Sample mic CRY_SAMPLES times and return True if baby is likely crying."""
    if not ADS_OK:
        return False
    loud = 0
    _select_channel(2)
    for _ in range(CRY_SAMPLES):
        try:
            if abs(_mic.value) > CRY_THRESHOLD_RAW:
                loud += 1
        except Exception:
            pass
        time.sleep(CRY_WINDOW_SEC / CRY_SAMPLES)
    return loud >= (CRY_SAMPLES // 2 + 1)


# ─── Main public function ─────────────────────────────────────────────────────

def read_all() -> dict:
    """
    Read all sensors. Returns a dict matching the /api/status JSON schema.
    Compatible with your existing working script values.
    """
    data = {
        "active":       True,
        "body_temp":    0.0,   # MLX90614 object temp
        "ambient_temp": 0.0,   # MLX90614 ambient
        "room_temp":    0.0,   # BME680
        "humidity":     0,     # BME680
        "pressure":     0.0,   # BME680
        "co2_ppm":      0,     # MH-Z19B
        "gas_index":    0,     # BME680 gas + MQ135 combined
        "mq135_raw":    0,     # MQ135 raw ADC
        "cry_detected": False, # MAX9814
    }

    # ── BME680 (channel 1) ────────────────────────────────────────────────────
    if BME_OK:
        try:
            _select_channel(1)
            data["room_temp"] = round(_bme.temperature, 2)
            data["humidity"]  = int(_bme.relative_humidity)
            data["pressure"]  = round(_bme.pressure, 2)
            gas_r             = _bme.gas   # Ohms — higher = cleaner air
            # Convert: low resistance (bad air) → high gas_index
            data["gas_index"] = int(max(0, 300000 - gas_r)) if gas_r else 0
        except Exception as e:
            print(f"[sensor] BME680 read error: {e}")

    # ── ADS1115 (channel 2) — MQ135 + MAX9814 ────────────────────────────────
    if ADS_OK:
        try:
            _select_channel(2)
            mq_raw            = abs(_mq135.value)
            data["mq135_raw"] = mq_raw
            # gas_index: take the max of BME gas index and MQ135-derived value
            mq_index          = int((mq_raw / 32767) * 300000)
            data["gas_index"] = max(data["gas_index"], mq_index)
        except Exception as e:
            print(f"[sensor] MQ135 read error: {e}")

        # Cry detection (samples MAX9814 over CRY_WINDOW_SEC)
        try:
            data["cry_detected"] = _detect_cry()
        except Exception as e:
            print(f"[sensor] Cry detect error: {e}")

    # ── MLX90614 (channel 3 — optional) ──────────────────────────────────────
    if MLX_OK:
        try:
            _select_channel(3)
            data["body_temp"]    = round(_mlx.object_temperature, 2)
            data["ambient_temp"] = round(_mlx.ambient_temperature, 2)
        except Exception as e:
            print(f"[sensor] MLX90614 read error: {e}")

    # ── MH-Z19B UART — no mux needed ─────────────────────────────────────────
    if MHZ_OK:
        try:
            result = mh_z19.read_all()
            if result and "co2" in result:
                data["co2_ppm"] = int(result["co2"])
        except Exception as e:
            print(f"[sensor] MH-Z19B read error: {e}")

    return data


# ─── Standalone test (mirrors your existing terminal output) ──────────────────

if __name__ == "__main__":
    print("\n=== Nurture Sensor Test ===")
    print("Reading every 3 seconds — Ctrl+C to stop\n")
    try:
        while True:
            d = read_all()
            print("===== BME680 Environmental Sensor =====")
            print(f"Temperature:   {d['room_temp']} C")
            print(f"Humidity:      {d['humidity']} %")
            print(f"Pressure:      {d['pressure']} hPa")
            print(f"Gas Index:     {d['gas_index']}")
            print("\n===== Analog Sensors (ADS1115) =====")
            print(f"MQ135 Gas:     {d['mq135_raw']}")
            print(f"Cry Detected:  {'YES 🍼' if d['cry_detected'] else 'no'}")
            if MLX_OK:
                print(f"\n===== MLX90614 =====")
                print(f"Body Temp:     {d['body_temp']} C")
                print(f"Ambient Temp:  {d['ambient_temp']} C")
            if MHZ_OK:
                print(f"\n===== MH-Z19B =====")
                print(f"CO₂:           {d['co2_ppm']} ppm")
            print("\n--------------------------------------")
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nDone.")
