"""Special-goods vocabulary shared by products, rack rows and the putaway rules (docs/survey.md A8)."""

# Temperature presets in °C (survey A8.1). The UI picks a band; min/max follow from it.
# shortcut: "frozen" (≤ −18 °C) has no lower bound in the sources; −30 °C stands in for one.
# Lower it if a colder zone is ever modelled.
TEMP_BANDS = {
    'frozen': ('Frozen food (≤ −18 °C)', -30.0, -18.0),
    'pharma_freezer': ('Pharma freezer (−25…−10 °C)', -25.0, -10.0),
    'pharma_fridge': ('Pharma fridge (2…8 °C)', 2.0, 8.0),
    'chilled': ('Chilled food (0…5 °C)', 0.0, 5.0),
    'cool': ('Cool (8…15 °C)', 8.0, 15.0),
    'controlled_room': ('Controlled room (15…25 °C)', 15.0, 25.0),
}
BAND_SELECTION = [(key, label) for key, (label, _lo, _hi) in TEMP_BANDS.items()] + [('custom', 'Custom range')]

# Hazard storage classes (survey A8.2, TRGS 510 simplified). A row approves each with a boolean hazard_<key>.
HAZARD_CLASSES = [
    ('gas', 'Compressed gas'),
    ('flammable_liquid', 'Flammable liquid'),
    ('flammable_solid', 'Flammable solid'),
    ('oxidiser', 'Oxidiser'),
    ('toxic', 'Toxic'),
    ('corrosive', 'Corrosive'),
]
