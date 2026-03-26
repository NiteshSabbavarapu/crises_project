from django.core.management.base import BaseCommand

from jobs.reference_data import HYDERABAD_REFERENCE_DATA, SOURCE_SEED_DATA
from locations.models import Area, City, Country, State
from sources.models import Source


class Command(BaseCommand):
    help = "Seed Hyderabad reference locations and trusted source registry."

    def handle(self, *args, **options):
        country, _ = Country.objects.get_or_create(**HYDERABAD_REFERENCE_DATA["country"])
        state, _ = State.objects.get_or_create(country=country, name=HYDERABAD_REFERENCE_DATA["state"]["name"], defaults={"code": HYDERABAD_REFERENCE_DATA["state"]["code"]})
        city, _ = City.objects.get_or_create(state=state, name=HYDERABAD_REFERENCE_DATA["city"]["name"])

        for area_data in HYDERABAD_REFERENCE_DATA["areas"]:
            Area.objects.get_or_create(city=city, name=area_data["name"], pincode=area_data["pincode"])

        for source_data in SOURCE_SEED_DATA:
            Source.objects.update_or_create(name=source_data["name"], defaults=source_data)

        self.stdout.write(self.style.SUCCESS("Seeded reference data and trusted sources."))
