import psycopg2
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_paginated_data(cursor, query, page_size=1000):
    """
    分页查询数据
    :param cursor: 数据库游标
    :param query: SQL 查询语句
    :param page_size: 每页大小
    :return: 分页数据生成器
    """
    offset = 0
    while True:
        paginated_query = f"{query} LIMIT {page_size} OFFSET {offset}"
        cursor.execute(paginated_query)
        rows = cursor.fetchall()
        if not rows:
            break
        yield rows
        offset += page_size

def fetch_subscriber_topo(cloud_conn, org_id, name_pattern):
    """
    从 Cloud DB 采集逻辑订阅拓扑数据，并结合物理拓扑信息
    :param cloud_conn: 云数据库连接对象
    :param org_id: 组织 ID，用于过滤数据
    :param name_pattern: 订阅者名称的正则表达式，用于过滤数据
    :param device_topo: 物理拓扑数据列表
    :return: subscriber_topo 数据列表
    """
    cursor = cloud_conn.cursor()

    try:
        # 查询符合条件的 subscribers
        logger.info("Fetching data from cloud_subscribers...")
        query = f"""
            SELECT 
                cs.subscriber_id,
                cs.name AS subscriber_name, 
                cs.subscriber_location_id,
                cs.account AS subscriber_account, 
                cs.created AS subscriber_created_time,
                cs.updated AS subscriber_updated_time
            FROM cloud_subscribers cs
            WHERE cs.org_id = '{org_id}' 
              AND cs.name ~ '{name_pattern}'
        """
        logger.info(f"Executing query: {query}")
        cursor.execute(query)
        subscribers = cursor.fetchall()
        logger.info(f"Fetched {len(subscribers)} subscribers from cloud_subscribers.")

        if not subscribers:
            logger.info("No subscribers found. Returning empty topology.")
            return []

        # 提取 subscriber_id 和 subscriber_location_id 映射
        subscriber_location_map = {row[0]: row[2] for row in subscribers}

        # 查询这些 subscribers 下绑定的 RG/ONT 设备
        logger.info("Fetching data from cloud_subscriber_devices...")
        query = f"""
            SELECT 
                csd.subscriber_id, 
                csd.id AS rg_fsan_or_ont_fsan, 
                csd.created AS device_created_time, 
                csd.updated AS device_updated_time
            FROM cloud_subscriber_devices csd
            WHERE csd.subscriber_id IN ({','.join(f"'{sub[0]}'" for sub in subscribers)})
        """
        logger.info(f"Executing query: {query}")
        cursor.execute(query)
        subscriber_devices = cursor.fetchall()
        logger.info(f"Fetched {len(subscriber_devices)} records from cloud_subscriber_devices.")

        # 查询这些 subscribers 下的services配置
        logger.info("Fetching data from cloud_subscriber_services...")
        query = f"""
            SELECT 
                css.subscriber_id, 
                css.usoc AS service_name, 
                css.description AS service_description,
                css.type AS service_type,
                css.endpoint_mapping_option_array AS endpoint_mapping_options, 
                css.created AS service_created_time, 
                css.updated AS service_updated_time
            FROM cloud_subscriber_services css
            WHERE css.subscriber_id IN ({','.join(f"'{sub[0]}'" for sub in subscribers)})
        """
        logger.info(f"Executing query: {query}")
        cursor.execute(query)
        subscriber_services = cursor.fetchall()
        logger.info(f"Fetched {len(subscriber_services)} records from cloud_subscriber_services.")

        # 查询这些 subscribers 下绑定的 endpoints
        logger.info("Fetching data from fa_flow_endpoints...")
        query = f"""
            SELECT 
                ffe.subscriber_id, 
                ffe.id AS endpoint_id, 
                ffe.agg_group AS endpoint_agg_group, 
                ffe.ip_address, 
                ffe.cm_serial_number AS ont_fsan,
                ffe.serial_number AS rg_fsan,
                ffe.mac_address AS rg_mac, 
                ffe.mapped_by, 
                ffe.old_ip_address,
                ffe.flow_discovered_time,
                ffe.create_time AS endpoint_created_time,
                ffe.update_time AS endpoint_updated_time
            FROM fa_flow_endpoints ffe
            WHERE ffe.deleted = FALSE 
              AND ffe.subscriber_id IN (
                  SELECT CAST(cs.subscriber_id AS UUID)
                  FROM cloud_subscribers cs
                  WHERE cs.org_id = '{org_id}' 
                    AND cs.name ~ '{name_pattern}'
              )
        """
        logger.info(f"Executing query: {query}")
        cursor.execute(query)
        endpoints = cursor.fetchall()
        logger.info(f"Fetched {len(endpoints)} active records from fa_flow_endpoints.")

        # 使用 defaultdict 简化数据整合逻辑
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
            "subscriber_updated_time": "N/A"
        })

        # 整合 cloud_subscriber_devices 数据
        for device in subscriber_devices:
            subscriber_id, rg_fsan_or_ont_fsan, device_created_time, device_updated_time = device

            # 初始化 subscriber_topo 条目
            if subscriber_topo[subscriber_id]["subscriber_id"] is None:
                subscriber_topo[subscriber_id]["subscriber_id"] = subscriber_id
                subscriber_topo[subscriber_id]["subscriber_name"] = next(
                    (sub[1] for sub in subscribers if sub[0] == subscriber_id), "N/A"
                )
                subscriber_topo[subscriber_id]["subscriber_location_id"] = subscriber_location_map.get(subscriber_id, "N/A")

            # 添加 RG 或 ONT 设备信息
            subscriber_topo[subscriber_id]["subscriberDevices"].append({
                "rg_fsan_or_ont_fsan": rg_fsan_or_ont_fsan,
                "device_created_time": device_created_time,
                "device_updated_time": device_updated_time
            })

        # 整合 cloud_subscriber_services 数据
        for service in subscriber_services:
            subscriber_id, service_name, service_description, service_type, endpoint_mapping_options, service_created_time, service_updated_time = service

            # 添加服务信息
            subscriber_topo[subscriber_id]["subscriberServices"].append({
                "service_name": service_name,
                "service_description": service_description,
                "service_type": service_type,
                "endpoint_mapping_options": endpoint_mapping_options,
                "service_created_time": service_created_time,
                "service_updated_time": service_updated_time
            })

        # 整合 fa_flow_endpoints 数据
        for endpoint in endpoints:
            (
                subscriber_id, endpoint_id, endpoint_agg_group,
                ip_address, ont_fsan, rg_fsan, rg_mac, mapped_by, old_ip_address, flow_discovered_time, endpoint_created_time, endpoint_updated_time
            ) = endpoint

            # 添加 Endpoint 信息
            subscriber_topo[subscriber_id]["subscriberEndpoints"]["endpoint_agg_group"] = endpoint_agg_group
            subscriber_topo[subscriber_id]["subscriberEndpoints"]["endpoints"].append({
                "endpoint_id": endpoint_id,
                "ip_address": ip_address,
                "ont_fsan": ont_fsan,
                "rg_fsan": rg_fsan,
                "rg_mac": rg_mac,
                "mapped_by": mapped_by,
                "old_ip_address": old_ip_address,
                "flow_discovered_time": flow_discovered_time,
                "endpoint_created_time": endpoint_created_time,
                "endpoint_updated_time": endpoint_updated_time
            })

        logger.info(f"Generated {len(subscriber_topo)} unique subscriber entries in subscriber_topo.")
        return list(subscriber_topo.values())

    except Exception as e:
        logger.error(f"An error occurred while fetching subscriber data: {e}")
        return []
