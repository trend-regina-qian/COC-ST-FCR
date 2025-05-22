import logging
import psycopg2
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_subscriber_topo(cloud_conn, org_id, name_pattern):
    """
    从 Cloud DB 采集逻辑订阅拓扑数据，并结合物理拓扑信息
    :param cloud_conn: 云数据库连接对象
    :param org_id: 组织 ID，用于过滤数据
    :param name_pattern: 订阅者名称的正则表达式，用于过滤数据
    :return: subscriber_topo 数据列表
    """
    cursor = cloud_conn.cursor()

    try:
        # Fetch all required data using JOINs
        query = """
            SELECT 
                cs.subscriber_id,
                cs.name AS subscriber_name, 
                cs.subscriber_location_id,
                cs.account AS subscriber_account, 
                cs.created AS subscriber_created_time,
                cs.updated AS subscriber_updated_time,
                csd.id AS device_fsan,
                csd.created AS device_created_time, 
                csd.updated AS device_updated_time,
                css.usoc AS service_name, 
                css.description AS service_description,
                css.type AS service_type,
                css.endpoint_mapping_option_array AS endpoint_mapping_options, 
                css.created AS service_created_time, 
                css.updated AS service_updated_time,
                ffe.id AS endpoint_id, 
                ffe.agg_group AS endpoint_agg_group, 
                ffe.ip_address, 
                ffe.deleted,
                ffe.delete_time, 
                ffe.cm_serial_number AS ont_fsan,
                ffe.serial_number AS rg_fsan,
                ffe.mac_address AS rg_mac, 
                ffe.mapped_by, 
                ffe.old_ip_address,
                ffe.flow_discovered_time,
                ffe.create_time AS endpoint_created_time,
                ffe.update_time AS endpoint_updated_time
            FROM cloud_subscribers cs
            LEFT JOIN cloud_subscriber_devices csd ON cs.subscriber_id = csd.subscriber_id
            LEFT JOIN cloud_subscriber_services css ON cs.subscriber_id = css.subscriber_id
            LEFT JOIN fa_flow_endpoints ffe ON cs.subscriber_id::uuid = ffe.subscriber_id
            WHERE cs.org_id = %s AND cs.name ~ %s
        """
        logger.info("Executing query to fetch subscriber topology...")
        cursor.execute(query, (org_id, name_pattern))
        rows = cursor.fetchall()
        logger.info(f"Fetched {len(rows)} records from cloud database.")

        # Fetch ONT FSANs from cloud_subscriber_sync_devices
        ont_fsan_set = set()
        try:
            cursor.execute("SELECT fsan FROM cloud_subscriber_sync_devices")
            ont_fsan_rows = cursor.fetchall()
            ont_fsan_set = {row[0] for row in ont_fsan_rows}
            logger.info(f"Fetched {len(ont_fsan_set)} ONT FSANs from cloud_subscriber_sync_devices.")
        except Exception as e:
            logger.error(f"An error occurred while fetching ONT FSANs: {e}")
            return []

        # Use defaultdict to build the subscriber_topo structure
        subscriber_topo = defaultdict(lambda: {
            "subscriber_id": None,
            "subscriber_location_id": "N/A",            
            "subscriber_name": "N/A",
            "subscriber_account": "N/A",            
            "subscriberDevices": [],
            "subscriberServices": [],
            "subscriberEndpoints": {
                "endpoint_agg_group": [], 
                "endpoints": []
            },
            "subscriber_created_time": "N/A",
            "subscriber_updated_time": "N/A",
            "added_devices": set(),  # Track added devices
            "added_services": set(),  # Track added services
            "added_endpoints": set()  # Track added endpoints
        })

        for row in rows:
            (
                subscriber_id, subscriber_name, subscriber_location_id, subscriber_account,
                subscriber_created_time, subscriber_updated_time,
                device_fsan, device_created_time, device_updated_time, 
                service_name, service_description, service_type, endpoint_mapping_options,
                service_created_time, service_updated_time,
                endpoint_id, endpoint_agg_group, ip_address, deleted, delete_time,  # Added deleted and delete_time
                ont_fsan, rg_fsan, rg_mac, mapped_by, old_ip_address, flow_discovered_time,
                endpoint_created_time, endpoint_updated_time
            ) = row

            # Initialize subscriber entry
            if subscriber_topo[subscriber_id]["subscriber_id"] is None:
                subscriber_topo[subscriber_id]["subscriber_id"] = subscriber_id
                subscriber_topo[subscriber_id]["subscriber_name"] = subscriber_name
                subscriber_topo[subscriber_id]["subscriber_location_id"] = subscriber_location_id
                subscriber_topo[subscriber_id]["subscriber_account"] = subscriber_account
                subscriber_topo[subscriber_id]["subscriber_created_time"] = subscriber_created_time
                subscriber_topo[subscriber_id]["subscriber_updated_time"] = subscriber_updated_time

            # Add device data if not already added
            device_key = (device_fsan, device_created_time, device_updated_time)
            if device_fsan and device_key not in subscriber_topo[subscriber_id]["added_devices"]:
                device_type = "ONT" if device_fsan in ont_fsan_set else "RG"
                subscriber_topo[subscriber_id]["subscriberDevices"].append({
                    "device_fsan": device_fsan,
                    "device_type": device_type,
                    "device_created_time": device_created_time,
                    "device_updated_time": device_updated_time
                })
                subscriber_topo[subscriber_id]["added_devices"].add(device_key)

            # Add service data if not already added
            service_key = (service_name, service_created_time, service_updated_time)
            if service_name and service_key not in subscriber_topo[subscriber_id]["added_services"]:
                subscriber_topo[subscriber_id]["subscriberServices"].append({
                    "service_name": service_name,
                    "service_description": service_description,
                    "service_type": service_type,
                    "endpoint_mapping_options": endpoint_mapping_options,
                    "service_created_time": service_created_time,
                    "service_updated_time": service_updated_time
                })
                subscriber_topo[subscriber_id]["added_services"].add(service_key)

            # Add endpoint data if not already added
            endpoint_key = (endpoint_id, endpoint_created_time, endpoint_updated_time)
            if endpoint_id and endpoint_key not in subscriber_topo[subscriber_id]["added_endpoints"]:
                # Assign endpoint_agg_group to the subscriberEndpoints field
                subscriber_topo[subscriber_id]["subscriberEndpoints"]["endpoint_agg_group"] = endpoint_agg_group

                # Add endpoint data to the endpoints list
                subscriber_topo[subscriber_id]["subscriberEndpoints"]["endpoints"].append({
                    "endpoint_id": endpoint_id,
                    "ip_address": ip_address,
                    "deleted": deleted,
                    "delete_time": delete_time,
                    "ont_fsan": ont_fsan,
                    "rg_fsan": rg_fsan,
                    "rg_mac": rg_mac,
                    "mapped_by": mapped_by,
                    "old_ip_address": old_ip_address,
                    "flow_discovered_time": flow_discovered_time,
                    "endpoint_created_time": endpoint_created_time,
                    "endpoint_updated_time": endpoint_updated_time
                })
                subscriber_topo[subscriber_id]["added_endpoints"].add(endpoint_key)

        # Remove tracking sets before returning the result
        for subscriber in subscriber_topo.values():
            subscriber.pop("added_devices", None)
            subscriber.pop("added_services", None)
            subscriber.pop("added_endpoints", None)

        logger.info(f"Generated {len(subscriber_topo)} unique subscriber entries in subscriber_topo.")
        return list(subscriber_topo.values())

    except Exception as e:
        logger.error(f"An error occurred while fetching subscriber data: {e}")
        return []
