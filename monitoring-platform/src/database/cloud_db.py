def connect_to_cloud_db(config):
    """
    Establish a connection to the cloud database using the provided configuration.
    
    :param config: Dictionary containing cloud database configuration.
    :return: Connection object to the cloud database.
    """
    import psycopg2
    return psycopg2.connect(
        dbname=config['dbname'],
        user=config['user'],
        password=config['password'],
        host=config['host'],
        port=config['port']
    )

def fetch_data(query, cloud_conn):
    """
    Execute a query on the cloud database and fetch the results.
    
    :param query: SQL query to be executed.
    :param cloud_conn: Connection object to the cloud database.
    :return: Fetched data from the cloud database.
    """
    with cloud_conn.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()

def close_cloud_db_connection(cloud_conn):
    """
    Close the connection to the cloud database.
    
    :param cloud_conn: Connection object to the cloud database.
    """
    cloud_conn.close()