# task_logger.py
import asyncio
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from dataclasses import dataclass
from config.logger import logger


class TaskStatus(Enum):
    """任务执行状态"""

    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL_SUCCESS = "partial_success"
    SKIPPED = "skipped"


@dataclass
class TaskResult:
    """任务执行结果"""

    status: TaskStatus
    message: str
    data: Any = None
    success_count: int = 0
    failure_count: int = 0
    total_count: int = 0

    @property
    def is_success(self) -> bool:
        """判断任务是否完全成功"""
        return self.status == TaskStatus.SUCCESS

    @property
    def has_failures(self) -> bool:
        """判断任务是否有失败"""
        return self.failure_count > 0


class TaskLogger:
    """统一任务日志处理器"""

    def __init__(self, task_name: str):
        self.task_name = task_name
        self.success_count = 0
        self.failure_count = 0
        self.total_count = 0
        self.messages: List[str] = []
        self.start_time: Optional[float] = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.start_time = asyncio.get_event_loop().time()
        logger.info(f"🎯 开始执行任务: {self.task_name}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if exc_type:
            self.log_failure(f"任务执行异常: {exc_val}")
            logger.exception(f"任务 {self.task_name} 执行异常")

        execution_time = asyncio.get_event_loop().time() - self.start_time
        status = self._get_overall_status()

        logger.info(
            f"📊 任务 {self.task_name} 执行完成 - "
            f"状态: {status.value.upper()} - "
            f"成功: {self.success_count} - "
            f"失败: {self.failure_count} - "
            f"耗时: {execution_time:.2f}s"
        )

    def _get_overall_status(self) -> TaskStatus:
        """获取整体执行状态"""
        if self.failure_count == 0 and self.success_count > 0:
            return TaskStatus.SUCCESS
        elif self.success_count > 0 and self.failure_count > 0:
            return TaskStatus.PARTIAL_SUCCESS
        elif self.success_count == 0 and self.failure_count > 0:
            return TaskStatus.FAILED
        else:
            return TaskStatus.SKIPPED

    def log_success(self, message: str, data: Any = None) -> None:
        """记录成功日志"""
        self.success_count += 1
        self.total_count += 1
        logger.info(f"✅ {message}")
        self.messages.append(f"✅ {message}")

    def log_failure(self, message: str, data: Any = None) -> None:
        """记录失败日志"""
        self.failure_count += 1
        self.total_count += 1
        logger.error(f"❌ {message}")
        self.messages.append(f"❌ {message}")

    def log_warning(self, message: str, data: Any = None) -> None:
        """记录警告日志"""
        logger.warning(f"⚠️ {message}")
        self.messages.append(f"⚠️ {message}")

    def log_info(self, message: str) -> None:
        """记录信息日志"""
        logger.info(f"ℹ️ {message}")
        self.messages.append(f"ℹ️ {message}")

    def get_result(self) -> TaskResult:
        """获取任务执行结果"""
        status = self._get_overall_status()

        if self.total_count == 0:
            summary = f"任务 '{self.task_name}' 未执行任何操作"
        else:
            summary = (
                f"任务 '{self.task_name}' 执行完成 - "
                f"成功: {self.success_count}, 失败: {self.failure_count}, 总计: {self.total_count}"
            )

        detailed_message = f"{summary}\n" + "\n".join(self.messages)

        return TaskResult(
            status=status,
            message=detailed_message,
            data={
                "task_name": self.task_name,
                "messages": self.messages,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "total_count": self.total_count,
            },
            success_count=self.success_count,
            failure_count=self.failure_count,
            total_count=self.total_count,
        )


async def execute_task_with_logging(
    task_name: str, task_func: Callable, *args, **kwargs
) -> TaskResult:
    """
    使用统一日志处理执行任务

    Args:
        task_name: 任务名称
        task_func: 要执行的任务函数
        *args, **kwargs: 任务函数参数

    Returns:
        TaskResult: 任务执行结果
    """
    async with TaskLogger(task_name) as task_logger:
        try:
            result = await task_func(*args, **kwargs)

            if isinstance(result, TaskResult):
                # 以返回的 TaskResult 为权威结果合并，保留原始 status/message/data/计数。
                if result.status == TaskStatus.PARTIAL_SUCCESS:
                    # 明确校验成功+失败==总数，不一致返回可诊断错误而非降级为 SKIPPED
                    if (
                        result.success_count + result.failure_count
                        != result.total_count
                    ):
                        return TaskResult(
                            status=TaskStatus.FAILED,
                            message=(
                                f"任务 '{task_name}' 返回 PARTIAL_SUCCESS 但计数不一致"
                                f"（成功 {result.success_count} + 失败 {result.failure_count}"
                                f" != 总数 {result.total_count}）"
                            ),
                            data=result.data,
                        )

                # 仅当返回的计数缺省时，按一次顶层任务事件补齐计数
                if result.total_count == 0:
                    if result.status == TaskStatus.SUCCESS:
                        task_logger.log_success(result.message)
                    elif result.status == TaskStatus.FAILED:
                        task_logger.log_failure(result.message)
                    elif result.status == TaskStatus.PARTIAL_SUCCESS:
                        task_logger.log_success(result.message)
                        task_logger.log_failure(result.message)
                    summary = task_logger.get_result()
                    merged = TaskResult(
                        status=result.status,
                        message=result.message,
                        data=result.data,
                        success_count=summary.success_count,
                        failure_count=summary.failure_count,
                        total_count=summary.total_count,
                    )
                    return merged

                # 计数完整：原样返回业务数据，不重新压缩成一条事件
                return result
            if isinstance(result, str):
                task_logger.log_failure(result)
            else:
                task_logger.log_success(f"任务 {task_name} 执行完成")

            return task_logger.get_result()

        except Exception as e:
            task_logger.log_failure(f"任务 {task_name} 执行异常: {str(e)}")
            return task_logger.get_result()
