import json
import logging
from datetime import datetime

import psycopg2
from psycopg2 import sql

def connect_to_local_db(db_config):
    try:
        connection = psycopg2.connect(**db_config)
        return connection
    except Exception as e:
        print(f"Error connecting to local database: {e}")
        return None

def store_device_topology(connection, device_topo):
    """
    Store device topology data in the local database.
    :param connection: Connection to the local database.
    :param device_topo: List of device topology data.
    """
    with connection.cursor() as cursor:
        for device in device_topo:
            # Validate ip_address_family
            if device['ip_address_family'] not in ['IPv4', 'IPv6', 'Dual Stack']:
                logging.warning(f"Invalid ip_address_family value: {device['ip_address_family']}. Skipping device: {device}")
                continue

            # Validate required fields
            if not device['parentont_fsan'] or not device['rg_fsan'] or not device['rg_mac']:
                logging.warning(f"Skipping device with missing required fields: {device}")
                continue

            cursor.execute(
                sql.SQL("""
                    INSERT INTO device_topo (
                        topo_id, parentont_fsan, rg_fsan, rg_mac, device_type, dhcp_IPv4, dhcp_IPv6, 
                        parentolt_server, ip_address_family, state, lease_first_acquired, lease_expires, device_data
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (topo_id) DO UPDATE SET
                        parentont_fsan = EXCLUDED.parentont_fsan,
                        rg_fsan = EXCLUDED.rg_fsan,
                        rg_mac = EXCLUDED.rg_mac,
                        device_type = EXCLUDED.device_type,
                        dhcp_IPv4 = EXCLUDED.dhcp_IPv4,
                        dhcp_IPv6 = EXCLUDED.dhcp_IPv6,
                        parentolt_server = EXCLUDED.parentolt_server,
                        ip_address_family = EXCLUDED.ip_address_family,
                        state = EXCLUDED.state,
                        lease_first_acquired = EXCLUDED.lease_first_acquired,
                        lease_expires = EXCLUDED.lease_expires,
                        device_data = EXCLUDED.device_data
                """),
                (
                    device['topo_id'],
                    device['parentont_fsan'],
                    device['rg_fsan'],
                    device['rg_mac'],
                    device['device_type'],
                    device['dhcp_IPv4'],
                    device['dhcp_IPv6'],
                    device['parentolt_server'],
                    device['ip_address_family'],
                    device['state'],
                    sanitize_timestamp(device['lease_first_acquired']),  # Sanitize timestamp
                    sanitize_timestamp(device['lease_expires']),  # Sanitize timestamp
                    json.dumps(device)  # Store the entire device data as JSON
                )
            )
        connection.commit()

def serialize_datetime(obj):
    """
    Helper function to convert datetime objects to strings for JSON serialization.
    Handles strings and returns them as-is.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()  # Convert to ISO 8601 format
    elif isinstance(obj, str):
        try:
            # Attempt to parse the string as a datetime
            return datetime.fromisoformat(obj).isoformat()
        except ValueError:
            return obj  # Return the string as-is if it cannot be parsed
    raise TypeError(f"Type {type(obj)} not serializable")

def sanitize_timestamp(value):
    """
    Convert invalid timestamp values (e.g., 'N/A') to None or ensure they are valid datetime strings.
    """
    if value in ["N/A", None]:
        return None
    if isinstance(value, str):
        try:
            # Attempt to parse the string as a datetime
            return datetime.fromisoformat(value).isoformat()
        except ValueError:
            return value  # Return the string as-is if it cannot be parsed
    return value

def store_subscriber_topology(connection, subscriber_topo):
    """
    Store subscriber topology data in the local database.
    :param connection: Connection to the local database.
    :param subscriber_topo: List of subscriber topology data.
    """
    with connection.cursor() as cursor:
        for subscriber in subscriber_topo:
            cursor.execute(
                sql.SQL("""
                    INSERT INTO subscriber_topo (
                        subscriber_id, subscriber_location_id, subscriber_name, subscriber_account,
                        subscriber_created_time, subscriber_updated_time, subscriber_devices,
                        subscriber_services, subscriber_endpoints
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (subscriber_id) DO UPDATE SET
                        subscriber_location_id = EXCLUDED.subscriber_location_id,
                        subscriber_name = EXCLUDED.subscriber_name,
                        subscriber_account = EXCLUDED.subscriber_account,
                        subscriber_created_time = EXCLUDED.subscriber_created_time,
                        subscriber_updated_time = EXCLUDED.subscriber_updated_time,
                        subscriber_devices = EXCLUDED.subscriber_devices,
                        subscriber_services = EXCLUDED.subscriber_services,
                        subscriber_endpoints = EXCLUDED.subscriber_endpoints
                """),
                (
                    subscriber['subscriber_id'],
                    subscriber['subscriber_location_id'],
                    subscriber['subscriber_name'],
                    subscriber['subscriber_account'],
                    sanitize_timestamp(subscriber['subscriber_created_time']),  # Sanitize timestamp
                    sanitize_timestamp(subscriber['subscriber_updated_time']),  # Sanitize timestamp
                    json.dumps(subscriber['subscriberDevices'], default=serialize_datetime),  # Serialize datetime
                    json.dumps(subscriber['subscriberServices'], default=serialize_datetime),  # Serialize datetime
                    json.dumps(subscriber['subscriberEndpoints'], default=serialize_datetime)  # Serialize datetime
                )
            )
        connection.commit()

def store_subscriber_endpoints(connection, subscriber_endpoints):
    """
    Store subscriber endpoints data in the local database.
    :param connection: Connection to the local database.
    :param subscriber_endpoints: List of subscriber endpoints data.
    """
    with connection.cursor() as cursor:
        for endpoint in subscriber_endpoints:
            cursor.execute(
                sql.SQL("""
                    INSERT INTO subscriber_endpoints (
                        endpoint_id, ip_address, deleted, delete_time, ont_fsan, rg_fsan, rg_mac,
                        mapped_by, old_ip_address, flow_discovered_time, endpoint_created_time,
                        endpoint_updated_time, endpoint_agg_group
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (endpoint_id) DO UPDATE SET
                        ip_address = EXCLUDED.ip_address,
                        deleted = EXCLUDED.deleted,
                        delete_time = EXCLUDED.delete_time,
                        ont_fsan = EXCLUDED.ont_fsan,
                        rg_fsan = EXCLUDED.rg_fsan,
                        rg_mac = EXCLUDED.rg_mac,
                        mapped_by = EXCLUDED.mapped_by,
                        old_ip_address = EXCLUDED.old_ip_address,
                        flow_discovered_time = EXCLUDED.flow_discovered_time,
                        endpoint_created_time = EXCLUDED.endpoint_created_time,
                        endpoint_updated_time = EXCLUDED.endpoint_updated_time,
                        endpoint_agg_group = EXCLUDED.endpoint_agg_group
                """),
                (
                    endpoint['endpoint_id'],
                    endpoint['ip_address'],
                    endpoint['deleted'],
                    endpoint['delete_time'],
                    endpoint['ont_fsan'],
                    endpoint['rg_fsan'],
                    endpoint['rg_mac'],
                    endpoint['mapped_by'],
                    endpoint['old_ip_address'],
                    endpoint['flow_discovered_time'],
                    endpoint['endpoint_created_time'],
                    endpoint['endpoint_updated_time'],
                    endpoint['endpoint_agg_group']
                )
            )
        connection.commit()

def fetch_device_topology(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM device_topo")
        return cursor.fetchall()

def fetch_subscriber_topology(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM subscriber_topo")
        return cursor.fetchall()