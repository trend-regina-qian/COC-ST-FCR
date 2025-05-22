# Monitoring Platform

## Overview
The Monitoring Platform is a comprehensive solution designed to automate the monitoring of device and subscriber topology data. It connects to both local and cloud databases to fetch, store, and monitor changes in the data, ensuring consistency, synchronization, and reliability in network management.

---

## Features
- **Data Collection**:
  - Fetches device topology data from OLT servers.
  - Retrieves subscriber topology data from cloud databases.
- **Endpoint Synchronization**:
  - Synchronizes endpoints between cloud and local databases.
- **Monitoring**:
  - Tracks FSAN consistency among subscribers.
  - Monitors IP synchronization between devices and endpoints.
  - Detects unbound endpoints.
  - Measures data synchronization delays.
  - Tracks IP address changes for subscribers.
- **Metrics Export**:
  - Exposes monitoring results as Prometheus metrics.
- **Visualization and Alerting**:
  - Integrates with Grafana for real-time visualization and alerting.

---

## Project Structure
```
monitoring-platform
├── src
│   ├── main.py                  # Entry point of the application
│   ├── config
│   │   └── config.ini           # Configuration settings for databases and servers
│   ├── database
│   │   ├── local_db.py          # Local database interactions
│   │   └── cloud_db.py          # Cloud database interactions
│   ├── fetch_topo
│   │   ├── fetch_device_data.py  # Functions to fetch device topology data
│   │   └── fetch_subscriber_data.py # Functions to fetch subscriber topology data
│   ├── monitoring
│   │   ├── monitoring_checks.py  # Core monitoring checks implementation
│   │   ├── metrics_exporter.py   # Prometheus metrics exporter
│   │   └── prometheus_alerts.yaml # Prometheus alert rules
│   └── utils
│       └── helpers.py            # Utility functions for various tasks
├── requirements.txt              # Project dependencies
├── README.md                     # Project documentation
└── .gitignore                    # Files and directories to ignore in version control
```

---

## Installation

1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   ```

2. **Navigate to the Project Directory**:
   ```bash
   cd monitoring-platform
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## Usage

To run the application, execute the following command:
```bash
python src/main.py
```

---

## Configuration

Update the `src/config/config.ini` file with the following details:
- **Local Database**:
  - `local_db_name`, `local_db_user`, `local_db_password`, `local_db_host`, `local_db_port`.
- **Cloud Database**:
  - `cloud_db_name`, `cloud_db_user`, `cloud_db_password`, `cloud_db_host`, `cloud_db_port`.
- **OLT Server**:
  - `olt_server_ip`, `olt_server_username`, `olt_server_password`.

---

## Monitoring Implementation

The monitoring platform performs five core monitoring checks. Below is a detailed explanation of each check, including its logic, data flow, and logging.

### **1. Device Binding Consistency**

#### **Objective**:
Ensure FSAN consistency between `subscriberDevices` and `subscriberEndpoints`.

#### **Data Flow**:
1. Fetch device topology from the `device_topo` table.
2. Fetch subscriber topology from the `subscriber_topo` table.
3. Extract FSANs from `subscriberDevices` and `subscriberEndpoints`.

#### **Logic**:
- Compare FSANs in `subscriberDevices` and `subscriberEndpoints`.
- Identify mismatched FSANs:
  - FSANs in `subscriberDevices` but not in `subscriberEndpoints`.
  - FSANs in `subscriberEndpoints` but not in `subscriberDevices`.

#### **Logging**:
- Logs mismatched FSANs with details.
- Example:
  ```
  INFO:root:Subscriber <subscriber_id>: FSANs in subscriberDevices but not in subscriberEndpoints: <new_fsans>
  INFO:root:Subscriber <subscriber_id>: FSANs in subscriberEndpoints but not in subscriberDevices: <removed_fsans>
  ```

---

### **2. IP Synchronization**

#### **Objective**:
Verify IP synchronization between `device_topo` and `subscriber_endpoints`.

