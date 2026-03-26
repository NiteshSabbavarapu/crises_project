from django.db import models
from django.utils.text import slugify


class Country(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=8, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class State(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="states")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("country", "name")

    def __str__(self):
        return self.name


class City(models.Model):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="cities")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("state", "name")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.state.name}-{self.name}")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Area(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="areas")
    name = models.CharField(max_length=120)
    pincode = models.CharField(max_length=12, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("city", "name", "pincode")

    def __str__(self):
        return f"{self.name}, {self.city.name}"
