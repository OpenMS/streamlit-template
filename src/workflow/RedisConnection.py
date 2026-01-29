"""
Redis Connection Factory for Scalable Deployments

Supports multiple Redis deployment modes:
- standalone: Single Redis instance (default, backward compatible)
- cluster: Redis Cluster for horizontal scaling across multiple shards
- sentinel: Redis Sentinel for high availability with automatic failover

Configuration via environment variables:
- REDIS_MODE: 'standalone' | 'cluster' | 'sentinel' (default: 'standalone')
- REDIS_URL: Connection URL for standalone mode (default: redis://localhost:6379/0)
- REDIS_CLUSTER_NODES: Comma-separated list of cluster nodes (e.g., "host1:7000,host2:7001")
- REDIS_SENTINEL_HOSTS: Comma-separated list of sentinel hosts (e.g., "host1:26379,host2:26379")
- REDIS_SENTINEL_MASTER: Name of the sentinel master (default: 'mymaster')
- REDIS_PASSWORD: Optional password for authentication
- REDIS_SSL: Enable SSL/TLS ('true' or 'false', default: 'false')
- REDIS_POOL_MAX_CONNECTIONS: Max connections in pool (default: 10)
"""

import os
import logging
from typing import Optional, Union, List, Tuple
from enum import Enum
from dataclasses import dataclass


logger = logging.getLogger(__name__)


class RedisMode(Enum):
    """Redis deployment modes"""
    STANDALONE = "standalone"
    CLUSTER = "cluster"
    SENTINEL = "sentinel"


@dataclass
class RedisConfig:
    """Redis connection configuration"""
    mode: RedisMode
    url: str = "redis://localhost:6379/0"
    cluster_nodes: List[Tuple[str, int]] = None
    sentinel_hosts: List[Tuple[str, int]] = None
    sentinel_master: str = "mymaster"
    password: Optional[str] = None
    ssl: bool = False
    pool_max_connections: int = 10
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    health_check_interval: int = 30

    def __post_init__(self):
        if self.cluster_nodes is None:
            self.cluster_nodes = []
        if self.sentinel_hosts is None:
            self.sentinel_hosts = []


def _parse_host_port_list(value: str) -> List[Tuple[str, int]]:
    """Parse comma-separated host:port list into tuples"""
    if not value:
        return []

    result = []
    for item in value.split(","):
        item = item.strip()
        if ":" in item:
            host, port = item.rsplit(":", 1)
            result.append((host, int(port)))
        else:
            # Default ports: 6379 for Redis, 26379 for Sentinel
            result.append((item, 6379))
    return result


def get_config_from_env() -> RedisConfig:
    """
    Build Redis configuration from environment variables.

    Returns:
        RedisConfig object with settings from environment
    """
    mode_str = os.environ.get("REDIS_MODE", "standalone").lower()

    try:
        mode = RedisMode(mode_str)
    except ValueError:
        logger.warning(f"Invalid REDIS_MODE '{mode_str}', falling back to standalone")
        mode = RedisMode.STANDALONE

    config = RedisConfig(
        mode=mode,
        url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        cluster_nodes=_parse_host_port_list(os.environ.get("REDIS_CLUSTER_NODES", "")),
        sentinel_hosts=_parse_host_port_list(os.environ.get("REDIS_SENTINEL_HOSTS", "")),
        sentinel_master=os.environ.get("REDIS_SENTINEL_MASTER", "mymaster"),
        password=os.environ.get("REDIS_PASSWORD"),
        ssl=os.environ.get("REDIS_SSL", "false").lower() == "true",
        pool_max_connections=int(os.environ.get("REDIS_POOL_MAX_CONNECTIONS", "10")),
    )

    return config


