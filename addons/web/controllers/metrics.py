from odoo import http
from odoo.tools import config
from odoo.service.monitoring import PrometheusObserver
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST


class PrometheusMetricsController(http.Controller):

    @http.route("/metrics", type="http", auth="none", csrf=False)
    def metrics(self):
        if not config["prometheus_enable"]:
            return http.Response("Prometheus monitoring is disabled", status=503)
        return http.Response(
            generate_latest(PrometheusObserver.get_registry()),
            content_type=CONTENT_TYPE_LATEST,
        )