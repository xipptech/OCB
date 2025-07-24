
from dataclasses import dataclass, fields
from ..tools import config
from prometheus_client import (
    Counter, 
    Gauge, 
    Histogram,
    multiprocess,
    CollectorRegistry,
)
import threading
import os
from typing import Literal, Optional

@dataclass
class MetricData:
    @classmethod
    def labels(cls):
        return [f.name for f in fields(cls)]
    
    def merged_with(self, **kw):
        return self.__class__(**{**self.__dict__, **kw})


class PrometheusObserver:

    is_initialized = False
    _registry = None

    @classmethod
    def _init(cls):
        registry = cls.get_registry()

        cls.request_count = Counter(
            "http_requests_total",
            "Total HTTP Requests",
            cls.RequestMetadata.labels(),
            registry=registry,
        )
        cls.request_latency = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds",
            cls.RequestMetadata.labels(),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 100),
            registry=registry,
        )
        cls.exception_count = Counter(
            "http_exceptions_total",
            "Total exceptions encountered",
            cls.RequestMetadata.labels(),
            registry=registry,
        )
        cls.in_progress_requests = Gauge(
            "http_requests_in_progress",
            "Number of HTTP requests currently in progress",
            registry=registry,
        )
        cls.is_initialized = True
        cls.data_queue = dict()
    
    @dataclass
    class RequestMetadata(MetricData):
        path: str = None
        http_method: str = None
        model: Optional[str] = None
        method: Optional[str] = None
        service: Optional[Literal["common", "db", "object"]] = None
        exception_type: Optional[str] = None
    
    @dataclass
    class PerformanceMetrics(MetricData):
        elapsed_time: float = 0
        database_time: float = 0
        query_count: int = 0
    
    @classmethod
    def get_registry(cls):
        if cls._registry is not None:
            return cls._registry
        registry = CollectorRegistry()
        if config["workers"]:
            multiprocess.MultiProcessCollector(registry, config["prometheus_multiproc_dir"])
        cls._registry = registry
        return registry

    @classmethod
    def add(cls, data):
        if not config["prometheus_enable"]:
            return
        if not cls.is_initialized:
            cls._init()
        cls.data_queue[type(data)] = data

    @classmethod    
    def update(cls, klass, **data):
        if not config["prometheus_enable"]:
            return
        if not cls.is_initialized:
            cls._init()
        if klass not in cls.data_queue:
            raise ValueError(f"No data found for {klass}")
        cls.data_queue[klass] = cls.data_queue[klass].merged_with(**data)
    
    @classmethod
    def update_with_exception(cls, exception):
        cls.update(
            cls.RequestMetadata, 
            exception_type=(
                type(exception).__module__ + "." + type(exception).__name__
                if type(exception).__module__
                else type(exception).__name__
            )
        )
    
    @classmethod
    def start_request(cls):
        if not config["prometheus_enable"]:
            return
        if not cls.is_initialized:
            cls._init()
        cls.in_progress_requests.inc()
    
    @classmethod
    def end_request(cls):
        if not config["prometheus_enable"]:
            return
        cls.flush()
        cls.in_progress_requests.dec()
    
    @classmethod
    def flush(cls):
        def sanitize_labels(d: dict) -> dict:
            return {k: (v if v is not None else "") for k, v in d.items()}

        def performance_metrics(metric: PrometheusObserver.PerformanceMetrics):
            cls.request_latency.labels(
                **sanitize_labels(request.__dict__)
            ).observe(metric.elapsed_time)

        def request_metrics(metric: PrometheusObserver.RequestMetadata):
            cls.request_count.labels(**sanitize_labels(metric.__dict__)).inc()
            if metric.exception_type:
                cls.exception_count.labels(**sanitize_labels(metric.__dict__)).inc()

        handlers = {
            cls.PerformanceMetrics: performance_metrics,
            cls.RequestMetadata: request_metrics,
        }
        request = cls.data_queue[cls.RequestMetadata]
        for klass, metric in cls.data_queue.items():
            if klass in handlers:
                handlers[klass](metric)

    @classmethod
    def clear_registry(cls):
        dir = config["prometheus_multiproc_dir"]
        if not dir:
            return
        for f in os.listdir(dir):
            path = os.path.join(dir, f)
            if os.path.isfile(path):
                os.remove(path)
    