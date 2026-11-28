"""The rules, on the lines the reader took from the ministry's real pictures (fixtures/)."""

import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "kuwait"))

from collect import albums  # noqa: E402
from parse import (  # noqa: E402
    Catalog, announcement, category, names_production_dates, normalized, read_lines, repeats, years_in,
)

MAKES = json.loads((HERE.parent / "kuwait" / "makes.json").read_text(encoding="utf-8"))
CATALOG = Catalog(MAKES["makes"], MAKES["aliases"])


def read(picture):
    lines = read_lines((HERE / "fixtures" / f"{picture}.txt").read_text(encoding="utf-8"))
    return announcement(lines, CATALOG)


def vehicles(found):
    return [(v["make"], v["models"], v["years"]) for v in found["vehicles"]]


class Words(unittest.TestCase):
    def test_arabic_spellings_are_read_as_one(self):
        self.assertEqual(normalized("إنفينيتي"), normalized("انفينيتي"))
        self.assertEqual(normalized("الوسادة الهوائية"), normalized("الوساده الهوائيه"))
        self.assertEqual(normalized("الخط الساخن: ١٨٤٦٤٦٤"), "الخط الساخن 1846464")

    def test_years_as_a_first_and_a_last(self):
        self.assertEqual(years_in("2027 - 2021"), (2021, 2027))
        self.assertEqual(years_in("Model Year 2021,2022 & 2023"), (2021, 2023))
        self.assertEqual(years_in("(2021) I-PACE جاكوار"), (2021, 2021))
        self.assertIsNone(years_in("عدد السيارات ( 134)"))

    def test_a_vin_is_not_read_as_years(self):
        self.assertIsNone(years_in("VIN: 5TDLB3CHXMS043712 to 5TDLB3CH7PS599559"))

    def test_production_dates_are_told_apart(self):
        self.assertTrue(names_production_dates("October/2020 - May/2025"))
        self.assertTrue(names_production_dates("نوفمبر 2024 - أغسطس 2025"))
        self.assertTrue(names_production_dates("28/06/2025 - 03/10/2025"))
        self.assertFalse(names_production_dates("Model Year 2025 & 2026"))

    def test_the_category_follows_the_fault(self):
        self.assertEqual(category("قد يتعرض نظام الوسادة الهوائية الخاصة بالسائق للتآكل"), "airBags")
        self.assertEqual(category("خلل في مسمار ذراع التعليق الخلفي والمكابح الخلفية"), "suspension")
        self.assertEqual(category("شاشة لوحة العدادات ... يقلل من القدرة على رؤية بعض المؤشرات"), "electrical")
        self.assertEqual(category("كلام لا يدل على شيء"), "other")


