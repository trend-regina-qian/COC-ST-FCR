import time
import logging

import psycopg2
from prometheus_client import start_http_server

from monitoring.monitoring_checks import (
    perform_device_binding_consistency_check,
    perform_ip_sync_status_check,
    perform_endpoint_binding_status_check,
    perform_data_sync_delay_check,
    perform_ip_change_check,
)
from monitoring.metrics_definitions import (
    device_binding_inconsistencies,
    ip_sync_issues,
    endpoint_binding_issues,
    data_sync_delays,
    subscriber_device_binding_consistency,
    device_endpoint_ip_sync,
    endpoint_binding_status,
    data_sync_delay,
    endpoint_ip_changes,
)

def collect_metrics(connection):
    """
    Collect all metrics for Prometheus by calling monitoring checks.
    """
    try:
        # Device binding consistency
        for subscriber_id, status, details in perform_device_binding_consistency_check(connection):
            subscriber_device_binding_consistency.labels(subscriber_id=subscriber_id, status=status).set(1)

        # IP synchronization status
        for rg_mac, rg_ip, status, details in perform_ip_sync_status_check(connection):
            device_endpoint_ip_sync.labels(rg_mac=rg_mac, rg_ip=rg_ip, status=status).set(1)

        # Endpoint binding status
        for endpoint_id, status in perform_endpoint_binding_status_check(connection):
            endpoint_binding_status.labels(endpoint_id=endpoint_id, status=status).set(1)

        # Data synchronization delay
        for topo_id, delay in perform_data_sync_delay_check(connection):
            data_sync_delay.labels(topo_id=topo_id).set(delay)

        # IP address changes
        for endpoint_id in perform_ip_change_check(connection):
            endpoint_ip_changes.labels(endpoint_id=endpoint_id).inc(1)

    except Exception as e:
        logging.error(f"Error collecting metrics: {e}")

def start_metrics_exporter(connection_string, prometheus_host="0.0.0.0", prometheus_port=8000):
    """
    Start the Prometheus metrics server and begin collecting metrics.
    """
    try:
        connection = psycopg2.connect(connection_string)
        start_http_server(prometheus_port, addr=prometheus_host)
        logging.info(f"Prometheus metrics server started on {prometheus_host}:{prometheus_port}")
        while True:
            collect_metrics(connection)
            time.sleep(60)
    except psycopg2.Error as db_error:
        logging.error(f"Database connection error: {db_error}")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
