-- Ensure device_topo table exists with the correct schema
CREATE TABLE IF NOT EXISTS device_topo (
    topo_id TEXT PRIMARY KEY,  -- Unique identifier for the topology
    rg_fsan TEXT NOT NULL,  -- RG FSAN
    rg_mac TEXT NOT NULL,  -- RG MAC address
    device_type TEXT NOT NULL CHECK (device_type IN ('Native', '2Box')),  -- Device type
    dhcp_IPv4 TEXT,  -- IPv4 address assigned via DHCP
    dhcp_IPv6 TEXT,  -- Comma-separated list of IPv6 addresses
    ip_address_family TEXT NOT NULL CHECK (ip_address_family IN ('IPv4', 'IPv6', 'Dual Stack')),  -- Address family
    parentont_fsan TEXT NOT NULL,  -- Renamed from ont_fsan
    parentolt_server TEXT NOT NULL,  -- Renamed from olt_server
    state TEXT,  -- Added field for up-down-state
    lease_first_acquired TIMESTAMP,  -- Added field for lease-first-acquired
    lease_expires TIMESTAMP,  -- Added field for lease-expires
    device_data JSONB  -- Full device data as JSON
);

-- Ensure subscriber_topo table exists with the correct schema
CREATE TABLE IF NOT EXISTS subscriber_topo (
    subscriber_id UUID PRIMARY KEY,
    subscriber_location_id TEXT NOT NULL,
    subscriber_name TEXT NOT NULL,
    subscriber_account TEXT,
    subscriber_created_time TIMESTAMP,
    subscriber_updated_time TIMESTAMP,
    subscriber_devices JSONB,  -- Store devices as JSON
    subscriber_services JSONB, -- Store services as JSON
    subscriber_endpoints JSONB -- Store endpoints as JSON
);

-- Ensure subscriber_endpoints table exists with the correct schema
CREATE TABLE IF NOT EXISTS subscriber_endpoints (
    endpoint_id UUID PRIMARY KEY,  -- Unique identifier for the endpoint
    subscriber_id UUID,  -- Added field for subscriber ID
    subscriber_location_id TEXT,  -- Added field for subscriber location ID
    ip_address TEXT,  -- IP address of the endpoint
    deleted BOOLEAN,  -- Indicates if the endpoint is deleted
    delete_time TIMESTAMP,  -- Timestamp when the endpoint was deleted
    ont_fsan TEXT,  -- ONT FSAN
    rg_fsan TEXT,  -- RG FSAN
    rg_mac TEXT,  -- RG MAC address
    mapped_by TEXT,  -- Mapping source
    old_ip_address TEXT,  -- Previous IP address
    flow_discovered_time TIMESTAMP,  -- Time when the flow was discovered
    endpoint_created_time TIMESTAMP,  -- Time when the endpoint was created
    endpoint_updated_time TIMESTAMP,  -- Time when the endpoint was last updated
    endpoint_agg_group TEXT  -- Aggregation group for the endpoint
);

-- Ensure ip_address_change_log table exists
CREATE TABLE IF NOT EXISTS ip_address_change_log (
    id SERIAL PRIMARY KEY,
    endpoint_id UUID NOT NULL,
    old_ip_address VARCHAR(45),
    new_ip_address VARCHAR(45),
    change_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Update the trigger function to log IP address changes
CREATE OR REPLACE FUNCTION log_ip_address_changes()
RETURNS TRIGGER AS $$
BEGIN
    -- Log only when ip_address changes
    IF NEW.ip_address IS DISTINCT FROM OLD.ip_address THEN
        INSERT INTO ip_address_change_log (endpoint_id, old_ip_address, new_ip_address, change_time)
        VALUES (NEW.endpoint_id, OLD.ip_address, NEW.ip_address, CURRENT_TIMESTAMP);
    END IF;
    RETURN NEW;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Error in trigger: %', SQLERRM;
    RETURN NULL;    
END;
$$ LANGUAGE plpgsql;


CREATE TABLE managed_endpoints (
    endpoint_id UUID PRIMARY KEY,
    agg_group TEXT,
    name VARCHAR(255),    
    mac_address VARCHAR(255),
    serial_number VARCHAR(255),
    cm_serial_number VARCHAR(255),
    subscriber_id UUID,
    org_id UUID,
    deleted BOOLEAN,
    ip_address TEXT,  -- IP address of the endpoint    
    old_ip_address TEXT,  -- Previous IP address  
    mapped_by TEXT,  -- Mapping source
    flow_discovered_time TIMESTAMP,
    create_time TIMESTAMP,
    update_time TIMESTAMP,
    endpoint_data JSONB,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Update the trigger to monitor changes in the managed_endpoints table
CREATE OR REPLACE FUNCTION update_last_updated_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = CURRENT_TIMESTAMP;
    RETURN NEW;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Error in trigger: %', SQLERRM;
    RETURN NULL;    
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_last_updated
BEFORE UPDATE ON managed_endpoints
FOR EACH ROW
EXECUTE FUNCTION update_last_updated_column();

-- Create a trigger on the managed_endpoints table
CREATE TRIGGER ip_address_change_trigger
AFTER UPDATE OF ip_address ON managed_endpoints
FOR EACH ROW
WHEN (OLD.ip_address IS DISTINCT FROM NEW.ip_address)
EXECUTE FUNCTION log_ip_address_changes();
