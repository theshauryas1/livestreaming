#!/usr/bin/env python3
"""
Nurture Baby Monitor — Real Sensor Reader
==========================================
Matches your actual hardware:

  TCA9548A  Mux  0x70  (smbus2)
  CH 1: BME680   0x77  temp, humidity, pressure, gas
  CH 2: ADS1115  0x48  → A0: MQ135, A1: MAX9814 mic
  CH 3: MLX90614 0x5A  body + ambient temp (optional)
  UART: MH-Z19B         CO₂ ppm (optional)
  GPIO17: Buzzer        alert output

Safe to import even if I²C bus is missing — all init wrapped in try/except.
"""

import time

# ─── I²C bus init (wrapped — never crashes import) ───────────────────────────
try:
    import board
    import busio
    _i2c = busio.I2C(board.SCL, board.SDA)
    I2C_OK = True
except Exception as e:
    _i2c = None
    I2C_OK = False
    print(f"[sensor] I²C init failed: {e}")

try:
    import smbus2
    _bus = smbus2.SMBus(1)
    BUS_OK = True
except Exception as e:
    _bus = None
    BUS_OK = False
    print(f"[sensor] smbus2 init failed: {e}")

MUX_ADDR = 0x70

def _mux_reset():
    """Disable ALL mux channels (write 0x00). Clears stuck bus state."""
    if not BUS_OK:
        return
    try:
        _bus.write_byte(MUX_ADDR, 0x00)
        time.sleep(0.1)
    except Exception:
        pass

def _select_channel(ch: int) -> bool:
    """Select TCA9548A channel 0-7. Returns False on failure."""
    if not BUS_OK:
        return False
    try:
        _bus.write_byte(MUX_ADDR, 1 << ch)
        time.sleep(0.1)   # longer delay = more reliable
        return True
    except Exception as e:
        print(f"[mux] ch{ch} error: {e}")
        _mux_reset()      # reset bus on any mux failure
        return False

# Reset mux at startup to clear any leftover channel state from previous run
_mux_reset()

# ─── BME680 on Mux Channel 1, address 0x77 ───────────────────────────────────
try:
    import adafruit_bme680
    if I2C_OK and _select_channel(1):
        _bme = adafruit_bme680.Adafruit_BME680_I2C(_i2c, address=0x77)
        _bme.sea_level_pressure = 1013.25
        _bme.filter_size = 3
        _mux_reset()
        BME_OK = True
        print("[sensor] ✓ BME680 (ch1, 0x77)")
    else:
        _bme = None; BME_OK = False
except Exception as e:
    _bme = None; BME_OK = False
    print(f"[sensor] ✗ BME680: {e}")

# ─── ADS1115 on Mux Channel 2 — MQ135 (A0), MAX9814 mic (A1) ─────────────────
try:
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    if I2C_OK and _select_channel(2):
        _ads   = ADS.ADS1115(_i2c)
        _mq135 = AnalogIn(_ads, 0)   # MQ135  on A0
        _mic   = AnalogIn(_ads, 1)   # MAX9814 on A1
        _mux_reset()
        ADS_OK = True
        print("[sensor] ✓ ADS1115 (ch2) — MQ135 A0, MAX9814 A1")
    else:
        _ads = None; ADS_OK = False
except Exception as e:
    _ads = None; ADS_OK = False
    print(f"[sensor] ✗ ADS1115: {e}")

# ─── MLX90614 on Mux Channel 3, address 0x5A (optional) ─────────────────────
try:
    import adafruit_mlx90614
    if I2C_OK and _select_channel(3):
        _mlx   = adafruit_mlx90614.MLX90614(_i2c)
        _mux_reset()
        MLX_OK = True
        print("[sensor] ✓ MLX90614 (ch3, 0x5A)")
    else:
        _mlx = None; MLX_OK = False
except Exception as e:
    _mlx = None; MLX_OK = False
    print(f"[sensor] ✗ MLX90614 (optional): {e}")

# ─── MH-Z19B — UART (no mux) ─────────────────────────────────────────────────
try:
    import mh_z19
    MHZ_OK = True
    print("[sensor] ✓ MH-Z19B (UART)")
