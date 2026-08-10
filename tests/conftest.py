import pytest

from tracker import config


@pytest.fixture(autouse=True)
def out_leg_not_bought(monkeypatch):
    """Default pre testy: odlet NIE je kúpený.

    OUT_LEG_BOUGHT je stav reálnej cesty, nie vlastnosť kódu — bez pripnutia by
    sa správanie testov menilo podľa toho, kde sa práve nachádzame s nákupom.
    Testy pre režim „odlet kúpený" si ho prepnú samy.
    """
    monkeypatch.setattr(config, "OUT_LEG_BOUGHT", False)
