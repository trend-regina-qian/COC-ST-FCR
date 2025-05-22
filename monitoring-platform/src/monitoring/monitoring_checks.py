import logging
import re
from collections import defaultdict

from prometheus_client import Counter, Gauge
from monitoring.metrics_definitions import (
    device_binding_inconsistencies,
    ip_sync_issues,
    endpoint_binding_issues,
    data_sync_delays,
)

def perform_device_binding_consistency_check(connection):
    """
    Perform device binding consistency checks and alignment between physical and logical layers for FSAN values.
    """
    results = []
    logged_messages = set()  # Track already-logged messages to avoid duplicate logs

    with connection.cursor() as cursor:
        # Query physical layer device topology (parentont_fsan, rg_fsan, topo_id)
        cursor.execute("""
            SELECT topo_id, parentont_fsan, rg_fsan
            FROM device_topo
            WHERE state = 'up'
        """)
        physical_layer_topo = cursor.fetchall()
        physical_layer_map = {
            (row[1], row[2]): row[0] for row in physical_layer_topo
        }  # Map (parentont_fsan, rg_fsan) -> topo_id

        # Query logical layer device topology (subscriberDevices and subscriberEndpoints)
        cursor.execute("""
            SELECT s.subscriber_id,
                   s.subscriber_devices,
                   s.subscriber_endpoints,
                   s.subscriber_location_id
            FROM subscriber_topo s
        """)
        logical_layer_topo = cursor.fetchall()

        for subscriber_id, subscriber_devices, subscriber_endpoints, subscriber_location_id in logical_layer_topo:
            # Check for missing devices or endpoints
            if not subscriber_devices:
                logging.warning(f"Subscriber {subscriber_id} has no devices bound. Please bind a device.")
                results.append((subscriber_id, 'incomplete', 'No devices bound'))
                continue
            if not subscriber_endpoints:
                logging.warning(f"Subscriber {subscriber_id} has no endpoints bound. Please bind an endpoint.")
                results.append((subscriber_id, 'incomplete', 'No endpoints bound'))
                continue

            # Extract FSANs from subscriberDevices
            logical_fsans = {device.get('device_fsan') for device in subscriber_devices if device.get('device_fsan')}

            # Extract FSANs from subscriberEndpoints
            endpoint_fsans = defaultdict(set)
            for endpoint in subscriber_endpoints['endpoints']:
                rg_fsan = endpoint.get('rg_fsan')
                ont_fsan = endpoint.get('ont_fsan')
                if rg_fsan and ont_fsan:
                    endpoint_fsans[rg_fsan].add(ont_fsan)

            # Flatten valid FSANs for comparison
            flattened_endpoint_fsans = set(endpoint_fsans.keys()).union(
                {ont_fsan for ont_fsans in endpoint_fsans.values() for ont_fsan in ont_fsans}
            )

            # Compare FSAN sets between subscriberDevices and subscriberEndpoints
            if logical_fsans != flattened_endpoint_fsans:
                new_fsans = logical_fsans - flattened_endpoint_fsans
                removed_fsans = flattened_endpoint_fsans - logical_fsans
                if new_fsans:
                    log_message = f"Subscriber {subscriber_id}: FSANs in subscriberDevices but not in subscriberEndpoints: {new_fsans}"
                    if log_message not in logged_messages:
                        logging.info(log_message)
                        logged_messages.add(log_message)
                    results.append((subscriber_id, 'updated', f"FSANs in subscriberDevices but not in subscriberEndpoints: {new_fsans}"))
                    device_binding_inconsistencies.labels(subscriber_id=subscriber_id).inc(len(new_fsans))
                if removed_fsans:
                    log_message = f"Subscriber {subscriber_id}: FSANs in subscriberEndpoints but not in subscriberDevices: {removed_fsans}"
                    if log_message not in logged_messages:
                        logging.info(log_message)
                        logged_messages.add(log_message)
                    results.append((subscriber_id, 'updated', f"FSANs in subscriberEndpoints but not in subscriberDevices: {removed_fsans}"))
                    device_binding_inconsistencies.labels(subscriber_id=subscriber_id).inc(len(removed_fsans))

            # Validate endpoint_fsans before unpacking
            for rg_fsan, ont_fsans in endpoint_fsans.items():
                if not isinstance(ont_fsans, set):
                    logging.error(f"Invalid data structure for endpoint_fsans: {rg_fsan} -> {ont_fsans}. Skipping.")
                    continue

                # Process valid FSAN pairs
                for ont_fsan in ont_fsans:
                    # Check alignment between physical and logical layers
                    if (ont_fsan, rg_fsan) in physical_layer_map:
                        physical_topo_id = physical_layer_map[(ont_fsan, rg_fsan)]
                        if physical_topo_id != subscriber_location_id:
                            logging.warning(f"ONT {ont_fsan}, RG {rg_fsan} for subscriber {subscriber_id}: Physical topo_id {physical_topo_id} does not match subscriber_location_id {subscriber_location_id}.")
                            results.append((subscriber_id, 'misaligned', f"ONT {ont_fsan}, RG {rg_fsan}: Physical topo_id {physical_topo_id} vs subscriber_location_id {subscriber_location_id}"))
                    else:
                        logging.warning(f"ONT {ont_fsan}, RG {rg_fsan} for subscriber {subscriber_id} is missing in the physical layer.")
                        results.append((subscriber_id, 'missing', f"ONT {ont_fsan}, RG {rg_fsan} not found in physical layer"))
    return results

