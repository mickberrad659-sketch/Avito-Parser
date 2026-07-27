from qrator_payload_codec import decode_field, encode_field
from generate_qrator_variants import (
    CANVAS_HASH_INDEX,
    DEFAULT_BASE_F,
    DEFAULT_BASE_S,
    UNIX_TIME_INDEX,
    generate_variants,
    load_f_base,
    load_s_base,
)


def test_generates_1000_unique_valid_variants() -> None:
    timestamp = 1_700_000_000
    variants = generate_variants(
        load_f_base(DEFAULT_BASE_F),
        load_s_base(DEFAULT_BASE_S),
        count=1000,
        timestamp=timestamp,
        seed=42,
        include_raw=True,
    )

    assert len({item["f"] for item in variants}) == 1000
    assert len({item["s"] for item in variants}) == 1
    assert len({item["canvasHash"] for item in variants}) == 1000

    for item in variants:
        raw_f = decode_field(item["f"], "f")
        values = [int(value) for value in raw_f.split(";")]
        assert len(values) == 141
        assert values[CANVAS_HASH_INDEX] == item["canvasHash"]
        assert values[UNIX_TIME_INDEX] == timestamp
        assert encode_field(raw_f, "f") == item["f"]
        assert decode_field(item["s"], "s") == item["rawS"]
