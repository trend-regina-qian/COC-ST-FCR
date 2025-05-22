import logging
from netmiko import ConnectHandler
import csv
import re

def ssh_connect_and_execute_commands(ip, username, password, commands, device_type="cisco_ios"):
    """
    使用 Netmiko 连接到网络设备并执行命令
    :param ip: 设备 IP 地址
    :param username: SSH 用户名
    :param password: SSH 密码
    :param commands: 要执行的命令列表
    :param device_type: 设备类型（默认为 cisco_ios）
    :return: 命令输出的字典
    """
    try:
        # 配置设备连接信息
        device = {
            "host": ip,
            "username": username,
            "password": password,
            "device_type": device_type
        }

        # 使用 Netmiko 连接到设备
        with ConnectHandler(**device) as connection:
            results = {}
            for command in commands:
                # 执行命令并获取输出
                output = connection.send_command(command)
                results[command] = output
            return results
    except Exception as e:
        logging.error(f"连接失败: {e}")
        return {}

# 解析 L3 Hosts 数据
def parse_l3_hosts(output):
    """
    解析 show l3-hosts 输出数据
    :param output: show l3-hosts 命令输出
    :return: 解析后的数据列表
    """
    pattern = (
        r"l3-host vlan (\d+) ip (\S+)\n"
        r"\s+mask\s+(\S+)\n"
        r"\s+interface\s+(\S+)\n"
        r"\s+mac\s+(\S+)\n"
        r"\s+dhcp-server\s+(\S+)\n"
        r"\s+gateway1\s+(\S+)\n"
        r"\s+host-type\s+(\S+)\n"
        r"\s+up-down-state\s+(\S+)\n"
        r"\s+lease-expires\s+(\S+)\n"
        r"\s+lease-renewed\s+(\S+)\n"
        r"\s+lease-first-acquired\s+(\S+)"
    )
    matches = re.findall(pattern, output)
    
    parsed_data = []
    for match in matches:
        parsed_data.append({
            "vlan": match[0],
            "ip": match[1],
            "mask": match[2],
            "interface": match[3],
            "mac": match[4],
            "dhcp_server": match[5],
            "gateway1": match[6],
            "host_type": match[7],
            "up_down_state": match[8],
            "lease_expires": match[9],
            "lease_renewed": match[10],
            "lease_first_acquired": match[11]
        })
    return parsed_data

# 解析 DHCPv6 数据
def parse_dhcpv6(output):
    """
    解析 show dhcpv6 输出数据
    :param output: show dhcpv6 命令输出
    :return: 解析后的数据列表
    """
    pattern = (
        r"(\d+)\s+"  # VLAN
        r"([\da-fA-F:]+/\d+)\s+"  # IP (IPv6 with prefix)
        r"(\S+)\s+"  # INTERFACE
        r"(-|[\da-fA-F:]+)\s+"  # INNER VLAN (can be '-' or a MAC)
        r"([\da-fA-F:]+)\s+"  # MAC
        r"([\da-fA-F:]+|::)\s+"  # DHCP SERVER (can be '::' or a MAC)
        r"([\d\-T:]+)\s+"  # LEASE EXPIRES (timestamp)
        r"([\da-fA-F:]+)"  # DHCPV6 SERVER MAC
    )
    matches = re.findall(pattern, output)
    
    parsed_data = []
    for match in matches:
        parsed_data.append({
            "vlan": match[0],
            "ip": match[1],
            "interface": match[2],
            "inner_vlan": match[3],  # INNER VLAN or '-'
            "mac": match[4],
            "dhcp_server": match[5],  # DHCP SERVER (can be '::')
            "lease_expires": match[6],
            "dhcpv6_server_mac": match[7]
        })
    return parsed_data

def determine_topology_type(ont_fsan, rg_fsan):
    if ont_fsan == rg_fsan:
        return "Native"
    else:
        return "2Box"

def load_rg_fsan_from_csv(csv_filepath):
    """
    从CSV文件加载rg_fsan、topo_id和ip_address_family映射
    :param csv_filepath: CSV文件路径
    :return: RG MAC到RG FSAN、topo_id和ip_address_family的映射字典
    """
    rg_fsan_map = {}
    with open(csv_filepath, mode='r', encoding='utf-8-sig') as csv_file:  # 确保正确编码
        # Remove trailing commas from each line
        cleaned_lines = (line.strip().rstrip(',') for line in csv_file)
        reader = csv.DictReader(cleaned_lines)
        for row in reader:
            rg_mac = row.get("RG MAC")  # 使用新的列名
            rg_fsan = row.get("RG FSAN")  # 使用新的列名
            topo_id = row.get("Topology ID")  # 新增列名
            ip_address_family = row.get("IP Address Family")  # 新增列名
            if rg_mac and rg_fsan and topo_id and ip_address_family:
                rg_fsan_map[rg_mac.strip().upper()] = {
                    "rg_fsan": rg_fsan.strip(),
                    "topo_id": topo_id.strip(),
                    "ip_address_family": ip_address_family.strip()
                }
    return rg_fsan_map