except Exception as e:
    MHZ_OK = False
    print(f"[sensor] ✗ MH-Z19B (optional): {e}")

# ─── Buzzer — GPIO17 ─────────────────────────────────────────────────────────
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

# ─── Cry detection config ─────────────────────────────────────────────────────
CRY_THRESHOLD_RAW = 18000  # ~2.25V — tune to your environment
CRY_SAMPLES       = 5
CRY_WINDOW_SEC    = 0.5


def buzz(duration_ms: int = 200):
    if not BUZZER_OK:
        return
    try:
        GPIO.output(17, GPIO.HIGH)
        time.sleep(duration_ms / 1000)
        GPIO.output(17, GPIO.LOW)
    except Exception:
        pass


def _detect_cry() -> bool:
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


def read_all() -> dict:
    """Read all available sensors. Returns dict matching /api/status schema."""
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

    # BME680 (ch1) ─────────────────────────────────────────────────────────────
    if BME_OK:
        try:
            if _select_channel(1):
                data["room_temp"] = round(_bme.temperature, 2)
                data["humidity"]  = int(_bme.relative_humidity)
                data["pressure"]  = round(_bme.pressure, 2)
                gas_r = _bme.gas
                data["gas_index"] = int(max(0, 300000 - gas_r)) if gas_r else 0
                _mux_reset()
        except Exception as e:
            print(f"[sensor] BME680 read error: {e}")
            _mux_reset()

    # ADS1115 (ch2) — MQ135 + MAX9814 ─────────────────────────────────────────
    if ADS_OK:
        try:
            if _select_channel(2):
                mq_raw = abs(_mq135.value)
                data["mq135_raw"] = mq_raw
                mq_index = int((mq_raw / 32767) * 300000)
                data["gas_index"] = max(data["gas_index"], mq_index)
                _mux_reset()
        except Exception as e:
            print(f"[sensor] MQ135 read error: {e}")
            _mux_reset()
        try:
            data["cry_detected"] = _detect_cry()
        except Exception as e:
            print(f"[sensor] Cry detect error: {e}")

    # MLX90614 (ch3) — optional ────────────────────────────────────────────────
    if MLX_OK:
        try:
            if _select_channel(3):
                data["body_temp"]    = round(_mlx.object_temperature, 2)
                data["ambient_temp"] = round(_mlx.ambient_temperature, 2)
                _mux_reset()
        except Exception as e:
            print(f"[sensor] MLX90614 read error: {e}")
            _mux_reset()

    # MH-Z19B — UART, no mux ───────────────────────────────────────────────────
    if MHZ_OK:
        try:
            result = mh_z19.read_all()
            if result and "co2" in result:
                data["co2_ppm"] = int(result["co2"])
        except Exception as e:
            print(f"[sensor] MH-Z19B read error: {e}")

    return data


# ─── Standalone test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n=== Nurture Sensor Test ===\n")
    print(f"  BME680:   {'✓' if BME_OK else '✗'}")
    print(f"  ADS1115:  {'✓' if ADS_OK else '✗'}")
    print(f"  MLX90614: {'✓' if MLX_OK else '✗ (not wired yet)'}")
    print(f"  MH-Z19B:  {'✓' if MHZ_OK else '✗ (not wired yet)'}")
    print(f"  Buzzer:   {'✓' if BUZZER_OK else '✗'}\n")
    print("Reading every 3s — Ctrl+C to stop\n")
    try:
        while True:
            d = read_all()
            print(f"BME680    → Temp:{d['room_temp']}°C  Hum:{d['humidity']}%  Pres:{d['pressure']}hPa  Gas:{d['gas_index']}")
            print(f"ADS1115   → MQ135:{d['mq135_raw']}  Cry:{'YES 🍼' if d['cry_detected'] else 'no'}")
            if MLX_OK:
                print(f"MLX90614  → Body:{d['body_temp']}°C  Ambient:{d['ambient_temp']}°C")
            if MHZ_OK:
                print(f"MH-Z19B   → CO₂:{d['co2_ppm']} ppm")
            print("─" * 55)
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nDone.")