#### **Data Flow**:
1. Fetch IPs from `device_topo` and `subscriber_endpoints`.
2. Normalize IPs by removing subnet masks and treating `None` or `N/A` as equivalent.

#### **Logic**:
- Compare IPs in `device_topo` and `subscriber_endpoints`.
- Identify unsynced IPs:
  - IPs missing on devices.
  - IPs missing on endpoints.

#### **Logging**:
- Logs unsynced IPs with details.
- Example:
  ```
  INFO:root:RG MAC <rg_mac>, IP <ip>: IP synchronization status is unsynced (missing on device).
  INFO:root:RG MAC <rg_mac>, IP <ip>: IP synchronization status is unsynced (missing on endpoint).
  ```

---

### **3. Endpoint Binding Status**

#### **Objective**:
Detect unbound endpoints in `managed_endpoints`.

#### **Data Flow**:
1. Fetch endpoints from `managed_endpoints` where `mac_address` or `subscriber_id` is `NULL`.

#### **Logic**:
- Identify endpoints with missing `mac_address` or `subscriber_id`.

#### **Logging**:
- Logs unbound endpoints with details.
- Example:
  ```
  INFO:root:Endpoint ID <endpoint_id>: Binding status is unbound.
  ```

---

### **4. Data Synchronization Delay**

#### **Objective**:
Measure delays between `device_topo` and `subscriber_endpoints`.

#### **Data Flow**:
1. Fetch timestamps from `device_topo` and `subscriber_endpoints`.
2. Calculate delays as the difference between `endpoint_created_time` and `lease_first_acquired`.

#### **Logic**:
- Identify delays in data synchronization.

#### **Logging**:
- Logs delays with details.
- Example:
  ```
  INFO:root:Topo ID <topo_id>: Data synchronization delay is <delay> seconds.
  ```

---

### **5. IP Address Changes**

#### **Objective**:
Track changes in `ip_address` in `managed_endpoints`.

#### **Data Flow**:
1. Fetch endpoints from `ip_address_change_log`.

#### **Logic**:
- Detect changes in `ip_address` and log them.

#### **Logging**:
- Logs IP changes with details.
- Example:
  ```
  INFO:root:Endpoint ID <endpoint_id>: IP address change detected.
  ```

---

## Metrics Exporter

- **File**: `metrics_exporter.py`
  - Exposes metrics for Prometheus.
  - Metrics include:
    - `device_binding_inconsistencies`
    - `ip_sync_issues`
    - `endpoint_binding_issues`
    - `data_sync_delays`
    - `endpoint_ip_changes`

---

## Prometheus Configuration

- **File**: `prometheus_alerts.yaml`
  - Defines alert rules for critical metrics.
  - Example:
    ```yaml
    groups:
      - name: Monitoring Alerts
        rules:
          - alert: HighDataSyncDelay
            expr: data_sync_delays > 300
            for: 5m
            labels:
              severity: warning
            annotations:
              summary: "High data synchronization delay detected"
              description: "Data synchronization delay is above 300 seconds for more than 5 minutes."
    ```

---

## Testing

### **1. Database Trigger**
- Update an IP address in the `managed_endpoints` table.
- Verify that a record is created in the `ip_address_change_log` table.

### **2. Metrics Exporter**
- Run the `metrics_exporter.py` script.
- Confirm that metrics are exposed at `http://localhost:8000/metrics`.

### **3. Prometheus Alerts**
- Simulate IP address changes or high data sync delays.
- Verify that Prometheus alerts are triggered as expected.

---

## Visualization and Alerting

### **Grafana Integration**
1. **Add Prometheus as a Data Source**:
   - URL: `http://localhost:8000`.
2. **Create Dashboards**:
   - Add panels for each metric:
     - `device_binding_inconsistencies`
     - `ip_sync_issues`
     - `endpoint_binding_issues`
     - `data_sync_delays`
     - `endpoint_ip_changes`
3. **Configure Alerts**:
   - Set thresholds for critical metrics and configure notifications.

---

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

---

## License

This project is licensed under the MIT License. See the LICENSE file for details.