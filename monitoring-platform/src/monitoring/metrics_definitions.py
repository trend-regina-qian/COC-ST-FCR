from prometheus_client import Counter, Gauge

# Define Prometheus metrics
device_binding_inconsistencies = Counter(
    'device_binding_inconsistencies', 'Count of device binding inconsistencies', ['subscriber_id']
)
ip_sync_issues = Counter(
    'ip_sync_issues', 'Count of IP synchronization issues', ['rg_mac', 'issue_type']
)
endpoint_binding_issues = Counter(
    'endpoint_binding_issues', 'Count of endpoint binding issues', ['endpoint_id']
)
data_sync_delays = Gauge(
    'data_sync_delays', 'Data synchronization delays in seconds', ['topo_id']
)

subscriber_device_binding_consistency = Gauge(
    'subscriber_device_binding_consistency',
    'Tracks the consistency between subscriberDevices and subscriberEndpoints',
    ['subscriber_id', 'status']
)

device_endpoint_ip_sync = Gauge(
    'device_endpoint_ip_sync',
    'Tracks the synchronization status of IP addresses between device_topo and subscriber_endpoints',
    ['rg_mac', 'rg_ip', 'status']
)

endpoint_binding_status = Gauge(
    'endpoint_binding_status',
    'Tracks the binding status of endpoints to devices or subscribers',
    ['endpoint_id', 'status']
)

data_sync_delay = Gauge(
    'data_sync_delay',
    'Tracks the data synchronization delay between device_topo and subscriber_endpoints',
    ['topo_id']
)

endpoint_ip_changes = Counter(
    'endpoint_ip_changes',
    'Tracks the number of IP address changes in managed_endpoints',
    ['endpoint_id']
)
