from django.core.management.base import BaseCommand
from travel.models import ChecklistCategory, ChecklistTemplate, ChecklistItemTemplate
from django.db import transaction

class Command(BaseCommand):
    help = 'Imports initial checklist categories and templates from Word extraction'

    def handle(self, *args, **options):
        with transaction.atomic():
            # 1. Categories
            cats_data = [
                ('Kleidung', 'bi-universal-access', 10),
                ('Körperpflege & Gesundheit', 'bi-shield-plus', 20),
                ('Technik & Sonstiges', 'bi-laptop', 30),
                ('Dokumente & Finanzen', 'bi-folder2-open', 5),
                ('Küche & Verpflegung', 'bi-cup-hot', 40),
                ('Vor der Abreise', 'bi-house-check', 50),
            ]
            categories = {}
            for name, icon, order in cats_data:
                cat, _ = ChecklistCategory.objects.get_or_create(
                    name=name,
                    defaults={'icon': icon, 'order': order}
                )
                categories[name] = cat

            # Helper to quickly add items
            def add_items(template, category_name, items_list, due_days=0):
                cat = categories.get(category_name)
                for text in items_list:
                    ChecklistItemTemplate.objects.get_or_create(
                        template=template,
                        category=cat,
                        text=text.strip(),
                        due_days_before=due_days
                    )

            # 2. Template: Wohnmobil
            womo, _ = ChecklistTemplate.objects.get_or_create(name="Wohnmobil Tour")
            add_items(womo, 'Kleidung', [
                "Unterwäsche", "Hosen kurz", "Hosen lang", "Socken", "Schlafanzug", 
                "Jogginghosen", "Dicke Socken", "Regenjacken", "Windjacken", "Turnschuhe", "Flipflops"
            ])
            add_items(womo, 'Körperpflege & Gesundheit', [
                "Sonnencreme", "Autan", "bite away Stick", "Medikamente", "Zahnbürste", 
                "Duschgel", "Shampoo", "Pflaster", "Fön", "Rasierer"
            ])
            add_items(womo, 'Technik & Sonstiges', [
                "Laptop & Ladekabel", "Handy & Ladekabel", "Ersatzbrille", "Kindles", 
                "Taschenmesser", "Reiseführer", "Stirnlampe", "Powerbank", "Minifaszienrolle"
            ])
            add_items(womo, 'Küche & Verpflegung', [
                "Ketchup/Majo/Senf", "Essig/Öl", "Gewürze", "Spülmittel", "Marmelade", "Kaffee/Milch"
            ])
            add_items(womo, 'Vor der Abreise', [
                "Schlüssel Nachbarn geben", "Zeitung abbestellen", "Geldbeutel ausräumen", 
                "Blumen gießen", "Bügeleisen aus", "Herd aus", "Stecker ziehen"
            ], due_days=1)

            # 3. Template: Übersee (Dokumente Fokus)
            overseas, _ = ChecklistTemplate.objects.get_or_create(name="Übersee / Fernreise")
            add_items(overseas, 'Dokumente & Finanzen', [
                "Reisepass (Gültigkeit prüfen!)", "Kreditkarten", "Krankenkarten", 
                "Auslandskrankenversicherung", "Internationaler Führerschein", "Einreisevisa", "Ticket-Kopien"
            ], due_days=30)
            add_items(overseas, 'Technik & Sonstiges', ["Universal-Adapterstecker", "Kofferwaage", "Oropax"])

            # 4. Template: Wandern
            wandern, _ = ChecklistTemplate.objects.get_or_create(name="Wanderurlaub")
            add_items(wandern, 'Kleidung', [
                "Wanderschuhe", "Wandersocken", "Wanderhose", "Funktions-Shirts", "Wanderstöcke", "Mütze/Stirnband"
            ])
            add_items(wandern, 'Technik & Sonstiges', ["Wanderkarten", "Rucksack", "Trinkflasche", "Vesperdose"])

            # 5. Template: Wellness / Hotel
            wellness, _ = ChecklistTemplate.objects.get_or_create(name="Wellness & Hotel")
            add_items(wellness, 'Kleidung', [
                "Schicke Kleidung für abends", "Bademantel", "Badeschuhe / Flipflops", "Badeanzug / Bikini"
            ])
            add_items(wellness, 'Körperpflege & Gesundheit', ["Körperöl", "Haarspray", "Nagellack"])

        self.stdout.write(self.style.SUCCESS('Successfully imported checklist templates and categories'))
