from rest_framework import serializers

from .models import RumorClaim, RumorEvidence, RumorVerdict


class RumorEvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = RumorEvidence
        fields = ("id", "source_name", "url", "note")


class RumorVerdictSerializer(serializers.ModelSerializer):
    evidence = RumorEvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = RumorVerdict
        fields = ("verdict", "confidence", "explanation", "official_link", "verified_at", "evidence")


class RumorClaimSerializer(serializers.ModelSerializer):
    verdict = RumorVerdictSerializer(read_only=True)

    class Meta:
        model = RumorClaim
        fields = (
            "id",
            "text",
            "city",
            "area",
            "pincode",
            "extracted_entities",
            "status",
            "created_at",
            "updated_at",
            "verdict",
        )
