"""Write a synthetic multi-page import workbook to stdout for browser tests."""

import io
import sys

from faker import Faker
from openpyxl import Workbook

fake = Faker("tr_TR")
fake.seed_instance(3800)
workbook = Workbook()
sheet = workbook.active
sheet.title = "Students"
sheet.append(["Okul No", "Ad Soyad", "Sınıf/Şube", "2. Yabancı Dil"])
grade = 4 if "--grade-four" in sys.argv else 5
for index in range(1, 206):
    sheet.append([
        78000 + index,
        "İpek Işık" if index == 205 else f"{fake.first_name()} {fake.last_name()}",
        f"{grade}/A" if index <= 120 else f"{grade}/B" if index <= 180 else "6/A",
        "Almanca" if index % 2 == 0 else "Fransızca",
    ])
output = io.BytesIO()
workbook.save(output)
sys.stdout.buffer.write(output.getvalue())
