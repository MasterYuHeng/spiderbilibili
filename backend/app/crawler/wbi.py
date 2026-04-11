from __future__ import annotations

from hashlib import md5
from urllib.parse import urlencode

WBI_MIXIN_KEY_ENCODER = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]

WBI_FILTER_PATTERN = set("!'()*")


def get_mixin_key(img_key: str, sub_key: str) -> str:
    source = img_key + sub_key
    return "".join(source[index] for index in WBI_MIXIN_KEY_ENCODER)[:32]


def sign_wbi_params(
    params: dict[str, object],
    *,
    img_key: str,
    sub_key: str,
) -> dict[str, str]:
    mixin_key = get_mixin_key(img_key, sub_key)
    filtered_params = {
        key: "".join(char for char in str(value) if char not in WBI_FILTER_PATTERN)
        for key, value in sorted(params.items())
        if value is not None
    }
    query = urlencode(filtered_params)
    filtered_params["w_rid"] = md5((query + mixin_key).encode("utf-8")).hexdigest()
    return filtered_params
