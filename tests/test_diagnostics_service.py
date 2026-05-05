from services.diagnostics_service import diagnose


def test_unknown_fault_code_returns_unknown_code_response():
    result = diagnose(
        code="ZZZ9999",
        make="Toyota",
        model="Avensis",
        symptoms="ei käynnisty",
        engine="1.8",
    )

    assert result["success"] is False
    assert result["unknown_code"] is True
    assert result["fault_code"] == "ZZZ9999"


def test_unknown_fault_code_is_uppercased_in_response():
    result = diagnose(
        code="abc123",
        make="Toyota",
        model="Avensis",
        symptoms="ei käynnisty",
        engine="1.8",
    )

    assert result["success"] is False
    assert result["unknown_code"] is True
    assert result["fault_code"] == "ABC123"

def test_known_fault_code_returns_success():
    result = diagnose(
        code="P0300",  # vaihda tähän vikakoodi joka varmasti on sun kannassa
        make="Toyota",
        model="Avensis",
        symptoms="nykii",
        engine="1.8",
    )

    assert result["success"] is True
    assert result["unknown_code"] is False
    assert "possible_causes" in result