"""Outpost API Views"""
from dataclasses import asdict

from django.utils.translation import gettext_lazy as _
from drf_yasg.utils import swagger_auto_schema
from kubernetes.client.configuration import Configuration
from kubernetes.config.config_exception import ConfigException
from kubernetes.config.kube_config import load_kube_config_from_dict
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.fields import BooleanField, CharField, SerializerMethodField
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from authentik.core.api.utils import (
    MetaNameSerializer,
    PassiveSerializer,
    TypeCreateSerializer,
)
from authentik.lib.templatetags.authentik_utils import verbose_name
from authentik.lib.utils.reflection import all_subclasses
from authentik.outposts.models import (
    DockerServiceConnection,
    KubernetesServiceConnection,
    OutpostServiceConnection,
)


class ServiceConnectionSerializer(ModelSerializer, MetaNameSerializer):
    """ServiceConnection Serializer"""

    object_type = SerializerMethodField()

    def get_object_type(self, obj: OutpostServiceConnection) -> str:
        """Get object type so that we know which API Endpoint to use to get the full object"""
        return obj._meta.object_name.lower().replace("serviceconnection", "")

    class Meta:

        model = OutpostServiceConnection
        fields = [
            "pk",
            "name",
            "local",
            "object_type",
            "verbose_name",
            "verbose_name_plural",
        ]


class ServiceConnectionStateSerializer(PassiveSerializer):
    """Serializer for Service connection state"""

    healthy = BooleanField(read_only=True)
    version = CharField(read_only=True)


class ServiceConnectionViewSet(
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    """ServiceConnection Viewset"""

    queryset = OutpostServiceConnection.objects.select_subclasses()
    serializer_class = ServiceConnectionSerializer
    search_fields = ["name"]
    filterset_fields = ["name"]

    @swagger_auto_schema(responses={200: TypeCreateSerializer(many=True)})
    @action(detail=False, pagination_class=None, filter_backends=[])
    def types(self, request: Request) -> Response:
        """Get all creatable service connection types"""
        data = []
        for subclass in all_subclasses(self.queryset.model):
            data.append(
                {
                    "name": verbose_name(subclass),
                    "description": subclass.__doc__,
                    "component": subclass().component,
                }
            )
        return Response(TypeCreateSerializer(data, many=True).data)

    @swagger_auto_schema(responses={200: ServiceConnectionStateSerializer(many=False)})
    @action(detail=True, pagination_class=None, filter_backends=[])
    # pylint: disable=unused-argument, invalid-name
    def state(self, request: Request, pk: str) -> Response:
        """Get the service connection's state"""
        connection = self.get_object()
        return Response(asdict(connection.state))


class DockerServiceConnectionSerializer(ServiceConnectionSerializer):
    """DockerServiceConnection Serializer"""

    class Meta:

        model = DockerServiceConnection
        fields = ServiceConnectionSerializer.Meta.fields + [
            "url",
            "tls_verification",
            "tls_authentication",
        ]


class DockerServiceConnectionViewSet(ModelViewSet):
    """DockerServiceConnection Viewset"""

    queryset = DockerServiceConnection.objects.all()
    serializer_class = DockerServiceConnectionSerializer


class KubernetesServiceConnectionSerializer(ServiceConnectionSerializer):
    """KubernetesServiceConnection Serializer"""

    def validate_kubeconfig(self, kubeconfig):
        """Validate kubeconfig by attempting to load it"""
        if kubeconfig == {}:
            if not self.validated_data["local"]:
                raise serializers.ValidationError(
                    _(
                        "You can only use an empty kubeconfig when connecting to a local cluster."
                    )
                )
            # Empty kubeconfig is valid
            return kubeconfig
        config = Configuration()
        try:
            load_kube_config_from_dict(kubeconfig, client_configuration=config)
        except ConfigException:
            raise serializers.ValidationError(_("Invalid kubeconfig"))
        return kubeconfig

    class Meta:

        model = KubernetesServiceConnection
        fields = ServiceConnectionSerializer.Meta.fields + ["kubeconfig"]


class KubernetesServiceConnectionViewSet(ModelViewSet):
    """KubernetesServiceConnection Viewset"""

    queryset = KubernetesServiceConnection.objects.all()
    serializer_class = KubernetesServiceConnectionSerializer
