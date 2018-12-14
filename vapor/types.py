from typing import Any, Dict

import kubernetes


class DeployedService(object):
    def stop(self) -> None:
        return None


class KubernetesDeployedService(DeployedService):
    def __init__(self, host: str, namespace: str) -> None:
        """host is the URL we can expect to access the service with"""
        self.host = host
        self.namespace = namespace

    @property
    def deployment(self) -> kubernetes.client.ExtensionsV1beta1Deployment:
        pass


class Request(object):
    """Request represents a generic request, with context from each environment passed down
    in a `params` dictionary. Individual execution engines can subclass this to provide their
    own environment-specific context.
    """
    def __init__(self, params: Dict[str, Any]) -> None:
        self.params = params


class HelmChart(KubernetesDeployedService):
    """HelmChart represents the running state of a helm chart, and can include any of the primitives
    inherited from the Kubernetes objects.
    """
    pass
