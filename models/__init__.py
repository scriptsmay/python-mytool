from config import logger
from .data_models import ConfigDataManager, ProjectEnv, ConfigData

# 通过管理器加载配置
ConfigDataManager.load_config()

# 使用管理器中的配置数据
project_config = ConfigDataManager.config_data

# 添加验证
if project_config is None:
    logger.error("❌ 配置加载失败，使用默认配置")
    project_config = ConfigData()
    ConfigDataManager.config_data = project_config

logger.info(
    f"✅ 配置加载成功 - 版本: {project_config.version},"
    f"用户数: {len(project_config.users)}, "
    f"weibo_cookie: {'已配置' if project_config.weibo_cookie else '未配置'}"
    f"\n   推送配置: enable: {project_config.push_config.enable}, servers: {project_config.push_config.push_servers}"
)

project_env = ProjectEnv()

from .data_models import *
