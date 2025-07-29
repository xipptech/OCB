from odoo import http
from odoo.tools import config
from prometheus_client import (
    generate_latest, 
    CONTENT_TYPE_LATEST,
)


class PrometheusMetricsController(http.Controller):

    @http.route("/metrics", type="http", auth="none", csrf=False)
    def metrics(self):
        if not config["prometheus_enable"]:
            return http.Response("Prometheus monitoring is disabled", status=503)
        if config["workers"]:
            return http.Response(
                "You must setup a dedicated /metrics server when using workers",
                status=503,
            )

        return http.Response(
            generate_latest(),
            content_type=CONTENT_TYPE_LATEST,
        )