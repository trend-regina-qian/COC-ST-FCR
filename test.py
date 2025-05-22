import json, os
import configparser

def load_db_config(dbp_filepath):
    """
    从 .dbp 文件加载数据库配置
    :param dbp_filepath: .dbp 文件路径
    :return: 数据库配置字典
    """
    print(f"文件路径是否存在: {os.path.exists('./credentials/anchen-20250402.dbp')}")
    config = configparser.ConfigParser()
    with open(dbp_filepath, 'rb') as file:  # 指定编码为 ANSI (mbcs)
        content = file.read()

    # # 如果文件内容没有 [section]，动态添加
    # if not content.strip().startswith("["):
    #     content = "[database]\n" + content
        # 将字节数据解码为字符串
    decoded_content = content.decode('mbcs')  # ANSI 编码对应 'mbcs'
    print("读取的 .dbp 文件内容如下:")    
    print(decoded_content)

   # 检查是否有重复的键
    try:
        config.read_string(content)
    except configparser.DuplicateOptionError as e:
        raise ValueError(f"配置文件中存在重复的键: {e}")

    return {
        "dbname": config.get("database", "dbname"),
        "user": config.get("database", "user"),
        "password": config.get("database", "password"),
        "host": config.get("database", "host"),
        "port": config.get("database", "port")
    }

# 示例调用
db_config = load_db_config("./credentials/anchen-20250402.dbp")
print("数据库配置:", db_config)