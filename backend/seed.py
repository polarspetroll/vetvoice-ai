"""seed 200 fake clients with pets. same data every run (seed 42)"""
import random
from faker import Faker
from sqlalchemy import select, func

from backend.db import SessionLocal
from backend.models import Client, Pet

DOGS = ["Labrador", "Golden Retriever", "French Bulldog", "Beagle", "Poodle", "German Shepherd", "Shih Tzu", "Mixed"]
CATS = ["Domestic Shorthair", "Maine Coon", "Siamese", "Ragdoll", "Bengal"]
PET_NAMES = ["Max", "Bella", "Luna", "Charlie", "Milo", "Daisy", "Rocky", "Coco", "Oliver", "Lucy", "Bailey",
             "Nala", "Teddy", "Ruby", "Simba", "Ziggy", "Pepper", "Winston", "Maple", "Biscuit", "Juniper", "Mochi",
             "Olive", "Hazel", "Murphy", "Tucker", "Willow", "Leo", "Cleo", "Bruno"]


def fake_phone(i):
    # 555-01xx numbers are reserved for fiction so no real person gets these
    area = "416" if i < 100 else "647"
    return f"+1{area}55501{i % 100:02d}"


def build(n=200):
    fake = Faker("en_CA")
    Faker.seed(42)
    rnd = random.Random(42)
    clients = []
    for i in range(n):
        c = Client(first_name=fake.first_name(), last_name=fake.last_name(), phone=fake_phone(i), email=fake.email())
        used = set()
        for _ in range(rnd.choice([1, 1, 1, 2, 2, 3])):
            name = rnd.choice([p for p in PET_NAMES if p not in used])
            used.add(name)
            species = rnd.choice(["dog", "dog", "cat", "cat", "rabbit"])
            breed = rnd.choice(DOGS) if species == "dog" else rnd.choice(CATS) if species == "cat" else None
            c.pets.append(Pet(name=name, species=species, breed=breed, birth_year=rnd.randint(2010, 2025)))
        clients.append(c)
    return clients


def main():
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(Client)):
            print("already seeded, skipping")
            return
        db.add_all(build())
        db.commit()
        print("seeded", db.scalar(select(func.count()).select_from(Client)), "clients",
              db.scalar(select(func.count()).select_from(Pet)), "pets")


if __name__ == "__main__":
    main()
