"""Shared email type for CampusXolve AI.

Pydantic's EmailStr (via email-validator) rejects reserved/special-use
domains such as the `.local` domain used by all seeded development users
(e.g. admin@campusxolve.local), which would lock those accounts out of
login. This type validates the general shape of an address while allowing
`.local` development domains. Normalization (strip/lowercase) happens in
the service layer.
"""

from typing import Annotated

from pydantic import StringConstraints

CampusEmail = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]
