import pytest
import requests

from typing import Dict

from vapor import bootstrap, testing
from vapor.types import HelmChart


def helm_function(name: str) -> Dict[str, str]:
    return {
        'message': f'Hello {name}!'
    }


@pytest.fixture(scope='module')
def deployed_helm_chart(request) -> HelmChart:
    """Starts and loads the Helm chart"""
    deployed_helm_chart = bootstrap(
        fn=helm_function,
        conf='vapor.toml',
    )

    def fin():
        deployed_helm_chart.stop()

    request.addfinalizer(fin)
    return deployed_helm_chart


def test_helm_chart_infra(deployed_helm_chart: HelmChart) -> None:
    """vapor bootstrap should create pods, a deployment, a service, and an ingress to access the service"""
    testing.assert_deployments_running(deployed_helm_chart)


def test_helm_function_response(deployed_helm_chart: HelmChart) -> None:
    """the bootstrapped helm function should return the data"""
    resp = requests.get(deployed_helm_chart.host, data={'name': 'test client'})
    assert resp.status_code == 200
    assert resp.json['message'] == 'Hello test client!'
