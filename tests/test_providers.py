from maintenance_copilot.config import Settings
from maintenance_copilot.providers import DocumentAiLayoutParser


def test_document_ai_parser_recovers_name_unit_value_rows_from_text() -> None:
    parser = DocumentAiLayoutParser(Settings(runtime_env="test"))
    text = """
    Product description
    Technical data
    1.2.3 Coolant thermostat
    Name
    Unit Value
    Start of opening
    °C
    °F
    82
    179
    Completely opened °C
    °F
    92
    197
    Tab. 5: Coolant thermostat
    """

    rows = parser._recover_table_rows_from_text(text)

    assert {"name": "Start of opening", "unit": "°C", "value": "82"} in rows
    assert {"name": "Start of opening", "unit": "°F", "value": "179"} in rows
    assert {"name": "Completely opened", "unit": "°C", "value": "92"} in rows
    assert {"name": "Completely opened", "unit": "°F", "value": "197"} in rows


def test_document_ai_parser_recovers_troubleshooting_rows_from_text() -> None:
    parser = DocumentAiLayoutParser(Settings(runtime_env="test"))
    text = """
    Operating faults
    Errors – Cause – Remedy
    Malfunction / error
    Cause
    Remedy
    Engine oil pressure is too low.
    Oil level in oil pan is too low.
    Fill oil to prescribed mark.
    Lubricating oil is too thin (oil
    diluted by diesel fuel).
    Drain the oil and refill with the
    specified oil.
    Pressure sensor has a fault.
    Check the oil pressure and replace
    the damaged pressure transducer.
    """

    rows = parser._recover_table_rows_from_text(text)

    assert rows[0] == {
        "malfunction": "Engine oil pressure is too low.",
        "cause": "Oil level in oil pan is too low.",
        "remedy": "Fill oil to prescribed mark.",
    }
    assert rows[1] == {
        "malfunction": "Engine oil pressure is too low.",
        "cause": "Lubricating oil is too thin (oil diluted by diesel fuel).",
        "remedy": "Drain the oil and refill with the specified oil.",
    }
    assert rows[2] == {
        "malfunction": "Engine oil pressure is too low.",
        "cause": "Pressure sensor has a fault.",
        "remedy": "Check the oil pressure and replace the damaged pressure transducer.",
    }
