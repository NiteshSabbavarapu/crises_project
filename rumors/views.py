from rest_framework import generics, permissions

from .models import RumorClaim
from .serializers import RumorClaimSerializer
from .services import verify_claim


class RumorClaimListCreateView(generics.ListCreateAPIView):
    serializer_class = RumorClaimSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = RumorClaim.objects.all().select_related("city", "area", "verdict")
        city = self.request.query_params.get("city")
        if city:
            queryset = queryset.filter(city_id=city)
        return queryset

    def perform_create(self, serializer):
        claim = serializer.save(submitter=self.request.user)
        verify_claim(claim)


class RumorClaimDetailView(generics.RetrieveAPIView):
    queryset = RumorClaim.objects.all().select_related("city", "area", "verdict")
    serializer_class = RumorClaimSerializer
    permission_classes = [permissions.IsAuthenticated]