def extract_rg_macs(data, vlan_filter="1985"):
    """
    从数据中提取符合 VLAN 条件的 RG MAC 地址
    :param data: 数据列表（如 l3_hosts_data 或 dhcpv6_data）
    :param vlan_filter: VLAN 过滤条件
    :return: RG MAC 地址集合
    """
    rg_macs = set()
    for entry in data:
        if entry["vlan"] == vlan_filter:
            rg_macs.add(entry["mac"].strip().upper())
    return rg_macs

def fetch_device_topo(olt_server_config):
    if not olt_server_config:
        raise ValueError("Missing required argument: 'olt_server_config'")
    
    # Connect to OLT server and execute commands
    olt_ip = olt_server_config['ip']
    olt_username = olt_server_config['username']
    olt_password = olt_server_config['password']
    commands = ["show l3-hosts", "show dhcpv6"]
    
    logging.info("Connecting to OLT server to fetch device data...")
    try:
        command_outputs = ssh_connect_and_execute_commands(olt_ip, olt_username, olt_password, commands)
    except Exception as e:
        logging.error(f"Connection failed: {e}")
        return []  # Return an empty list to avoid further errors
    
    if not command_outputs:  # Check if command outputs were successfully retrieved
        logging.error("Failed to retrieve command outputs. Please check connection settings.")
        return []  # Return an empty list to avoid further errors
    
    logging.info("Parsing command outputs...")
    # Parse command outputs
    l3_hosts_data = parse_l3_hosts(command_outputs.get("show l3-hosts", ""))
    dhcpv6_data = parse_dhcpv6(command_outputs.get("show dhcpv6", ""))
    
    # Debug parsed data
    logging.debug(f"L3 Hosts Data: {l3_hosts_data}")
    logging.debug(f"DHCPv6 Data: {dhcpv6_data}")
    
    # Extract all RG MACs, limited to VLAN 1985
    all_rg_macs = extract_rg_macs(l3_hosts_data).union(extract_rg_macs(dhcpv6_data))
    logging.info(f"Extracted {len(all_rg_macs)} RG MAC addresses.")
    
    # Load rg_fsan, topo_id, and ip_address_family mappings from CSV
    csv_filepath = "./csv/deviceInfo.csv"
    rg_fsan_map = load_rg_fsan_from_csv(csv_filepath)
    
    # Debug loaded CSV data
    logging.debug(f"RG FSAN Map: {rg_fsan_map}")
    
    # Generate device_topo table
    device_topo = []
    for rg_mac in all_rg_macs:
        # Find matching entry in l3_hosts_data
        l3_host = next((host for host in l3_hosts_data if host["mac"].strip().upper() == rg_mac), None)
        parentont_fsan = l3_host["interface"].split('/')[0].strip().upper() if l3_host and l3_host["interface"] else None
        ipv4 = l3_host["ip"] if l3_host else None
        state = l3_host["up_down_state"] if l3_host else None
        lease_first_acquired = l3_host["lease_first_acquired"] if l3_host else None
        lease_expires = l3_host["lease_expires"] if l3_host else None
        
        # Find matching entry in dhcpv6_data
        ipv6_list = [entry["ip"] for entry in dhcpv6_data if entry["mac"].strip().upper() == rg_mac]
        
        # Get rg_fsan, topo_id, and ip_address_family
        rg_fsan_entry = rg_fsan_map.get(rg_mac, {"rg_fsan": None, "topo_id": None, "ip_address_family": None})
        rg_fsan = rg_fsan_entry["rg_fsan"]
        topo_id = rg_fsan_entry["topo_id"]
        
        # Normalize ip_address_family to match the database schema
        ip_address_family = rg_fsan_entry["ip_address_family"]
        if ip_address_family:
            ip_address_family = ip_address_family.strip().title()  # Normalize to title case (e.g., "Dual Stack")
            if ip_address_family == "Ipv4":
                ip_address_family = "IPv4"
            elif ip_address_family == "Ipv6":
                ip_address_family = "IPv6"
        
        # Determine topo type
        device_type = "Native" if parentont_fsan and rg_fsan and parentont_fsan == rg_fsan else "2Box"
        
        # Add to device_topo table, ensuring all fields have default values
        device_topo.append({
            "topo_id": topo_id if topo_id else "UNKNOWN",
            "rg_fsan": rg_fsan if rg_fsan else "UNKNOWN",
            "rg_mac": rg_mac if rg_mac else "UNKNOWN",
            "device_type": device_type if device_type else "UNKNOWN",
            "dhcp_IPv4": ipv4 if ipv4 else "N/A",
            "dhcp_IPv6": ",".join(ipv6_list) if ipv6_list else "N/A",
            "parentont_fsan": parentont_fsan if parentont_fsan else "UNKNOWN",
            "parentolt_server": olt_ip,
            "ip_address_family": ip_address_family if ip_address_family else "UNKNOWN",
            "state": state if state else "UNKNOWN",
            "lease_first_acquired": lease_first_acquired if lease_first_acquired else None,
            "lease_expires": lease_expires if lease_expires else None
        })
    
    logging.info(f"Generated {len(device_topo)} device topology records.")
    return device_topo