class Pictures(unittest.TestCase):
    def test_one_model_with_its_years(self):
        found = read("36847b23-d823-4980-8c96-a8fe7860ff35")
        self.assertEqual(found["status"], "ready")
        self.assertEqual(vehicles(found), [("Hyundai", ["Palisade"], [2026, 2026])])
        self.assertEqual(found["category"], "seats")
        self.assertTrue(found["fault"].startswith("في بعض المركبات نظام منع طي الكرسي"))
        self.assertIn("1808444", found["remedy"])
        self.assertNotIn("تم تنظيم", found["remedy"])

    def test_models_sharing_their_years_are_one_entry(self):
        found = read("482f0f6a-a725-4339-a297-71d5a336aa9b")
        self.assertEqual(vehicles(found), [("Genesis", ["G90", "G80", "GV80", "GV70"], [2020, 2025])])

    def test_years_written_before_the_models_cover_them_all(self):
        found = read("9c945f59-c813-4e8a-859c-341a3f660d8f")
        self.assertEqual(vehicles(found), [("Chevrolet", ["Tahoe", "Suburban"], [2022, 2022])])

    def test_models_with_their_own_years_are_entries_of_their_own(self):
        found = read("d28e7517-a951-4264-82e0-e333a3b210c0")
        self.assertEqual(found["status"], "ready")
        self.assertEqual(vehicles(found), [("Infiniti", ["QX55"], [2022, 2022]), ("Infiniti", ["QX50"], [2018, 2020])])

    def test_the_make_is_known_from_its_models_alone(self):
        found = read("39a4dd84-9412-490b-9ad2-e6b7edb86894")
        self.assertEqual(found["status"], "ready")
        self.assertEqual(vehicles(found), [
            ("Land Rover", ["Discovery"], [2021, 2027]),
            ("Land Rover", ["Defender"], [2020, 2027]),
            ("Land Rover", ["Range Rover"], [2022, 2027]),
        ])

    def test_factory_names_are_read_as_the_lists_names(self):
        self.assertEqual(vehicles(read("4fa2eb0d-3d4e-4050-b84f-214a197b7930")), [("Toyota", ["Land Cruiser"], [2025, 2026])])
        self.assertEqual(vehicles(read("bf3f06d1-b3ee-48db-9aaa-60af8ebbbfb5")), [("Toyota", ["Prado"], [2024, 2025])])

    def test_production_dates_wait_for_a_person(self):
        found = read("b30bd0b9-b806-4c0b-9e07-5d9fbdec6a9a")
        self.assertEqual(found["status"], "needs-review")
        self.assertEqual(vehicles(found), [("Kia", ["Telluride"], [2024, 2025])])

    def test_a_model_the_list_lacks_waits_for_a_person(self):
        found = read("93700122-2ceb-438c-9f34-d7d49ac2d2a5")
        self.assertEqual(found["status"], "needs-review")
        self.assertEqual(found["vehicles"], [])

    def test_sections_read_out_of_order_wait_for_a_person(self):
        found = read("67f98eb7-2b04-4d3e-98c2-f175dcd0d24e")
        self.assertEqual(found["status"], "needs-review")
        self.assertEqual(found["fault"], "")

    def test_a_picture_with_no_make_waits_for_a_person(self):
        self.assertEqual(read("9b2e375d-10a1-4b3a-ac68-a941578c04b7")["status"], "needs-review")

    def test_a_picture_published_twice_is_seen_as_a_repeat(self):
        first = read("9c945f59-c813-4e8a-859c-341a3f660d8f")
        second = read("9cb0cd94-5c3f-4e50-a996-dd55a07d779e")
        self.assertTrue(repeats(second, first))
        self.assertFalse(repeats(read("482f0f6a-a725-4339-a297-71d5a336aa9b"), first))

    def test_a_tire_recall_is_left(self):
        lines = [(1.0, "استدعاء إطارات"), (1.0, "الخلل"), (1.0, "شيء")]
        self.assertEqual(announcement(lines, CATALOG)["status"], "skipped")


class Page(unittest.TestCase):
    def test_albums_with_their_dates(self):
        page = (
            '<div class="albums"><a class="al" href="../x/1/index.html"><img src="https://files.moci.gov.kw/'
            'mocisite/assets/content/uploads/2026/10/799cc12f-bde8-450d-9bee-ad7c11a40382.jpg" '
            'alt="تاريخ الاستدعاء:2026/9/24"></a><a class="al" href="../x/2/index.html"><img '
            'src="https://elsewhere.example/9b2e375d-10a1-4b3a-ac68-a941578c04b7.jpg" alt="2026/7/30"></a>'
            '<a class="al" href="../x/3/index.html"><img src="https://files.moci.gov.kw/u/'
            '9b2e375d-10a1-4b3a-ac68-a941578c04b7.jpg" alt="تاريخ الاستدعا:2026/7/30"></a></div>'
        )
        self.assertEqual([(a["picture"][:8], a["date"]) for a in albums(page)], [
            ("799cc12f", "2026-09-24"),
            ("9b2e375d", "2026-07-30"),
        ])


if __name__ == "__main__":
    unittest.main()