class RedisConnectionFactory:
    """
    Factory for creating Redis connections based on deployment mode.

    Supports standalone, cluster, and sentinel modes with connection pooling.
    """

    def __init__(self, config: Optional[RedisConfig] = None):
        """
        Initialize the connection factory.

        Args:
            config: Optional RedisConfig. If not provided, reads from environment.
        """
        self.config = config or get_config_from_env()
        self._connection = None
        self._pool = None

    def get_connection(self) -> Union["Redis", "RedisCluster"]:
        """
        Get a Redis connection based on configured mode.

        Returns:
            Redis or RedisCluster connection object

        Raises:
            ConnectionError: If unable to connect to Redis
            ImportError: If required Redis packages are not installed
        """
        if self._connection is not None:
            return self._connection

        if self.config.mode == RedisMode.CLUSTER:
            self._connection = self._create_cluster_connection()
        elif self.config.mode == RedisMode.SENTINEL:
            self._connection = self._create_sentinel_connection()
        else:
            self._connection = self._create_standalone_connection()

        return self._connection

    def _create_standalone_connection(self) -> "Redis":
        """Create a standalone Redis connection with connection pool"""
        from redis import Redis, ConnectionPool

        # Create connection pool for better resource management
        self._pool = ConnectionPool.from_url(
            self.config.url,
            max_connections=self.config.pool_max_connections,
            socket_timeout=self.config.socket_timeout,
            socket_connect_timeout=self.config.socket_connect_timeout,
            retry_on_timeout=self.config.retry_on_timeout,
            health_check_interval=self.config.health_check_interval,
        )

        connection = Redis(connection_pool=self._pool)

        # Verify connection
        connection.ping()
        logger.info("Connected to Redis (standalone mode)")

        return connection

    def _create_cluster_connection(self) -> "RedisCluster":
        """Create a Redis Cluster connection"""
        from redis.cluster import RedisCluster, ClusterNode

        if not self.config.cluster_nodes:
            raise ValueError(
                "REDIS_CLUSTER_NODES must be set for cluster mode "
                "(e.g., 'host1:7000,host2:7001,host3:7002')"
            )

        # Build startup nodes
        startup_nodes = [
            ClusterNode(host, port)
            for host, port in self.config.cluster_nodes
        ]

        connection = RedisCluster(
            startup_nodes=startup_nodes,
            password=self.config.password,
            ssl=self.config.ssl,
            socket_timeout=self.config.socket_timeout,
            socket_connect_timeout=self.config.socket_connect_timeout,
            retry_on_timeout=self.config.retry_on_timeout,
            health_check_interval=self.config.health_check_interval,
        )

        # Verify connection
        connection.ping()
        logger.info(f"Connected to Redis Cluster ({len(self.config.cluster_nodes)} nodes)")

        return connection

    def _create_sentinel_connection(self) -> "Redis":
        """Create a Redis connection through Sentinel for high availability"""
        from redis import Redis
        from redis.sentinel import Sentinel

        if not self.config.sentinel_hosts:
            raise ValueError(
                "REDIS_SENTINEL_HOSTS must be set for sentinel mode "
                "(e.g., 'sentinel1:26379,sentinel2:26379')"
            )

        # Create Sentinel connection
        sentinel = Sentinel(
            self.config.sentinel_hosts,
            socket_timeout=self.config.socket_timeout,
            password=self.config.password,
            sentinel_kwargs={"password": self.config.password} if self.config.password else {},
        )

        # Get master connection from Sentinel
        connection = sentinel.master_for(
            self.config.sentinel_master,
            socket_timeout=self.config.socket_timeout,
            password=self.config.password,
            retry_on_timeout=self.config.retry_on_timeout,
        )

        # Verify connection
        connection.ping()
        logger.info(f"Connected to Redis via Sentinel (master: {self.config.sentinel_master})")

        return connection

    def get_health_info(self) -> dict:
        """
        Get health information for the Redis connection.

        Returns:
            Dictionary with health status and mode-specific metrics
        """
        try:
            conn = self.get_connection()

            base_info = {
                "status": "healthy",
                "mode": self.config.mode.value,
            }

            if self.config.mode == RedisMode.CLUSTER:
                return self._get_cluster_health_info(conn, base_info)
            elif self.config.mode == RedisMode.SENTINEL:
                return self._get_sentinel_health_info(conn, base_info)
            else:
                return self._get_standalone_health_info(conn, base_info)

        except Exception as e:
            return {
                "status": "unhealthy",
                "mode": self.config.mode.value,
                "error": str(e),
            }

    def _get_standalone_health_info(self, conn, base_info: dict) -> dict:
        """Get health info for standalone mode"""
        info = conn.info()
        base_info.update({
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory_human", "unknown"),
            "uptime_days": info.get("uptime_in_days", 0),
            "role": info.get("role", "unknown"),
        })
        return base_info

    def _get_cluster_health_info(self, conn, base_info: dict) -> dict:
        """Get health info for cluster mode"""
        # Get cluster info
        cluster_info = conn.cluster_info()
        cluster_nodes = conn.cluster_nodes()

        # Count node types
        masters = sum(1 for n in cluster_nodes.values() if "master" in n.get("flags", ""))
        replicas = sum(1 for n in cluster_nodes.values() if "slave" in n.get("flags", ""))

        base_info.update({
            "cluster_state": cluster_info.get("cluster_state", "unknown"),
            "cluster_slots_assigned": cluster_info.get("cluster_slots_assigned", 0),
            "cluster_slots_ok": cluster_info.get("cluster_slots_ok", 0),
            "cluster_known_nodes": cluster_info.get("cluster_known_nodes", 0),
            "master_nodes": masters,
            "replica_nodes": replicas,
        })
        return base_info

    def _get_sentinel_health_info(self, conn, base_info: dict) -> dict:
        """Get health info for sentinel mode"""
        info = conn.info()
        base_info.update({
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory_human", "unknown"),
            "role": info.get("role", "unknown"),
            "master_name": self.config.sentinel_master,
            "connected_slaves": info.get("connected_slaves", 0),
        })
        return base_info

    def close(self) -> None:
        """Close the Redis connection and connection pool"""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

        if self._pool is not None:
            try:
                self._pool.disconnect()
            except Exception:
                pass
            self._pool = None


# Global connection factory instance (lazy initialization)
_factory: Optional[RedisConnectionFactory] = None


def get_redis_connection() -> Union["Redis", "RedisCluster"]:
    """
    Get a Redis connection using the global factory.

    Returns:
        Redis or RedisCluster connection
    """
    global _factory
    if _factory is None:
        _factory = RedisConnectionFactory()
    return _factory.get_connection()


def get_redis_health() -> dict:
    """
    Get health information using the global factory.

    Returns:
        Dictionary with health status
    """
    global _factory
    if _factory is None:
        _factory = RedisConnectionFactory()
    return _factory.get_health_info()


def get_redis_mode() -> RedisMode:
    """
    Get the current Redis mode.

    Returns:
        RedisMode enum value
    """
    global _factory
    if _factory is None:
        _factory = RedisConnectionFactory()
    return _factory.config.mode