def perform_ip_sync_status_check(connection):
    """
    Perform IP synchronization status checks and return results.
    """
    results = []
    logged_messages = set()  # Track already-logged messages to avoid duplicate logs

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT LOWER(TRIM(d.rg_mac)) AS rg_mac, 
                   ARRAY_AGG(DISTINCT d.dhcp_ipv4) AS device_ipv4s,
                   ARRAY_AGG(DISTINCT d.dhcp_ipv6) AS device_ipv6s,
                   ARRAY_AGG(DISTINCT e.ip_address) AS endpoint_ips
            FROM device_topo d
            LEFT JOIN subscriber_endpoints e ON LOWER(TRIM(d.rg_mac)) = LOWER(TRIM(e.rg_mac))
            WHERE d.state = 'up'
            GROUP BY LOWER(TRIM(d.rg_mac))
        """)
        for rg_mac, device_ipv4s, device_ipv6s, endpoint_ips in cursor.fetchall():
            # Helper function to normalize IPs by removing subnet masks and treating 'N/A' and None as equivalent
            def normalize_ip(ip):
                if ip in (None, 'N/A'):
                    return 'None'  # Normalize both None and 'N/A' to 'None'
                return re.sub(r'/\d+$', '', ip)  # Remove subnet masks if present

            # Split and normalize dhcp_ipv6 into individual addresses
            split_device_ipv6s = set(
                normalize_ip(ip.strip())
                for ipv6_list in device_ipv6s if ipv6_list
                for ip in ipv6_list.split(',')
            )

            # Normalize device_ipv4s and endpoint_ips
            device_ips = set(normalize_ip(ip) for ip in device_ipv4s if ip) | split_device_ipv6s
            endpoint_ips = set(normalize_ip(ip) for ip in endpoint_ips if ip)

            # Exclude 'None' from comparison
            device_ips.discard('None')
            endpoint_ips.discard('None')

            # Compare the two sets and log unsynced IPs with details
            for ip in device_ips.union(endpoint_ips):
                if ip not in device_ips:
                    log_message = f"RG MAC {rg_mac}, IP {ip}: IP synchronization status is unsynced (missing on device)."
                    if log_message not in logged_messages:
                        logging.info(log_message)
                        logged_messages.add(log_message)
                    results.append((rg_mac, ip, 'unsynced', 'missing on device'))
                    ip_sync_issues.labels(rg_mac=rg_mac, issue_type='missing_on_device').inc()
                elif ip not in endpoint_ips:
                    log_message = f"RG MAC {rg_mac}, IP {ip}: IP synchronization status is unsynced (missing on endpoint)."
                    if log_message not in logged_messages:
                        logging.info(log_message)
                        logged_messages.add(log_message)
                    results.append((rg_mac, ip, 'unsynced', 'missing on endpoint'))
                    ip_sync_issues.labels(rg_mac=rg_mac, issue_type='missing_on_endpoint').inc()
    return results

def perform_endpoint_binding_status_check(connection):
    """
    Perform endpoint binding status checks and return results.
    """
    results = []
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT endpoint_id
            FROM managed_endpoints
            WHERE mac_address IS NULL OR subscriber_id IS NULL
        """)
        for (endpoint_id,) in cursor.fetchall():
            results.append((endpoint_id, 'unbound'))
            endpoint_binding_issues.labels(endpoint_id=endpoint_id).inc()
    return results

def perform_data_sync_delay_check(connection):
    """
    Perform data synchronization delay checks and return results.
    """
    results = []
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT d.topo_id, 
                   MAX(d.lease_first_acquired) AS latest_lease_time, 
                   e.endpoint_created_time
            FROM device_topo d
            LEFT JOIN subscriber_endpoints e ON d.rg_mac = e.rg_mac
            WHERE e.endpoint_created_time IS NOT NULL
            GROUP BY d.topo_id, e.endpoint_created_time
        """)
        for topo_id, latest_lease_time, endpoint_created_time in cursor.fetchall():
            delay = (endpoint_created_time - latest_lease_time).total_seconds()
            results.append((topo_id, delay))
            data_sync_delays.labels(topo_id=topo_id).set(delay)
    return results

def perform_ip_change_check(connection):
    """
    Perform IP address change checks and return results.
    """
    results = []
    logged_endpoints = set()  # Track already-logged endpoint IDs to avoid duplicate logs

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT endpoint_id
            FROM ip_address_change_log
        """)
        for (endpoint_id,) in cursor.fetchall():
            if endpoint_id not in logged_endpoints:
                results.append(endpoint_id)
                logging.info(f"Endpoint ID {endpoint_id}: IP address change detected.")
                logged_endpoints.add(endpoint_id)  # Mark this endpoint as logged
    return results