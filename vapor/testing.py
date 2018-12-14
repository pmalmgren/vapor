from .types import KubernetesService


def assert_deployments_running(deployed_service: KubernetesService) -> None:
    deployment = deployed_service.deployment
    status = deployment.status

    assert (
        status.updated_replicas == deployment.spec.replicas and
        status.replicas == deployment.spec.replicas and
        status.available_replicas == deployment.spec.replicas and
        status.observed_generation >= deployment.metadata.generation
    )
