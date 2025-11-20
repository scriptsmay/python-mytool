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
    f"✅ 配置加载成功 - 版本: {project_config.version}, 用户数: {len(project_config.users)}"
)

project_env = ProjectEnv()

from .data_models import *
