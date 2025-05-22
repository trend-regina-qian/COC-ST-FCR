def log_message(message):
    print(f"[LOG] {message}")

def validate_config(config):
    required_keys = ['dbname', 'user', 'password', 'host', 'port']
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required configuration key: {key}")

def format_subscriber_data(subscriber):
    return {
        'subscriber_id': subscriber['subscriber_id'],
        'subscriberDevices': subscriber['subscriberDevices'],
        'subscriberEndpoints': subscriber['subscriberEndpoints']
    }

def format_device_data(device):
    return {
        'device_id': device['device_id'],
        'device_type': device['device_type'],
        'location': device['location']
    }