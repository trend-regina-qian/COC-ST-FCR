import os
import sys
import signal
import logging
import configparser
import json
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor
from tenacity import retry, stop_after_attempt, wait_fixed
from prometheus_client import start_http_server

from database.local_db import (
    store_device_topology,
    store_subscriber_topology,
    store_subscriber_endpoints,
)
from fetch_topo.fetch_subscriber_data import fetch_subscriber_topo
from fetch_topo.fetch_device_data import fetch_device_topo
from monitoring.metrics_exporter import start_metrics_exporter
from monitoring.monitoring_checks import (
    perform_device_binding_consistency_check,
    perform_ip_sync_status_check,
    perform_endpoint_binding_status_check,
    perform_data_sync_delay_check,
    perform_ip_change_check,
)

# Add the project root to PYTHONPATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

# Graceful shutdown handler
def signal_handler(sig, frame):
    logging.info("Shutting down gracefully...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def connect_to_db(config):
    return psycopg2.connect(**config)

def collect_data(local_conn, cloud_conn, olt_server_config):
    """
    Collect and store data from device and subscriber sources.
    """
    # Fetch and store device topology
    logging.info("Fetching device data...")
    device_topo = fetch_device_topo(olt_server_config)
    logging.info(f"Fetched {len(device_topo)} device records.")
    store_device_topology(local_conn, device_topo)

    # Fetch and store subscriber topology
    logging.info("Fetching subscriber data...")
    subscriber_topo = fetch_subscriber_topo(cloud_conn, "12987422", "SOAK")
    logging.info(f"Fetched {len(subscriber_topo)} subscriber records.")
    store_subscriber_topology(local_conn, subscriber_topo)

    logging.info("Extracting and storing subscriber endpoints...")
    subscriber_endpoints = []
    for subscriber in subscriber_topo:
        endpoint_agg_group = subscriber["subscriberEndpoints"].get("endpoint_agg_group", None)
        for endpoint in subscriber["subscriberEndpoints"].get("endpoints", []):
            endpoint["endpoint_agg_group"] = endpoint_agg_group
            subscriber_endpoints.append(endpoint)
    store_subscriber_endpoints(local_conn, subscriber_endpoints)
    logging.info(f"Extracted {len(subscriber_endpoints)} subscriber endpoints.")

def sync_endpoints_from_cloud(cloud_connection, local_connection):
    """
    Fetch all endpoints from the cloud database and store them in the local database.
    """
    batch_size = 1000
    offset = 0

    with cloud_connection.cursor(cursor_factory=RealDictCursor) as cloud_cursor, local_connection.cursor() as local_cursor:
        while True:
            cloud_cursor.execute("""
                SELECT *, row_to_json(ffe) AS endpoint_data
                FROM fa_flow_endpoints ffe
                WHERE org_id = '12987422' AND name ~ 'SOAK' AND deleted = false
                LIMIT %s OFFSET %s
            """, (batch_size, offset))
            endpoints = cloud_cursor.fetchall()

            if not endpoints:
                break

            for endpoint in endpoints:
                endpoint_id = endpoint['id']
                mac_address = endpoint['mac_address']
                subscriber_id = endpoint['subscriber_id']
                org_id = str(endpoint['org_id']) if isinstance(endpoint['org_id'], uuid.UUID) else str(uuid.UUID(int=endpoint['org_id']))
                name = endpoint['name']
                deleted = endpoint['deleted']
                serial_number = endpoint['serial_number']
                endpoint_data = json.dumps(endpoint['endpoint_data'])  # Convert to JSON string
                ip_address = endpoint.get('ip_address')  # Safely get ip_address from endpoint data
                agg_group = endpoint.get('agg_group')
                cm_serial_number = endpoint.get('cm_serial_number')
                old_ip_address = endpoint.get('old_ip_address')
                mapped_by = endpoint.get('mapped_by')
                flow_discovered_time = endpoint.get('flow_discovered_time')
                create_time = endpoint.get('create_time')
                update_time = endpoint.get('update_time')

                local_cursor.execute("""
                    INSERT INTO managed_endpoints (
                        endpoint_id, mac_address, subscriber_id, org_id, name, deleted, serial_number, endpoint_data, ip_address,
                        agg_group, cm_serial_number, old_ip_address, mapped_by, flow_discovered_time, create_time, update_time
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (endpoint_id) DO UPDATE SET
                        mac_address = EXCLUDED.mac_address,
                        subscriber_id = EXCLUDED.subscriber_id,
                        org_id = EXCLUDED.org_id,
                        name = EXCLUDED.name,
                        deleted = EXCLUDED.deleted,
                        serial_number = EXCLUDED.serial_number,
                        endpoint_data = EXCLUDED.endpoint_data,
                        ip_address = EXCLUDED.ip_address,
                        agg_group = EXCLUDED.agg_group,
                        cm_serial_number = EXCLUDED.cm_serial_number,
                        old_ip_address = EXCLUDED.old_ip_address,
                        mapped_by = EXCLUDED.mapped_by,
                        flow_discovered_time = EXCLUDED.flow_discovered_time,
                        create_time = EXCLUDED.create_time,
                        update_time = EXCLUDED.update_time
                """, (
                    endpoint_id, mac_address, subscriber_id, org_id, name, deleted, serial_number, endpoint_data, ip_address,
                    agg_group, cm_serial_number, old_ip_address, mapped_by, flow_discovered_time, create_time, update_time
                ))

            local_connection.commit()
            offset += batch_size

def perform_monitoring_checks(local_conn):
    """
    Perform all monitoring checks and log the results.
    """
    if local_conn.closed:
        logging.error("Database connection is closed. Cannot perform monitoring checks.")
        return

    try:
        logging.info("Checking device and endpoint alignment...")
        results = perform_device_binding_consistency_check(local_conn)
        logged_subscribers = set()  # Track already-logged subscribers
        for subscriber_id, status, details in results:
            if subscriber_id not in logged_subscribers:
                if details:
                    logging.info(f"Subscriber ID {subscriber_id}: Device binding consistency is {status}. Details: {details}")
                else:
                    logging.info(f"Subscriber ID {subscriber_id}: Device binding consistency is {status}.")
                logged_subscribers.add(subscriber_id)
        logging.info("Device and endpoint alignment check completed successfully.")
    except Exception as e:
        logging.error(f"Error during device and endpoint alignment check: {e}", exc_info=True)

    try:
        logging.info("Checking IP alignment between physical and subscription layers...")
        results = perform_ip_sync_status_check(local_conn)
        logged_ips = set()  # Track already-logged IPs
        for rg_mac, rg_ip, status, details in results:
            log_message = f"RG MAC {rg_mac}, IP {rg_ip}: IP synchronization status is {status}. Details: {details}"
            if log_message not in logged_ips:
                logging.info(log_message)
                logged_ips.add(log_message)
        logging.info("IP alignment check completed successfully.")
    except Exception as e:
        logging.error(f"Error during IP alignment check: {e}", exc_info=True)

    try:
        logging.info("Checking endpoint binding status...")
        results = perform_endpoint_binding_status_check(local_conn)
        logged_endpoints = set()  # Track already-logged endpoints
        for endpoint_id, status in results:
            if endpoint_id not in logged_endpoints:
                logging.info(f"Endpoint ID {endpoint_id}: Binding status is {status}.")
                logged_endpoints.add(endpoint_id)
        logging.info("Endpoint binding status check completed successfully.")
    except Exception as e:
        logging.error(f"Error during endpoint binding status check: {e}", exc_info=True)

    try:
        logging.info("Checking data synchronization delay...")
        results = perform_data_sync_delay_check(local_conn)
        logged_topos = set()  # Track already-logged topo IDs
        for topo_id, delay in results:
            if topo_id not in logged_topos:
                logging.info(f"Topo ID {topo_id}: Data synchronization delay is {delay} seconds.")
                logged_topos.add(topo_id)
        logging.info("Data synchronization delay check completed successfully.")
    except Exception as e:
        logging.error(f"Error during data synchronization delay check: {e}", exc_info=True)

    try:
        logging.info("Checking IP address changes...")
        results = perform_ip_change_check(local_conn)
        logged_changes = set()  # Track already-logged endpoint IDs
        for endpoint_id in results:
            if endpoint_id not in logged_changes:
                logging.info(f"Endpoint ID {endpoint_id}: IP address change detected.")
                logged_changes.add(endpoint_id)
        logging.info("IP address change check completed successfully.")
    except Exception as e:
        logging.error(f"Error during IP address change check: {e}", exc_info=True)

def main():
    # Load configuration from the relative path
    config = configparser.ConfigParser()
    config.read('./config/config.ini')  # Correct relative path

    local_db_config = {
        "dbname": config['config']['local_db_name'],
        "user": config['config']['local_db_user'],
        "password": config['config']['local_db_password'],
        "host": config['config']['local_db_host'],
        "port": config['config']['local_db_port']
    }

    cloud_db_config = {
        "dbname": config['config']['cloud_db_name'],
        "user": config['config']['cloud_db_user'],
        "password": config['config']['cloud_db_password'],
        "host": config['config']['cloud_db_host'],
        "port": config['config']['cloud_db_port']
    }
    
    olt_server_config = {
        "ip": config['config']['olt_server_ip'],
        "username": config['config']['olt_server_username'],
        "password": config['config']['olt_server_password']
    }

    try:
        with connect_to_db(local_db_config) as local_conn, connect_to_db(cloud_db_config) as cloud_conn:
            logging.info("Connected to local and cloud databases.")

            # Start Prometheus metrics exporter
            logging.info("Starting Prometheus metrics exporter...")
            start_http_server(8000)  # Expose metrics on port 8000

            # Collect data
            collect_data(local_conn, cloud_conn, olt_server_config)

            # Sync endpoints from cloud
            logging.info("Syncing endpoints from cloud...")
            sync_endpoints_from_cloud(cloud_conn, local_conn)

            # Perform monitoring checks
            perform_monitoring_checks(local_conn)

            # Start Prometheus metrics exporter
            logging.info("Starting Prometheus metrics exporter...")
            connection_string = f"dbname={local_db_config['dbname']} user={local_db_config['user']} password={local_db_config['password']} host={local_db_config['host']} port={local_db_config['port']}"
            start_metrics_exporter(connection_string)

    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    main()