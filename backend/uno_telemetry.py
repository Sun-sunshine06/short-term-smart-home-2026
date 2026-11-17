"""Parse USB_ASR_D3_V1 telemetry without treating command logs as acknowledgments."""


def parse_telemetry(line):
    if len(line) > 512 or not line.startswith("RAIN_RAW:"):
        return None
    fields = {}
    for item in line.strip().split(","):
        key, separator, value = item.partition(":")
        if not separator or key in fields:
            return None
        fields[key] = value
    values, quality = {}, {}
    mapping = {"RAIN_RAW": "rain_raw", "RAIN": "rain_percent", "RAIN_STATE": "rain_state",
               "SOIL_RAW": "soil_raw", "SOIL": "soil_percent", "SOIL_STATE": "soil_state"}
    for raw_key, key in mapping.items():
        if raw_key not in fields:
            quality[key] = "unknown"
            continue
        value = fields[raw_key]
        if key.endswith("_state"):
            values[key] = value
            allowed = ("DRY", "OK") if key == "soil_state" else ("DRY", "WET")
            quality[key] = "valid" if value in allowed else "invalid"
        else:
            try:
                if key.endswith("_percent"):
                    if not value.endswith("%"):
                        raise ValueError("missing percent suffix")
                    value = value[:-1]
                number = int(value)
                values[key] = number
                maximum = 100 if key.endswith("_percent") else 1023
                quality[key] = "valid" if 0 <= number <= maximum else "invalid"
            except ValueError:
                values[key] = None
                quality[key] = "invalid"
    return {"source": "uno_usb_asr_d3_v1", **values, "quality": quality}
