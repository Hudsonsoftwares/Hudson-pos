import re

def parse_coordinate(value):
    """
    Parses various format styles of latitude and longitude coordinates into a standard float.
    Handles decimal values, directional suffixes (N, S, E, W), degree symbols, and DMS formats.
    """
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    
    val_str = str(value).strip()
    if not val_str:
        return 0.0
        
    val_upper = val_str.upper()
    multiplier = 1.0
    if any(val_upper.startswith(x) or val_upper.endswith(x) for x in ('S', 'W')):
        multiplier = -1.0
        
    for char in ('N', 'S', 'E', 'W'):
        val_upper = val_upper.replace(char, '')
        
    val_upper = val_upper.strip()
    
    try:
        temp_str = val_upper.replace(',', '.')
        return float(temp_str) * multiplier
    except ValueError:
        pass
        
    # DMS format: 9° 31' 49.8"
    dms_match = re.match(
        r'^\s*([+-]?\d+(?:\.\d+)?)\s*[°dD\s\-]\s*(\d+(?:\.\d+)?)\s*[\'′mM\s\-]\s*(\d+(?:\.\d+)?)\s*["″sS]?\s*$',
        val_upper
    )
    if dms_match:
        deg = float(dms_match.group(1))
        minute = float(dms_match.group(2))
        sec = float(dms_match.group(3))
        sign = -1.0 if deg < 0 or multiplier < 0 else 1.0
        abs_deg = abs(deg)
        decimal_val = abs_deg + (minute / 60.0) + (sec / 3600.0)
        return decimal_val * sign

    # DM format: 9° 31'
    dm_match = re.match(
        r'^\s*([+-]?\d+(?:\.\d+)?)\s*[°dD\s\-]\s*(\d+(?:\.\d+)?)\s*[\'′mM]?\s*$',
        val_upper
    )
    if dm_match:
        deg = float(dm_match.group(1))
        minute = float(dm_match.group(2))
        sign = -1.0 if deg < 0 or multiplier < 0 else 1.0
        abs_deg = abs(deg)
        decimal_val = abs_deg + (minute / 60.0)
        return decimal_val * sign
        
    # Fallback to cleaning special characters and parsing float
    cleaned_chars = []
    has_dot = False
    for char in val_upper:
        if char.isdigit():
            cleaned_chars.append(char)
        elif char in ('-', '+') and not cleaned_chars:
            cleaned_chars.append(char)
        elif char in ('.', ','):
            if not has_dot:
                cleaned_chars.append('.')
                has_dot = True
    
    cleaned_str = "".join(cleaned_chars)
    if cleaned_str:
        try:
            return float(cleaned_str) * multiplier
        except ValueError:
            pass
            
    raise ValueError(f"Could not parse coordinate: {value}")
